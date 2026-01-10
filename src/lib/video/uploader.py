import asyncio
import logging
import socket
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..core.config import config

logger = logging.getLogger("youtube_up")


def should_retry_exception(exception: BaseException) -> bool:
    """Check if the exception is worth retrying."""
    if isinstance(exception, (socket.error, socket.timeout)):
        return True
    if isinstance(exception, HttpError):
        # Retry 5xx server errors, 429 Too Many Requests, and 408 Request Timeout
        if exception.resp.status in [408, 429, 500, 502, 503, 504]:
            return True
        return False
    return False


class VideoUploader:
    def __init__(self, credentials):
        self.credentials = credentials
        # self.service is no longer stored here to ensure thread safety

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(config.upload.retry_count),
        retry=retry_if_exception(should_retry_exception),
    )
    async def upload_video(
        self,
        file_path: Path,
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[str]:
        """
        Uploads a single video with retry logic and progress tracking.
        Returns Video ID on success, None on failure.
        """
        logger.info(f"Preparing upload for {file_path.name}...")

        body = {
            "snippet": {
                "title": metadata.get("title", file_path.stem),
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "categoryId": metadata.get("categoryId", "22"),  # 22 is People & Blogs
            },
            "status": {
                "privacyStatus": metadata.get(
                    "privacy_status", config.upload.privacy_status
                ),
                "selfDeclaredMadeForKids": False,
            },
            "recordingDetails": metadata.get("recordingDetails", {}),
        }

        # Wrap MediaFileUpload to allow blocking IO in thread if needed,
        # but here we initialize it directly as it just prepares the request.
        media = MediaFileUpload(
            str(file_path), chunksize=config.upload.chunk_size, resumable=True
        )

        # Build a fresh service instance for this thread
        # This is critical for thread safety with httplib2
        service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

        request = service.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media
        )

        video_id = await self._execute_upload(request, file_path, progress_callback)
        return video_id

    async def _execute_upload(self, request, file_path, progress_callback):
        """
        Executes the upload in a loop to handle chunks and progress.
        Runs blocking next_chunk() in a separate thread to keep asyncio event loop responsive.
        """
        response = None
        while response is None:
            status, response = await asyncio.to_thread(request.next_chunk)

            if status:
                # progress = int(status.progress() * 100)
                if progress_callback:
                    progress_callback(status.resumable_progress, status.total_size)
                # logger.debug(f"Uploaded {progress}% of {file_path.name}")

        if response and "id" in response:
            logger.info(
                f"Upload complete for {file_path.name}. Video ID: {response['id']}"
            )
            return response["id"]
        else:
            logger.error(
                f"Upload failed unexpectedly for {file_path.name}. Response: {response}"
            )
            return None

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(config.upload.retry_count),
        retry=retry_if_exception(should_retry_exception),
    )
    async def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """
        Uploads a custom thumbnail for a video.
        """
        logger.info(f"Uploading thumbnail for {video_id} from {thumbnail_path.name}...")
        
        service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
        
        try:
            await asyncio.to_thread(
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path))
                ).execute
            )
            logger.info(f"Thumbnail uploaded successfully for {video_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload thumbnail for {video_id}: {e}")
            raise e
