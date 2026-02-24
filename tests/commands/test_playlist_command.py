import unittest
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from src.main import app

runner = CliRunner()

class TestPlaylistCommand(unittest.TestCase):

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_rename_playlist_success(self, MockPlaylistManager, mock_get_credentials):
         mock_creds = MagicMock()
         mock_get_credentials.return_value = mock_creds
         
         mock_pl_mgr = MockPlaylistManager.return_value
         mock_pl_mgr.rename_playlist.return_value = True
         
         result = runner.invoke(app, ["playlist", "rename", "Old Playlist", "New Playlist"])
         
         if result.exit_code != 0:
             print(result.output)

         self.assertEqual(result.exit_code, 0)
         mock_pl_mgr.rename_playlist.assert_called_with("Old Playlist", "New Playlist")

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_list_playlists(self, MockPlaylistManager, mock_get_credentials):
        """全プレイリスト一覧の表示テスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        mock_mgr.list_playlists.return_value = [
            {"id": "PL1", "title": "Test Playlist", "item_count": 5, "privacy": "private"},
            {"id": "PL2", "title": "Another", "item_count": 10, "privacy": "public"},
        ]

        result = runner.invoke(app, ["playlist", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Test Playlist", result.output)
        self.assertIn("Another", result.output)
        mock_mgr.list_playlists.assert_called_once()

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_list_playlist_items(self, MockPlaylistManager, mock_get_credentials):
        """特定プレイリスト内の動画一覧テスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        mock_mgr.list_playlist_items.return_value = [
            {"video_id": "vid1", "title": "Video One", "position": 0},
            {"video_id": "vid2", "title": "Video Two", "position": 1},
        ]

        result = runner.invoke(app, ["playlist", "list", "My Playlist"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Video One", result.output)
        self.assertIn("Video Two", result.output)
        mock_mgr.list_playlist_items.assert_called_once_with("My Playlist")

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_list_playlists_empty(self, MockPlaylistManager, mock_get_credentials):
        """プレイリストが0件の場合のテスト"""
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        mock_mgr.list_playlists.return_value = []

        result = runner.invoke(app, ["playlist", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No playlists found", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_add_video_success(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.get_or_create_playlist.return_value = "PL123"
        mock_mgr.add_video_to_playlist.return_value = True

        result = runner.invoke(app, ["playlist", "add", "VID1", "My Playlist", "--privacy", "public"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Successfully added VID1", result.output)
        mock_mgr.get_or_create_playlist.assert_called_once_with("My Playlist", "public")
        mock_mgr.add_video_to_playlist.assert_called_once_with("PL123", "VID1")

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_add_video_fail_create(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.get_or_create_playlist.return_value = None

        result = runner.invoke(app, ["playlist", "add", "VID1", "My Playlist"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to find or create playlist", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_add_video_fail_add(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.get_or_create_playlist.return_value = "PL123"
        mock_mgr.add_video_to_playlist.return_value = False

        result = runner.invoke(app, ["playlist", "add", "VID1", "My Playlist"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to add video to playlist", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_remove_video_success(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.find_playlist_id.return_value = "PL123"
        mock_mgr.remove_video_from_playlist.return_value = True

        result = runner.invoke(app, ["playlist", "remove", "VID1", "My Playlist"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Successfully removed VID1", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_remove_video_not_found(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.find_playlist_id.return_value = None

        result = runner.invoke(app, ["playlist", "remove", "VID1", "My Playlist"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Playlist not found", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_remove_video_fail(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        
        mock_mgr.find_playlist_id.return_value = "PL123"
        mock_mgr.remove_video_from_playlist.return_value = False

        result = runner.invoke(app, ["playlist", "remove", "VID1", "My Playlist"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to remove video", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_rename_playlist_fail(self, MockPlaylistManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_mgr = MockPlaylistManager.return_value
        mock_mgr.rename_playlist.return_value = False

        result = runner.invoke(app, ["playlist", "rename", "Old", "New"])
        
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to rename", result.output)

    @patch("src.commands.playlist.get_credentials", side_effect=Exception("API Error"))
    def test_auth_error(self, mock_get_credentials):
        result = runner.invoke(app, ["playlist", "list"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Auth Error: API Error", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_no_videos(self, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = []
        
        result = runner.invoke(app, ["playlist", "orphans"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No uploaded videos found", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_none_orphaned(self, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID1", "title": "Video 1"},
            {"id": "VID2", "title": "Video 2"}
        ]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {
            "PLA": {"VID1"},
            "PLB": {"VID2"}
        }

        result = runner.invoke(app, ["playlist", "orphans"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No orphan videos found", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_has_orphans(self, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID1", "title": "Video 1"},
            {"id": "VID2", "title": "Video 2"}
        ]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {
            "PLA": {"VID1"}
        }

        result = runner.invoke(app, ["playlist", "orphans"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Orphan Videos: 1", result.output)
        self.assertIn("- Video 2 (VID2)", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    @patch("src.commands.playlist.typer.confirm", return_value=True)
    def test_orphans_fix_yes(self, mock_confirm, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID1", "title": "Video 1"}
        ]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}
        mock_pl.get_or_create_playlist.return_value = "PLC"
        mock_pl.add_video_to_playlist.return_value = True

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = {"playlist_name": "HistoryPlaylist"}

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Assigning Orphans...", result.output)
        self.assertIn("Assigned Video 1 -> HistoryPlaylist", result.output)
        
        mock_pl.get_or_create_playlist.assert_called_once_with("HistoryPlaylist")
        mock_pl.add_video_to_playlist.assert_called_once_with("PLC", "VID1")

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    def test_orphans_fix_no_history_match(self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID1", "title": "Video 1"}
        ]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = None

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Skipping Video 1 (no history/playlist found)", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    def test_orphans_fix_from_filepath(self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID2", "title": "Video 2"}
        ]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}
        mock_pl.get_or_create_playlist.return_value = "PL_DIR"
        mock_pl.add_video_to_playlist.return_value = True

        mock_hist = MockHistoryMgr.return_value
        # No playlist_name, but has file_path
        mock_hist.get_record_by_video_id.return_value = {"file_path": "/some/dir/MyFolder/video.mp4"}

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Assigned Video 2 -> MyFolder", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.typer.confirm", return_value=False)
    def test_orphans_fix_abort(self, mock_confirm, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Vid 1"}]
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        result = runner.invoke(app, ["playlist", "orphans", "--fix"])
        self.assertNotEqual(result.exit_code, 0) # Aborted

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    def test_orphans_fix_exception_in_path(self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Vid 1"}]
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        mock_hist = MockHistoryMgr.return_value
        # raise exception in Path(record["file_path"]).parent.name
        # we can mock Path or just pass something that causes an exception when passed to Path
        mock_hist.get_record_by_video_id.return_value = {"file_path": 12345} # type error expected in Path

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Skipping Vid 1 (no history/playlist found)", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    def test_orphans_fix_add_fail(self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Vid 1"}]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}
        mock_pl.get_or_create_playlist.return_value = "PL1"
        # simulate failure to add
        mock_pl.add_video_to_playlist.return_value = False

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = {"playlist_name": "MyList"}

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Failed to assign Vid 1 -> MyList", result.output)

    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.lib.data.history.HistoryManager")
    def test_orphans_fix_create_fail(self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Vid 1"}]
        
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}
        # simulate failure to create playlist
        mock_pl.get_or_create_playlist.return_value = None

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = {"playlist_name": "MyList"}

        result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Failed to get/create playlist MyList for Vid 1", result.output)

if __name__ == "__main__":
    unittest.main()
