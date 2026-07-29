import logging
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..core.quota import QuotaExceededError, is_quota_error
from ..data.snapshot import SnapshotCache

logger = logging.getLogger("youtube_up")


class VideoManager:
    """
    Manages general YouTube Video interactions (metadata, settings, deletion).
    """

    def __init__(self, credentials, cache: Optional[SnapshotCache] = None):
        self.credentials = credentials
        self._cache = cache

    def update_privacy_status(self, video_id: str, privacy_status: str) -> bool:
        """
        Updates the privacy status of a video (public, private, unlisted).
        """
        if privacy_status not in ["public", "private", "unlisted"]:
            logger.error(f"Invalid privacy status: {privacy_status}")
            return False

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            body = {
                "id": video_id,
                "status": {
                    "privacyStatus": privacy_status
                }
            }

            request = service.videos().update(
                part="status",
                body=body
            )
            request.execute()
            
            logger.info(f"Updated privacy status for {video_id} to {privacy_status}")
            return True

        except HttpError as e:
            logger.error(f"Failed to update privacy status for {video_id}: {e}")
            return False

    def update_metadata(
        self,
        video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None,
        category_id: Optional[str] = None
    ) -> bool:
        """
        Updates metadata for a video. Fetches current snippet first to preserve other fields.
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            # 1. Get current snippet
            request = service.videos().list(
                part="snippet",
                id=video_id
            )
            response = request.execute()
            items = response.get("items", [])
            
            if not items:
                logger.error(f"Video {video_id} not found.")
                return False
                
            snippet = items[0]["snippet"]
            
            # 2. Update fields if provided
            if title:
                snippet["title"] = title
            if description:
                snippet["description"] = description
            if tags is not None:
                snippet["tags"] = tags
            if category_id:
                snippet["categoryId"] = category_id
                
            # 3. specific update
            update_body = {
                "id": video_id,
                "snippet": {
                    "title": snippet["title"],
                    "description": snippet["description"],
                    "tags": snippet.get("tags", []),
                    "categoryId": snippet["categoryId"]
                }
            }
            
            update_request = service.videos().update(
                part="snippet",
                body=update_body
            )
            update_request.execute()
            
            logger.info(f"Updated metadata for {video_id}")
            return True

        except HttpError as e:
            logger.error(f"Failed to update metadata for {video_id}: {e}")
            return False

    def update_thumbnail(self, video_id: str, image_path: str) -> bool:
        """
        Updates the thumbnail of a video.
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            request = service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(image_path)
            )
            request.execute()
            
            logger.info(f"Updated thumbnail for {video_id} from {image_path}")
            return True
        except HttpError as e:
            logger.error(f"Failed to update thumbnail for {video_id}: {e}")
            return False

    def delete_video(self, video_id: str) -> bool:
        """
        Deletes a video from YouTube.
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            request = service.videos().delete(
                id=video_id
            )
            request.execute()
            
            logger.info(f"Deleted video {video_id}")
            return True
        except HttpError as e:
            logger.error(f"Failed to delete video {video_id}: {e}")
            return False

    def get_all_uploaded_videos(
        self, refresh: bool = False, offline: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieves all videos uploaded by the authenticated user.
        公開状態 (privacyStatus) も含めて返す。

        refresh=True: キャッシュを無視して API から取り直す
        offline=True: API を叩かず、期限切れでもキャッシュを使う
                      (キャッシュが空なら RuntimeError)
        """
        if offline:
            if self._cache is None:
                raise RuntimeError(
                    "offline モードにはキャッシュが必要です。"
                    "settings.yaml で cache.enabled を有効にしてください。"
                )
            cached = self._cache.load_videos()
            if not cached:
                raise RuntimeError(
                    "キャッシュが空のため offline モードで実行できません。"
                    "クォータに余裕があるときに --refresh 付きで実行してください。"
                )
            return cached

        if self._cache is not None and not refresh and self._cache.is_fresh("videos"):
            cached = self._cache.load_videos()
            if cached:
                logger.info(f"Loaded {len(cached)} videos from cache.")
                return cached

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            # 1. Get the "uploads" playlist ID from the channel resource
            channels_response = service.channels().list(
                mine=True,
                part="contentDetails"
            ).execute()
            
            channel_items = channels_response.get("items", [])
            if not channel_items:
                logger.error("No channel found for authenticated user.")
                return []
                
            uploads_playlist_id = channel_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            
            # 2. Iterate through the uploads playlist
            videos = []
            seen_video_ids = set()
            next_page_token = None

            logger.info("Fetching all uploaded videos...")
            while True:
                pl_request = service.playlistItems().list(
                    playlistId=uploads_playlist_id,
                    part="snippet,contentDetails",
                    maxResults=50,
                    pageToken=next_page_token
                )
                pl_response = pl_request.execute()

                for item in pl_response.get("items", []):
                    video_id = item["contentDetails"]["videoId"]
                    # 件数が多い環境ではページング中 (数分かかる) に uploads
                    # プレイリストの内容が変化し、同じ動画が複数のページに
                    # 現れることがある (YouTube API の既知の挙動)。重複した
                    # まま返すと SnapshotCache.save_videos が UNIQUE 制約
                    # 違反でクラッシュするため、最初に見つかったものだけ残す。
                    if video_id in seen_video_ids:
                        continue
                    seen_video_ids.add(video_id)
                    videos.append({
                        "id": video_id,
                        "title": item["snippet"]["title"]
                    })

                next_page_token = pl_response.get("nextPageToken")
                if not next_page_token:
                    break
            
            # 3. Batch fetch privacy status (50件ずつ)
            if videos:
                video_ids = [v["id"] for v in videos]
                privacy_map = {}
                for i in range(0, len(video_ids), 50):
                    batch_ids = video_ids[i:i + 50]
                    vid_response = service.videos().list(
                        id=",".join(batch_ids),
                        part="status"
                    ).execute()
                    for item in vid_response.get("items", []):
                        privacy_map[item["id"]] = item["status"]["privacyStatus"]
                
                for v in videos:
                    v["privacy"] = privacy_map.get(v["id"], "unknown")
            
            if self._cache is not None:
                self._cache.save_videos(videos)
                self._cache.mark_complete("videos")

            logger.info(f"Found {len(videos)} uploaded videos.")
            return videos

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while fetching videos: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to fetch uploaded videos: {e}")
            return []
