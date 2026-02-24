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

    @patch("src.lib.video.manager.build")
    def test_delete_video_success(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_videos = MagicMock()
        mock_service.videos.return_value = mock_videos
        
        mock_delete = MagicMock()
        mock_videos.delete.return_value = mock_delete
        mock_delete.execute.return_value = {}

        result = self.manager.delete_video("vid123")

        # Verify
        self.assertTrue(result)
        mock_videos.delete.assert_called_with(id="vid123")

    @patch("src.lib.video.manager.build")
    def test_update_metadata_not_found(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.videos().list().execute.return_value = {"items": []}

        result = self.manager.update_metadata("vid123", title="New")
        self.assertFalse(result)

    @patch("src.lib.video.manager.build")
    def test_update_metadata_http_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.videos().list().execute.side_effect = HttpError(
            MagicMock(status=500), b"Error"
        )

        result = self.manager.update_metadata("vid123", title="New")
        self.assertFalse(result)

    @patch("src.lib.video.manager.build")
    @patch("src.lib.video.manager.MediaFileUpload")
    def test_update_thumbnail_http_error(self, mock_media_file, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.thumbnails().set().execute.side_effect = HttpError(
            MagicMock(status=500), b"Error"
        )

        result = self.manager.update_thumbnail("vid123", "dummy_path.jpg")
        self.assertFalse(result)

    @patch("src.lib.video.manager.build")
    def test_delete_video_http_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.videos().delete().execute.side_effect = HttpError(
            MagicMock(status=500), b"Error"
        )

        result = self.manager.delete_video("vid123")
        self.assertFalse(result)

    @patch("src.lib.video.manager.build")
    def test_get_all_uploaded_videos_success(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # 1. Mock channel list
        mock_service.channels().list().execute.return_value = {
            "items": [{
                "contentDetails": {
                    "relatedPlaylists": {"uploads": "PL_UPLOADS"}
                }
            }]
        }

        # 2. Mock playlistItems list
        mock_execute = MagicMock()
        mock_service.playlistItems().list().execute = mock_execute
        
        # Paginated response
        mock_execute.side_effect = [
            {
                "items": [{"contentDetails": {"videoId": "VID1"}, "snippet": {"title": "Title 1"}}],
                "nextPageToken": "token"
            },
            {
                "items": [{"contentDetails": {"videoId": "VID2"}, "snippet": {"title": "Title 2"}}],
                "nextPageToken": None
            }
        ]

        # 3. Mock videos update for privacy status
        mock_service.videos().list().execute.return_value = {
            "items": [
                {"id": "VID1", "status": {"privacyStatus": "public"}},
                {"id": "VID2", "status": {"privacyStatus": "private"}}
            ]
        }

        # Execute
        videos = self.manager.get_all_uploaded_videos()

        # Verify
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0]["id"], "VID1")
        self.assertEqual(videos[0]["title"], "Title 1")
        self.assertEqual(videos[0]["privacy"], "public")
        self.assertEqual(videos[1]["id"], "VID2")
        self.assertEqual(videos[1]["privacy"], "private")

    @patch("src.lib.video.manager.build")
    def test_get_all_uploaded_videos_no_channel(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.return_value = {"items": []}

        videos = self.manager.get_all_uploaded_videos()
        self.assertEqual(videos, [])

    @patch("src.lib.video.manager.build")
    def test_get_all_uploaded_videos_http_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.side_effect = HttpError(
            MagicMock(status=500), b"Error"
        )

        videos = self.manager.get_all_uploaded_videos()
        self.assertEqual(videos, [])
