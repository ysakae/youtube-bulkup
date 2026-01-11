import unittest
from unittest.mock import MagicMock, patch
from src.lib.video.manager import VideoManager
from googleapiclient.errors import HttpError

class TestVideoManager(unittest.TestCase):
    def setUp(self):
        self.mock_credentials = MagicMock()
        self.manager = VideoManager(self.mock_credentials)

    @patch("src.lib.video.manager.build")
    def test_update_privacy_status_success(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_videos = MagicMock()
        mock_service.videos.return_value = mock_videos
        
        mock_update = MagicMock()
        mock_videos.update.return_value = mock_update
        
        mock_execute = MagicMock()
        mock_update.execute.return_value = mock_execute

        # Execute
        result = self.manager.update_privacy_status("test_video_id", "unlisted")

        # Verify
        self.assertTrue(result)
        mock_videos.update.assert_called_with(
            part="status",
            body={
                "id": "test_video_id",
                "status": {"privacyStatus": "unlisted"}
            }
        )
        mock_update.execute.assert_called_once()

    @patch("src.lib.video.manager.build")
    def test_update_privacy_status_invalid_status(self, mock_build):
        result = self.manager.update_privacy_status("test_video_id", "invalid_status")
        self.assertFalse(result)
        mock_build.assert_not_called()

    @patch("src.lib.video.manager.build")
    def test_update_privacy_status_api_error(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.videos().update().execute.side_effect = HttpError(
            MagicMock(status=500), b"Error"
        )

        # Execute
        result = self.manager.update_privacy_status("test_video_id", "public")

        # Verify
        self.assertFalse(result)

    @patch("src.lib.video.manager.build")
    def test_update_metadata_success(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_videos = MagicMock()
        mock_service.videos.return_value = mock_videos
        
        # list() response
        mock_list = MagicMock()
        mock_videos.list.return_value = mock_list
        mock_list.execute.return_value = {
            "items": [{
                "snippet": {
                    "title": "Old Title",
                    "description": "Old Desc",
                    "tags": ["old"],
                    "categoryId": "22"
                }
            }]
        }
        
        # update() response
        mock_update = MagicMock()
        mock_videos.update.return_value = mock_update
        mock_update.execute.return_value = {}

        # Execute
        result = self.manager.update_metadata(
            "test_video_id",
            title="New Title",
            description="New Desc",
            tags=["new"],
            category_id="25"
        )

        # Verify
        self.assertTrue(result)
        mock_videos.update.assert_called_with(
            part="snippet",
            body={
                "id": "test_video_id",
                "snippet": {
                    "title": "New Title",
                    "description": "New Desc",
                    "tags": ["new"],
                    "categoryId": "25"
                }
            }
        )

    @patch("src.lib.video.manager.build")
    @patch("src.lib.video.manager.MediaFileUpload")
    def test_update_thumbnail_success(self, mock_media_file, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_thumbnails = MagicMock()
        mock_service.thumbnails.return_value = mock_thumbnails
        
        mock_set = MagicMock()
        mock_thumbnails.set.return_value = mock_set
        mock_set.execute.return_value = {}

        # Execute
        result = self.manager.update_thumbnail("vid123", "/path/to/image.jpg")

        # Verify
        self.assertTrue(result)
        mock_media_file.assert_called_with("/path/to/image.jpg")
        mock_thumbnails.set.assert_called_with(
            videoId="vid123",
            media_body=mock_media_file.return_value
        )
