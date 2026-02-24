import unittest
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from src.main import app

runner = CliRunner()

class TestVideoCommand(unittest.TestCase):
    
    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_privacy_bulk_success(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        # Setup
        mock_creds = MagicMock()
        mock_get_credentials.return_value = mock_creds
        
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_privacy_status.return_value = True
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = ["vid1", "vid2"]
        
        # Execute
        result = runner.invoke(app, ["video", "update-privacy", "all", "unlisted", "--playlist", "MyPlaylist"])
        
        # Verify
        if result.exit_code != 0:
            print(result.output)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Bulk Update Complete", result.stdout)
        self.assertIn("vid1", result.stdout)
        
        mock_pl_mgr.get_video_ids_from_playlist.assert_called_with("MyPlaylist")
        self.assertEqual(mock_idx_mgr.update_privacy_status.call_count, 2)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_privacy_single_success(self, MockVideoManager, mock_get_credentials):
        mock_creds = MagicMock()
        mock_get_credentials.return_value = mock_creds
        
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_privacy_status.return_value = True
        
        result = runner.invoke(app, ["video", "update-privacy", "VID123", "public"])
        
        if result.exit_code != 0:
            print(result.output)
        self.assertEqual(result.exit_code, 0)
        mock_idx_mgr.update_privacy_status.assert_called_with("VID123", "public")

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_metadata_single_success(self, MockVideoManager, mock_get_credentials):
         mock_creds = MagicMock()
         mock_get_credentials.return_value = mock_creds
         
         mock_idx_mgr = MockVideoManager.return_value
         mock_idx_mgr.update_metadata.return_value = True
         
         result = runner.invoke(app, ["video", "update-meta", "VID123", "--title", "New Title"])
         
         if result.exit_code != 0:
            print(result.output)
         self.assertEqual(result.exit_code, 0)
         mock_idx_mgr.update_metadata.assert_called_with(
             "VID123", title="New Title", description=None, tags=None, category_id=None
         )

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_thumbnail_success(self, MockVideoManager, mock_get_credentials):
         mock_creds = MagicMock()
         mock_get_credentials.return_value = mock_creds
         
         mock_idx_mgr = MockVideoManager.return_value
         mock_idx_mgr.update_thumbnail.return_value = True
         
         result = runner.invoke(app, ["video", "update-thumbnail", "VID123", "./thumb.jpg"])
         
         self.assertEqual(result.exit_code, 0)
         mock_idx_mgr.update_thumbnail.assert_called_with("VID123", "./thumb.jpg")

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_delete_video_success(self, MockVideoManager, mock_get_credentials):
         mock_creds = MagicMock()
         mock_get_credentials.return_value = mock_creds
         
         mock_idx_mgr = MockVideoManager.return_value
         mock_idx_mgr.delete_video.return_value = True
         
         # Test with -y option to skip prompt
         result = runner.invoke(app, ["video", "delete-video", "VID123", "-y"])
         
         self.assertEqual(result.exit_code, 0)
         mock_idx_mgr.delete_video.assert_called_with("VID123")

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_list_videos(self, MockVideoManager, mock_get_credentials):
        """video list の正常系テスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockVideoManager.return_value
        mock_mgr.get_all_uploaded_videos.return_value = [
            {"id": "vid1", "title": "Video One", "privacy": "private"},
            {"id": "vid2", "title": "Video Two", "privacy": "public"},
        ]

        result = runner.invoke(app, ["video", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Video One", result.output)
        self.assertIn("Video Two", result.output)
        mock_mgr.get_all_uploaded_videos.assert_called_once()

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_list_videos_with_status_filter(self, MockVideoManager, mock_get_credentials):
        """video list --status フィルタテスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockVideoManager.return_value
        mock_mgr.get_all_uploaded_videos.return_value = [
            {"id": "vid1", "title": "Private Video", "privacy": "private"},
            {"id": "vid2", "title": "Public Video", "privacy": "public"},
        ]

        result = runner.invoke(app, ["video", "list", "--status", "public"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Public Video", result.output)
        # private のものは表示されないはず（フィルタ済み）

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_list_videos_empty(self, MockVideoManager, mock_get_credentials):
        """動画0件の場合のテスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockVideoManager.return_value
        mock_mgr.get_all_uploaded_videos.return_value = []

        result = runner.invoke(app, ["video", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No uploaded videos found", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_list_videos_unlisted_display(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockVideoManager.return_value
        mock_mgr.get_all_uploaded_videos.return_value = [
            {"id": "vid_unlisted", "title": "Unlisted Video", "privacy": "unlisted"}
        ]
        
        result = runner.invoke(app, ["video", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Unlisted Video", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_privacy_bulk_target_not_all(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_privacy_status.return_value = True
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = ["vid1"]
        
        # Test warning when target is not 'all'
        result = runner.invoke(app, ["video", "update-privacy", "VID123", "unlisted", "--playlist", "MyList"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Warning: 'target' argument is ignored", result.output)
        mock_idx_mgr.update_privacy_status.assert_called_with("vid1", "unlisted")

    @patch("src.commands.video.get_credentials", side_effect=Exception("API Error"))
    def test_auth_error_video_manager(self, mock_get_credentials):
        result = runner.invoke(app, ["video", "list"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Auth Error: API Error", result.output)
        
    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.PlaylistManager", side_effect=Exception("PL Auth Error"))
    @patch("src.commands.video.VideoManager")
    def test_auth_error_playlist_manager(self, MockVideoManager, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        # Mocking VideoManager to pass the first auth check
        
        result = runner.invoke(app, ["video", "update-privacy", "all", "public", "--playlist", "MyList"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Auth Error: PL Auth Error", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_list_videos_status_not_found(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockVideoManager.return_value
        mock_mgr.get_all_uploaded_videos.return_value = [
            {"id": "vid1", "title": "Vid", "privacy": "private"}
        ]
        
        result = runner.invoke(app, ["video", "list", "--status", "public"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No videos found with status: public", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_privacy_bulk_no_videos(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = []
        
        result = runner.invoke(app, ["video", "update-privacy", "all", "unlisted", "--playlist", "EmptyList"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("No videos found in playlist EmptyList", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_privacy_bulk_partial_fail(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_idx_mgr = MockVideoManager.return_value
        # Fail on second video
        mock_idx_mgr.update_privacy_status.side_effect = [True, False]
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = ["vid1", "vid2"]
        
        result = runner.invoke(app, ["video", "update-privacy", "all", "unlisted", "--playlist", "MyList"])
        
        # Should exit 1 because of partial failure
        self.assertEqual(result.exit_code, 1)
        self.assertIn("1 success, 1 failed", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_privacy_single_fail(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_privacy_status.return_value = False
        
        result = runner.invoke(app, ["video", "update-privacy", "VID1", "public"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to update privacy status", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_meta_bulk_success(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_metadata.return_value = True
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = ["vid1"]
        
        # Note the target is "VID123" not "all", should trigger a warning but proceed
        result = runner.invoke(app, ["video", "update-meta", "VID123", "--title", "New Title", "--playlist", "MyList"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("1 success, 0 failed", result.output)
        self.assertIn("Warning: 'target' argument is ignored", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_meta_bulk_no_videos(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = []
        
        result = runner.invoke(app, ["video", "update-meta", "all", "--title", "New Title", "--playlist", "EmptyList"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("No videos found in playlist", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.PlaylistManager")
    def test_update_meta_bulk_partial_fail(self, MockPlaylistManager, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_metadata.side_effect = [False] # fail
        
        mock_pl_mgr = MockPlaylistManager.return_value
        mock_pl_mgr.get_video_ids_from_playlist.return_value = ["vid1"]
        
        result = runner.invoke(app, ["video", "update-meta", "all", "--title", "New Title", "--playlist", "MyList"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("0 success, 1 failed", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_meta_single_fail(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_metadata.return_value = False
        
        result = runner.invoke(app, ["video", "update-meta", "VID1", "--title", "New"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to update metadata", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_update_thumbnail_fail(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.update_thumbnail.return_value = False
        
        result = runner.invoke(app, ["video", "update-thumbnail", "VID1", "./thumb.jpg"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to update thumbnail", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    @patch("src.commands.video.typer.confirm", return_value=False)
    def test_delete_video_abort(self, mock_confirm, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        result = runner.invoke(app, ["video", "delete-video", "VID1"])
        
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Aborted", result.output)

    @patch("src.commands.video.get_credentials")
    @patch("src.commands.video.VideoManager")
    def test_delete_video_fail(self, MockVideoManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_idx_mgr = MockVideoManager.return_value
        mock_idx_mgr.delete_video.return_value = False
        
        result = runner.invoke(app, ["video", "delete-video", "VID1", "-y"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to delete video", result.output)

if __name__ == "__main__":
    unittest.main()
