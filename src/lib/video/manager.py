import logging
from typing import Optional, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
