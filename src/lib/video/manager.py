import logging
from typing import Optional, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("youtube_up")


class VideoManager:
    """
    Manages general YouTube Video interactions (metadata, settings, deletion).
    """

    def __init__(self, credentials):
        self.credentials = credentials

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
