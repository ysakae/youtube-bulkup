import logging
from typing import Any, Dict, List, Tuple

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from ..lib.data.history import HistoryManager

logger = logging.getLogger("youtube_up")

class SyncManager:
    def __init__(self, service: Resource, history_manager: HistoryManager):
        self.service = service
        self.history = history_manager

    def fetch_all_remote_videos(self) -> List[Dict[str, Any]]:
        """
        Fetch all uploaded videos from the authenticated user's channel.
        Returns a list of video objects (snippet resource).
        """
        try:
            # 1. Get Uploads Playlist ID
            channels_response = self.service.channels().list(
                mine=True,
                part="contentDetails"
            ).execute()

            if not channels_response.get("items"):
                logger.warning("No channel found for authenticated user.")
                return []

            uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # 2. Fetch all items from the playlist
            videos = []
            next_page_token = None

            while True:
                pl_request = self.service.playlistItems().list(
                    playlistId=uploads_playlist_id,
                    part="snippet,contentDetails",
                    maxResults=50,
                    pageToken=next_page_token
                )
                pl_response = pl_request.execute()

                videos.extend(pl_response.get("items", []))

                next_page_token = pl_response.get("nextPageToken")
                if not next_page_token:
                    break

            return videos

        except HttpError as e:
            logger.error(f"Failed to fetch remote videos: {e}")
            raise

    def compare(self) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Compare local history with remote videos.
        Returns:
            (in_sync, missing_in_local, missing_in_remote)
            Each list contains dicts with video details.
        """
        remote_videos = self.fetch_all_remote_videos()
        # Map remote video_id -> video_object
        remote_map = {v["contentDetails"]["videoId"]: v for v in remote_videos}
        
        local_records = self.history.get_all_records()
        # Filter only successful uploads that have a video_id
        local_map = {r["video_id"]: r for r in local_records if r.get("status") == "success" and r.get("video_id")}

        remote_ids = set(remote_map.keys())
        local_ids = set(local_map.keys())

        # 1. In Sync (Both exist)
        common_ids = remote_ids.intersection(local_ids)
        in_sync = []
        for vid in common_ids:
            in_sync.append({
                "video_id": vid,
                "remote_title": remote_map[vid]["snippet"]["title"],
                "local_path": local_map[vid].get("file_path", "N/A"),
                "status": "OK"
            })

        # 2. Missing in Local (Exists in Remote only)
        missing_local_ids = remote_ids - local_ids
        missing_in_local = []
        for vid in missing_local_ids:
            missing_in_local.append({
                "video_id": vid,
                "remote_title": remote_map[vid]["snippet"]["title"],
                "local_path": "N/A",
                "status": "MISSING_LOCAL"
            })

        # 3. Missing in Remote (Exists in Local only)
        missing_remote_ids = local_ids - remote_ids
        missing_in_remote = []
        for vid in missing_remote_ids:
            missing_in_remote.append({
                "video_id": vid,
                "remote_title": "N/A",
                "local_path": local_map[vid].get("file_path", "N/A"),
                "status": "MISSING_REMOTE"
            })

        return in_sync, missing_in_local, missing_in_remote

    def fix_missing_remote(self, missing_remote_items: list) -> tuple:
        """
        ローカルにだけあるレコード（リモートで削除済み）を履歴から削除する。
        Returns: (deleted_count, failed_count)
        """
        deleted = 0
        failed = 0

        for item in missing_remote_items:
            video_id = item["video_id"]
            if self.history.delete_record_by_video_id(video_id):
                logger.info(f"Deleted local record for {video_id}")
                deleted += 1
            else:
                logger.warning(f"Failed to delete local record for {video_id}")
                failed += 1

        return deleted, failed
