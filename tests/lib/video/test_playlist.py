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

    @patch("src.lib.video.playlist.build")
    def test_rename_playlist_success(self, mock_build):
        # Setup mocks
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_playlists = MagicMock()
        mock_service.playlists.return_value = mock_playlists
        
        # list() response
        mock_list = MagicMock()
        mock_playlists.list.return_value = mock_list
        mock_list.execute.return_value = {
            "items": [{
                "id": "PL123",
                "snippet": {
                    "title": "Old Name",
                    "description": "Desc"
                }
            }]
        }
        
        # update() response
        mock_update = MagicMock()
        mock_playlists.update.return_value = mock_update
        mock_update.execute.return_value = {}

        # Pre-populate cache to test lookup
        self.manager._playlist_cache["Old Name"] = "PL123"

        # Execute
        result = self.manager.rename_playlist("Old Name", "New Name")

        # Verify
        self.assertTrue(result)
        mock_playlists.update.assert_called_with(
            part="snippet",
            body={
                "id": "PL123",
                "snippet": {
                    "title": "New Name",
                    "description": "Desc"
                }
            }
        )
        # Check cache update
        self.assertIn("New Name", self.manager._playlist_cache)
        self.assertNotIn("Old Name", self.manager._playlist_cache)

    @patch("src.lib.video.playlist.build")
    def test_ensure_cache_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Simulate HttpError
        resp = httplib2.Response({'status': '500'})
        mock_service.playlists().list().execute.side_effect = HttpError(resp, b"Error")
        
        # Should not raise exception
        self.manager._ensure_cache()
        self.assertFalse(self.manager._initialized)

    @patch("src.lib.video.playlist.build")
    def test_get_or_create_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_service.playlists().list().execute.return_value = {}
        
        resp = httplib2.Response({'status': '400'})
        mock_service.playlists().insert().execute.side_effect = HttpError(resp, b"Failed to create")
        
        playlist_id = self.manager.get_or_create_playlist("New Playlist")
        self.assertIsNone(playlist_id)

    @patch("src.lib.video.playlist.build")
    def test_add_video_to_playlist_already_in(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '400'})
        mock_service.playlistItems().insert().execute.side_effect = HttpError(resp, b"videoAlreadyInPlaylist")
        
        success = self.manager.add_video_to_playlist("PL123", "VID999")
        self.assertTrue(success)

    @patch("src.lib.video.playlist.build")
    def test_add_video_to_playlist_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlistItems().insert().execute.side_effect = HttpError(resp, b"Internal Server Error")
        
        success = self.manager.add_video_to_playlist("PL123", "VID999")
        self.assertFalse(success)

    @patch("src.lib.video.playlist.build")
    def test_remove_video_from_playlist_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlistItems().list().execute.side_effect = HttpError(resp, b"Internal Server Error")
        
        success = self.manager.remove_video_from_playlist("playlist_id_abc", "video_id_xyz")
        self.assertFalse(success)

    @patch.object(PlaylistManager, "get_or_create_playlist")
    @patch("src.lib.video.playlist.build")
    def test_get_video_ids_from_playlist(self, mock_build, mock_get_playlist):
        mock_get_playlist.return_value = "PL123"
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_list = MagicMock()
        mock_service.playlistItems().list.return_value = mock_list
        mock_list.execute.return_value = {
            "items": [
                {"contentDetails": {"videoId": "VID1"}},
                {"contentDetails": {"videoId": "VID2"}}
            ]
        }
        mock_service.playlistItems().list_next.return_value = None
        
        video_ids = self.manager.get_video_ids_from_playlist("My Playlist")
        
        self.assertEqual(video_ids, ["VID1", "VID2"])
        
    @patch.object(PlaylistManager, "get_or_create_playlist")
    def test_get_video_ids_from_playlist_not_found(self, mock_get_playlist):
        mock_get_playlist.return_value = None
        video_ids = self.manager.get_video_ids_from_playlist("Not Found")
        self.assertEqual(video_ids, [])

    @patch.object(PlaylistManager, "get_or_create_playlist")
    @patch("src.lib.video.playlist.build")
    def test_get_video_ids_from_playlist_http_error(self, mock_build, mock_get_playlist):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_get_playlist.return_value = "PL123"
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlistItems().list().execute.side_effect = HttpError(resp, b"Error")
        
        video_ids = self.manager.get_video_ids_from_playlist("My Playlist")
        self.assertEqual(video_ids, [])

    def test_find_playlist_id(self):
        self.manager._playlist_cache = {
            "Playlist A": "PL123",
            "Playlist B": "PL456"
        }
        self.manager._initialized = True
        
        # Test by title
        self.assertEqual(self.manager.find_playlist_id("Playlist A"), "PL123")
        
        # Test by ID
        self.assertEqual(self.manager.find_playlist_id("PL456"), "PL456")
        
        # Not found
        self.assertIsNone(self.manager.find_playlist_id("Unknown"))

    @patch("src.lib.video.playlist.build")
    def test_rename_playlist_not_found(self, mock_build):
        self.manager._playlist_cache = {}
        self.manager._initialized = True
        
        # Should fail for non-PL string
        self.assertFalse(self.manager.rename_playlist("Unknown Title", "New Name"))
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Try raw PL string but no items return from API
        mock_service.playlists().list().execute.return_value = {"items": []}
        
        self.assertFalse(self.manager.rename_playlist("PLUnknown", "New Name"))

    @patch("src.lib.video.playlist.build")
    def test_rename_playlist_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        self.manager._playlist_cache = {"Title": "PL123"}
        self.manager._initialized = True
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlists().list().execute.side_effect = HttpError(resp, b"Error")
        
        self.assertFalse(self.manager.rename_playlist("Title", "New Name"))

    @patch("src.lib.video.playlist.build")
    def test_list_playlists(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_service.playlists().list().execute.return_value = {
            "items": [
                {
                    "id": "PL1", 
                    "snippet": {"title": "Play 1"}, 
                    "contentDetails": {"itemCount": 5},
                    "status": {"privacyStatus": "private"}
                },
                {
                    "id": "PL2", 
                    "snippet": {"title": "Play 2"}, 
                    "contentDetails": {"itemCount": 2},
                    "status": {"privacyStatus": "public"}
                }
            ],
            "nextPageToken": None
        }
        
        playlists = self.manager.list_playlists()
        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0]["id"], "PL1")
        self.assertEqual(playlists[0]["item_count"], 5)
        self.assertEqual(playlists[1]["privacy"], "public")

    @patch("src.lib.video.playlist.build")
    def test_list_playlists_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlists().list().execute.side_effect = HttpError(resp, b"Error")
        
        playlists = self.manager.list_playlists()
        self.assertEqual(playlists, [])

    @patch.object(PlaylistManager, "find_playlist_id")
    @patch("src.lib.video.playlist.build")
    def test_list_playlist_items(self, mock_build, mock_find_id):
        mock_find_id.return_value = "PL123"
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        mock_service.playlistItems().list().execute.return_value = {
            "items": [
                {
                    "snippet": {"title": "Vid 1", "position": 0},
                    "contentDetails": {"videoId": "VID1"}
                }
            ],
            "nextPageToken": None
        }
        
        items = self.manager.list_playlist_items("MyList")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["video_id"], "VID1")
        self.assertEqual(items[0]["title"], "Vid 1")
        self.assertEqual(items[0]["position"], 0)

    @patch.object(PlaylistManager, "find_playlist_id")
    def test_list_playlist_items_not_found(self, mock_find_id):
        mock_find_id.return_value = None
        items = self.manager.list_playlist_items("Unknown")
        self.assertEqual(items, [])

    @patch.object(PlaylistManager, "find_playlist_id")
    @patch("src.lib.video.playlist.build")
    def test_list_playlist_items_http_error(self, mock_build, mock_find_id):
        from googleapiclient.errors import HttpError
        import httplib2
        
        mock_find_id.return_value = "PL123"
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlistItems().list().execute.side_effect = HttpError(resp, b"Error")
        
        items = self.manager.list_playlist_items("MyList")
        self.assertEqual(items, [])
        
    @patch("src.lib.video.playlist.build")
    def test_get_all_playlists_map(self, mock_build):
        self.manager._playlist_cache = {
            "List1": "PL1",
            "List2": "PL2"
        }
        self.manager._initialized = True
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # We need mock execute sequences for multiple calls
        mock_execute = MagicMock()
        mock_service.playlistItems().list().execute = mock_execute
        
        # PL1 returns VID1, VID2. PL2 returns VID3
        mock_execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "VID1"}}, {"contentDetails": {"videoId": "VID2"}}]},
            {"items": [{"contentDetails": {"videoId": "VID3"}}]}
        ]
        
        mock_service.playlistItems().list_next.return_value = None
        
        playlist_map = self.manager.get_all_playlists_map()
        
        self.assertIn("PL1", playlist_map)
        self.assertIn("PL2", playlist_map)
        self.assertEqual(playlist_map["PL1"], {"VID1", "VID2"})
        self.assertEqual(playlist_map["PL2"], {"VID3"})

    @patch("src.lib.video.playlist.build")
    def test_get_all_playlists_map_http_error(self, mock_build):
        from googleapiclient.errors import HttpError
        import httplib2
        
        self.manager._playlist_cache = {"List1": "PL1"}
        self.manager._initialized = True
        
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        resp = httplib2.Response({'status': '500'})
        mock_service.playlistItems().list().execute.side_effect = HttpError(resp, b"Error")
        
        playlist_map = self.manager.get_all_playlists_map()
        self.assertEqual(playlist_map, {})

if __name__ == '__main__':
    unittest.main()
