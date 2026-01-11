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
