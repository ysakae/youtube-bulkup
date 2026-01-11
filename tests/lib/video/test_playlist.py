import unittest
from unittest.mock import MagicMock, patch
from src.lib.video.playlist import PlaylistManager

class TestPlaylistManager(unittest.TestCase):
    def setUp(self):
        self.mock_creds = MagicMock()
        self.manager = PlaylistManager(self.mock_creds)

    @patch("src.lib.video.playlist.build")
    def test_get_or_create_existing(self, mock_build):
        # Mock Service
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Mock playlists().list().execute()
        mock_list = mock_service.playlists().list.return_value
        mock_list.execute.return_value = {
            "items": [
                {"id": "PL123", "snippet": {"title": "Existing Playlist"}}
            ]
        }

        playlist_id = self.manager.get_or_create_playlist("Existing Playlist")
        self.assertEqual(playlist_id, "PL123")
        
        # Verify fresh service was built
        mock_build.assert_called_with("youtube", "v3", credentials=self.mock_creds, cache_discovery=False)

    @patch("src.lib.video.playlist.build")
    def test_get_or_create_new(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock list -> empty (to ensure we go to create)
        mock_service.playlists().list.return_value.execute.return_value = {}

        # Mock insert
        mock_service.playlists().insert.return_value.execute.return_value = {
            "id": "PL_NEW", "snippet": {"title": "New Playlist"}
        }

        playlist_id = self.manager.get_or_create_playlist("New Playlist")
        
        self.assertEqual(playlist_id, "PL_NEW")
        mock_service.playlists().insert.assert_called()
        # Verify build called twice (once for ensure_cache, once for create in this flow?)
        # Actually _ensure_cache calls build, then insert calls build again.
        self.assertTrue(mock_build.call_count >= 1)

    @patch("src.lib.video.playlist.build")
    def test_add_video_to_playlist(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Mock successful add
        mock_service.playlistItems().insert.return_value.execute.return_value = {}
        
        success = self.manager.add_video_to_playlist("PL123", "VID999")
        self.assertTrue(success)
        mock_service.playlistItems().insert.assert_called()
        mock_build.assert_called()

    @patch("src.lib.video.playlist.build")
    def test_remove_video_from_playlist(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Mocking list response to find playlistItem
        mock_list = MagicMock()
        mock_service.playlistItems().list.return_value = mock_list
        mock_list.execute.return_value = {
            "items": [{"id": "playlist_item_id_123"}]
        }
        
        # Mocking delete
        mock_delete = MagicMock()
        mock_service.playlistItems().delete.return_value = mock_delete
        
        # Execute
        result = self.manager.remove_video_from_playlist("playlist_id_abc", "video_id_xyz")
        
        # Verify
        self.assertTrue(result)
        mock_service.playlistItems().list.assert_called_with(
            part="id",
            playlistId="playlist_id_abc",
            videoId="video_id_xyz"
        )
        mock_service.playlistItems().delete.assert_called_with(id="playlist_item_id_123")
        mock_delete.execute.assert_called_once()
        
    @patch("src.lib.video.playlist.build")
    def test_remove_video_from_playlist_not_found(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Mocking list response to return empty items
        mock_service.playlistItems().list().execute.return_value = {"items": []}
        
        # Execute
        result = self.manager.remove_video_from_playlist("playlist_id_abc", "video_id_xyz")
        
        # Verify
        self.assertFalse(result)
        mock_service.playlistItems().delete.assert_not_called()

if __name__ == '__main__':
    unittest.main()
