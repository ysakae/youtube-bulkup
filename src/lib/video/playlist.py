import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.quota import QuotaExceededError, is_quota_error
from ..data.snapshot import SnapshotCache

logger = logging.getLogger("youtube_up")


@dataclass(frozen=True)
class PlaylistInfo:
    """1つのプレイリストのメタ情報。"""

    id: str
    title: str
    item_count: int
    privacy: str
    published_at: str


class PlaylistManager:
    """
    Manages YouTube Playlist interactions.
    """

    def __init__(self, credentials, cache: Optional[SnapshotCache] = None):
        self.credentials = credentials
        # タイトル -> 「正の」プレイリストID。同名が複数ある場合は最古のものを指す。
        self._playlist_cache: Dict[str, str] = {}
        # 全プレイリスト (同名の重複も含む)
        self._playlists: List[PlaylistInfo] = []
        self._initialized = False
        self._cache = cache

    def _ensure_cache(self):
        """
        Populates the cache with existing playlists from the channel.
        This is done lazily to avoid startup latency if not needed.

        全ページを取得する。ページネーションを怠ると既存プレイリストを
        見落として同名のものを重複作成してしまう。
        """
        if self._initialized:
            return

        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )

            playlists: List[PlaylistInfo] = []
            next_page_token = None

            while True:
                response = service.playlists().list(
                    part="snippet,contentDetails,status",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page_token,
                ).execute()

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    playlists.append(
                        PlaylistInfo(
                            id=item["id"],
                            title=snippet.get("title", ""),
                            item_count=item.get("contentDetails", {}).get(
                                "itemCount", 0
                            ),
                            privacy=item.get("status", {}).get(
                                "privacyStatus", "private"
                            ),
                            published_at=snippet.get("publishedAt", ""),
                        )
                    )

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            self._playlists = playlists
            self._playlist_cache = self._build_title_index(playlists)
            if self._cache is not None:
                self._cache.save_playlists([
                    {
                        "id": p.id,
                        "title": p.title,
                        "item_count": p.item_count,
                        "privacy": p.privacy,
                        "published_at": p.published_at,
                    }
                    for p in playlists
                ])
                self._cache.mark_complete("playlists")
            self._initialized = True
            logger.debug(
                f"Initialized playlist cache with {len(playlists)} playlists "
                f"({len(self._playlist_cache)} unique titles)."
            )

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while listing playlists: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to list playlists: {e}")
            # 初期化済みにしない (次回リトライできるようにする)

    @staticmethod
    def _build_title_index(playlists: List[PlaylistInfo]) -> Dict[str, str]:
        """タイトル -> 正のプレイリストID の索引を作る。

        同名が複数ある場合は published_at が最も古いものを「正」とする。
        後から誤って作成された重複ではなく、本来のプレイリストを選ぶため。
        """
        index: Dict[str, PlaylistInfo] = {}
        for pl in playlists:
            current = index.get(pl.title)
            if current is None or pl.published_at < current.published_at:
                index[pl.title] = pl
        return {title: pl.id for title, pl in index.items()}

    def _all_playlist_ids(self) -> List[str]:
        """走査対象の全プレイリストID。重複プレイリストも含む。

        _playlists と _playlist_cache の両方から集めて重複を除く。
        _playlists が空のとき (テストが _playlist_cache に直接代入した場合など) も、
        新規作成直後で片方にしか反映されていない場合も、取りこぼさないため。
        """
        ids = []
        seen = set()
        for playlist_id in [p.id for p in self._playlists] + list(
            self._playlist_cache.values()
        ):
            if playlist_id not in seen:
                seen.add(playlist_id)
                ids.append(playlist_id)
        return ids

    def get_duplicate_playlists(self) -> Dict[str, List[PlaylistInfo]]:
        """同名プレイリストが2つ以上あるものを {title: [PlaylistInfo, ...]} で返す。

        各リストは published_at 昇順 (先頭が「正」)。
        """
        self._ensure_cache()

        grouped: Dict[str, List[PlaylistInfo]] = {}
        for pl in self._playlists:
            grouped.setdefault(pl.title, []).append(pl)

        return {
            title: sorted(items, key=lambda p: p.published_at)
            for title, items in grouped.items()
            if len(items) > 1
        }

    def get_or_create_playlist(self, title: str, privacy_status: str = "private") -> Optional[str]:
        """
        Retrieves a playlist ID by title, or creates one if it doesn't exist.
        """
        self._ensure_cache()

        if title in self._playlist_cache:
            return self._playlist_cache[title]

        # Create new playlist
        logger.info(f"Creating new playlist: '{title}' ({privacy_status})")

        body = {
            "snippet": {
                "title": title,
                "description": f"Created into playlist '{title}' by youtube-bulkup"
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }

        try:
            # Build fresh service for write operation
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            request = service.playlists().insert(
                part="snippet,status",
                body=body
            )
            response = request.execute()

            playlist_id = response["id"]
            self._playlist_cache[title] = playlist_id
            # _playlists にも反映する (再走査時に新規作成分が漏れないようにするため)。
            # _build_title_index は再実行しない: _playlists が空の状態
            # (テストが _playlist_cache に直接代入したケースなど) で再構築すると
            # 既存の _playlist_cache のエントリが消えてしまうため。
            self._playlists.append(
                PlaylistInfo(
                    id=playlist_id,
                    title=title,
                    item_count=0,
                    privacy=privacy_status,
                    published_at=response.get("snippet", {}).get("publishedAt", ""),
                )
            )
            logger.info(f"Created playlist '{title}' -> {playlist_id}")
            return playlist_id

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while creating playlist '{title}': {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to create playlist '{title}': {e}")
            return None

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Adds a video to a specific playlist.
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            request = service.playlistItems().insert(
                part="snippet",
                body=body
            )
            request.execute()
            logger.info(f"Added video {video_id} to playlist {playlist_id}")
            return True

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while adding {video_id}: {e}")
                raise QuotaExceededError(str(e)) from e

            if "videoAlreadyInPlaylist" in str(e): # Check specific error message if possible
                logger.info(f"Video {video_id} already in playlist {playlist_id}")
                return True

            logger.error(f"Failed to add video {video_id} to playlist {playlist_id}: {e}")
            return False

    def remove_video_from_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Removes a video from a specific playlist.
        Requires finding the playlistItemId first.
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            # 1. Find the playlistItem ID for this video in this playlist
            # API doesn't let us delete by videoId directly, we need the item ID.
            request = service.playlistItems().list(
                part="id",
                playlistId=playlist_id,
                videoId=video_id
            )
            response = request.execute()
            items = response.get("items", [])

            if not items:
                logger.warning(f"Video {video_id} not found in playlist {playlist_id}")
                return False

            # There could theoretically be duplicates, we remove the first one found
            playlist_item_id = items[0]["id"]

            # 2. Delete the playlist item
            delete_request = service.playlistItems().delete(id=playlist_item_id)
            delete_request.execute()

            logger.info(f"Removed video {video_id} from playlist {playlist_id}")
            return True

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while removing {video_id}: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to remove video {video_id} from playlist {playlist_id}: {e}")
            return False

    def get_video_ids_from_playlist(self, playlist_name_or_id: str) -> List[str]:
        """
        Retrieves all video IDs from a playlist.
        """
        playlist_id = self.get_or_create_playlist(playlist_name_or_id)
        if not playlist_id:
             # It might be an ID directly, check if we can list items using it as ID
             # But get_or_create logic currently treats input as title if not found in cache.
             # If user passes ID, get_or_create creates a new playlist with that ID as title.
             # This is a limitation acknowledged in previous steps.
             # For now, we rely on get_or_create resolving title to ID.
             # If it fails (e.g. error), we return empty.
             return []

        video_ids = []
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            request = service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50
            )

            while request:
                response = request.execute()
                for item in response.get("items", []):
                    video_ids.append(item["contentDetails"]["videoId"])

                request = service.playlistItems().list_next(request, response)

            logger.info(f"Found {len(video_ids)} videos in playlist {playlist_name_or_id}")
            return video_ids

        except HttpError as e:
            logger.error(f"Failed to get videos from playlist {playlist_name_or_id}: {e}")
            return []

    def find_playlist_id(self, name_or_id: str) -> Optional[str]:
        """
        Tries to resolve a name or ID to a Playlist ID.
        Checks cache first (titles), then checks if cached values match (IDs).
        """
        self._ensure_cache()

        # 1. Check if it's a known title
        if name_or_id in self._playlist_cache:
            return self._playlist_cache[name_or_id]

        # 2. Check if it's a known ID (value in cache)
        if name_or_id in self._playlist_cache.values():
            return name_or_id

        # 3. If not found in cache, it might be an ID we haven't seen (unlikely if cache is full list),
        # or a title we haven't seen.
        # For now, we assume if it starts with "PL" it's an ID, otherwise treat as title (which failed).
        # But to be safe, if we return None, the caller can decide.
        return None

    def rename_playlist(self, name_or_id: str, new_title: str) -> bool:
        """
        Renames a playlist.
        """
        playlist_id = self.find_playlist_id(name_or_id)
        if not playlist_id:
            # If not found in cache, maybe it's a raw ID passed by user?
            # Let's assume if it looks like an ID, we try to use it.
            if name_or_id.startswith("PL"):
                 playlist_id = name_or_id
            else:
                 logger.error(f"Playlist not found: {name_or_id}")
                 return False

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            # 1. Get current snippet to preserve other fields
            request = service.playlists().list(
                part="snippet",
                id=playlist_id
            )
            response = request.execute()
            items = response.get("items", [])

            if not items:
                logger.error(f"Playlist {playlist_id} not found on YouTube.")
                return False

            snippet = items[0]["snippet"]

            # 2. Update title
            snippet["title"] = new_title

            # 3. Update playlist
            body = {
                "id": playlist_id,
                "snippet": snippet
            }

            update_request = service.playlists().update(
                part="snippet",
                body=body
            )
            update_request.execute()

            # Update cache if possible
            # We need to remove old entry if it was keyed by old title
            keys_to_remove = [k for k, v in self._playlist_cache.items() if v == playlist_id]
            for k in keys_to_remove:
                del self._playlist_cache[k]
            self._playlist_cache[new_title] = playlist_id

            logger.info(f"Renamed playlist {playlist_id} to '{new_title}'")
            return True

        except HttpError as e:
            logger.error(f"Failed to rename playlist {name_or_id}: {e}")
            return False

    def delete_playlist(self, playlist_id: str) -> bool:
        """プレイリストを削除する (中の動画自体は削除されない)。"""
        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )
            service.playlists().delete(id=playlist_id).execute()

            # キャッシュからも取り除く。_all_playlist_ids() は _playlists と
            # _playlist_cache の両方をマージして返すため、片方からしか
            # 除去しないと削除済みのIDが走査対象に残り続けてしまう。
            #
            # _build_title_index(self._playlists) で _playlist_cache を
            # 丸ごと作り直す方法は取らない: _playlists が空のとき
            # (テストが _playlist_cache に直接代入したケースなど) に
            # 実行すると、削除対象と無関係な他のエントリまで巻き込んで
            # 消えてしまうため。該当エントリだけを個別に除去する。
            self._playlists = [
                p for p in self._playlists if p.id != playlist_id
            ]
            self._playlist_cache = {
                title: pid
                for title, pid in self._playlist_cache.items()
                if pid != playlist_id
            }

            logger.info(f"Deleted playlist {playlist_id}")
            return True

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while deleting {playlist_id}: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to delete playlist {playlist_id}: {e}")
            return False

    def list_playlists(self) -> List[Dict[str, str]]:
        """
        全プレイリストの一覧を取得する。
        各プレイリストのタイトル、ID、動画数、公開設定を返す。
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            playlists = []
            next_page_token = None

            while True:
                request = service.playlists().list(
                    part="snippet,contentDetails,status",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get("items", []):
                    playlists.append({
                        "id": item["id"],
                        "title": item["snippet"]["title"],
                        "item_count": item["contentDetails"]["itemCount"],
                        "privacy": item["status"]["privacyStatus"],
                    })

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            logger.info(f"Found {len(playlists)} playlists.")
            return playlists

        except HttpError as e:
            logger.error(f"Failed to list playlists: {e}")
            return []

    def list_playlist_items(self, playlist_name_or_id: str) -> List[Dict[str, str]]:
        """
        指定プレイリスト内の全動画の一覧を取得する。
        各動画のタイトルとVideoIDを返す。
        """
        # プレイリスト名からIDを解決（find_playlist_id で新規作成しない）
        playlist_id = self.find_playlist_id(playlist_name_or_id)
        if not playlist_id:
            logger.error(f"Playlist not found: {playlist_name_or_id}")
            return []

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            items = []
            next_page_token = None

            while True:
                request = service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get("items", []):
                    items.append({
                        "video_id": item["contentDetails"]["videoId"],
                        "title": item["snippet"]["title"],
                        "position": item["snippet"]["position"],
                    })

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            logger.info(f"Found {len(items)} items in playlist {playlist_name_or_id}.")
            return items

        except HttpError as e:
            logger.error(f"Failed to list playlist items for {playlist_name_or_id}: {e}")
            return []

    def get_all_playlists_map(
        self, refresh: bool = False, offline: bool = False
    ) -> Dict[str, Set[str]]:
        """
        Returns a map where key is Playlist ID and value is a Set of Video IDs in that playlist.

        重複プレイリストの中身も含める。漏らすと重複側にだけ入っている動画が
        オーファンと誤判定される。

        refresh=True: キャッシュを無視して API から取り直す
        offline=True: API を一切叩かず、期限切れでもキャッシュを使う
                      (キャッシュが空なら RuntimeError)
        """
        if offline:
            if self._cache is None:
                raise RuntimeError(
                    "offline モードにはキャッシュが必要です。"
                    "settings.yaml で cache.enabled を有効にしてください。"
                )
            cached = self._cache.load_playlist_map()
            if not cached:
                raise RuntimeError(
                    "キャッシュが空のため offline モードで実行できません。"
                    "クォータに余裕があるときに --refresh 付きで実行してください。"
                )
            return cached

        if self._cache is not None and not refresh and self._cache.is_fresh("playlist_items"):
            cached = self._cache.load_playlist_map()
            if cached:
                logger.info(f"Loaded {len(cached)} playlists from cache.")
                return cached

        self._ensure_cache()
        playlist_map: Dict[str, Set[str]] = {}

        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )

            for playlist_id in self._all_playlist_ids():
                video_ids = set()

                request = service.playlistItems().list(
                    part="contentDetails",
                    playlistId=playlist_id,
                    maxResults=50
                )

                while request:
                    response = request.execute()
                    for item in response.get("items", []):
                        video_ids.add(item["contentDetails"]["videoId"])

                    request = service.playlistItems().list_next(request, response)

                playlist_map[playlist_id] = video_ids
                if self._cache is not None:
                    self._cache.save_playlist_items(playlist_id, video_ids)

            if self._cache is not None and self._initialized and self._all_playlist_ids():
                # 走査対象から外れたプレイリスト (YouTube 側で削除された、
                # dedupe で消した等) の行を落とす。save_playlist_items は
                # 該当 playlist_id の行しか置換しないため、これを怠ると
                # 「存在しないプレイリストの中身」がキャッシュに残り、
                # そこにしか入っていない動画がオーファンとして検出されなくなる。
                #
                # ただし _ensure_cache が非クォータの HttpError を握りつぶして
                # 戻った場合 (_initialized が False のまま) は走査対象が空になる。
                # この状態で prune すると、一過性のサーバエラー1回でキャッシュを
                # 丸ごと失ってしまうため、一覧取得が成功したときだけ実行する。
                self._cache.prune_playlist_items(set(playlist_map.keys()))
                # 全件を走査し終えたときだけ「完了」を記録する
                self._cache.mark_complete("playlist_items")

            return playlist_map

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while building playlist map: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to build playlist map: {e}")
            return {}
