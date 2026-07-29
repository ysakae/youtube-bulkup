import unittest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from src.lib.video.manager import VideoManager


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


class TestVideoManagerCacheIntegration(unittest.TestCase):
    """VideoManager の SnapshotCache 連携 (refresh/offline/quota) を検証する。

    tests/lib/video/test_playlist.py の TestPlaylistCacheIntegration と
    同じ書き方 (一時DBファイル + tearDown で後片付け) に揃えている。
    """

    def setUp(self):
        import tempfile

        from src.lib.data.snapshot import SnapshotCache

        self.mock_creds = MagicMock()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cache = SnapshotCache(db_path=self.tmp.name, ttl_hours=24)

    def tearDown(self):
        import os

        self.cache.close()
        for suffix in ["", "-wal", "-shm"]:
            path = self.tmp.name + suffix
            if os.path.exists(path):
                os.remove(path)

    @staticmethod
    def _channel_response():
        return {
            "items": [{
                "contentDetails": {
                    "relatedPlaylists": {"uploads": "PL_UPLOADS"}
                }
            }]
        }

    @patch("src.lib.video.manager.build")
    def test_videos_are_saved_to_cache(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.return_value = self._channel_response()
        mock_service.playlistItems().list().execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}, "snippet": {"title": "T1"}}],
            "nextPageToken": None,
        }
        mock_service.videos().list().execute.return_value = {
            "items": [{"id": "v1", "status": {"privacyStatus": "public"}}]
        }

        manager = VideoManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_uploaded_videos()

        self.assertEqual(len(result), 1)
        self.assertEqual(
            self.cache.load_videos(), [{"id": "v1", "title": "T1", "privacy": "public"}]
        )
        self.assertTrue(self.cache.is_fresh("videos"))

    @patch("src.lib.video.manager.build")
    def test_second_call_uses_cache_without_api(self, mock_build):
        self.cache.save_videos([{"id": "v1", "title": "T1", "privacy": "public"}])
        self.cache.mark_complete("videos")

        manager = VideoManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_uploaded_videos()

        self.assertEqual(result, [{"id": "v1", "title": "T1", "privacy": "public"}])
        mock_build.assert_not_called()

    @patch("src.lib.video.manager.build")
    def test_refresh_bypasses_cache(self, mock_build):
        self.cache.save_videos([{"id": "old", "title": "旧", "privacy": "public"}])
        self.cache.mark_complete("videos")

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.return_value = self._channel_response()
        mock_service.playlistItems().list().execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v2"}, "snippet": {"title": "T2"}}],
            "nextPageToken": None,
        }
        mock_service.videos().list().execute.return_value = {
            "items": [{"id": "v2", "status": {"privacyStatus": "private"}}]
        }

        manager = VideoManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_uploaded_videos(refresh=True)

        self.assertEqual(result, [{"id": "v2", "title": "T2", "privacy": "private"}])

    @patch("src.lib.video.manager.build")
    def test_offline_uses_stale_cache_without_api(self, mock_build):
        """TTL 切れでも offline ならキャッシュを使う (quota 枯渇中の調査用)。"""
        self.cache.save_videos([{"id": "v1", "title": "T1", "privacy": "public"}])
        self.cache.mark_complete("videos")
        self.cache.ttl_seconds = 0

        manager = VideoManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_uploaded_videos(offline=True)

        self.assertEqual(result, [{"id": "v1", "title": "T1", "privacy": "public"}])
        mock_build.assert_not_called()

    @patch("src.lib.video.manager.build")
    def test_offline_without_cache_raises(self, mock_build):
        manager = VideoManager(self.mock_creds, cache=None)
        with self.assertRaises(RuntimeError):
            manager.get_all_uploaded_videos(offline=True)
        mock_build.assert_not_called()

    @patch("src.lib.video.manager.build")
    def test_offline_with_empty_cache_raises(self, mock_build):
        manager = VideoManager(self.mock_creds, cache=self.cache)
        with self.assertRaises(RuntimeError):
            manager.get_all_uploaded_videos(offline=True)
        mock_build.assert_not_called()

    @staticmethod
    def _quota_error():
        import httplib2

        resp = httplib2.Response({"status": 403})
        resp.status = 403
        return HttpError(resp, b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}')

    @patch("src.lib.video.manager.build")
    def test_quota_error_raises_and_does_not_mark_complete(self, mock_build):
        """走査中にクォータが尽きたら QuotaExceededError を送出し、

        キャッシュを「完了」と記録しない (部分的な取得結果を新鮮な
        キャッシュと誤認させないため)。
        """
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.channels().list().execute.side_effect = self._quota_error()

        manager = VideoManager(self.mock_creds, cache=self.cache)

        with self.assertRaises(QuotaExceededError):
            manager.get_all_uploaded_videos()

        self.assertFalse(self.cache.is_fresh("videos"))
