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

if __name__ == "__main__":
    unittest.main()
