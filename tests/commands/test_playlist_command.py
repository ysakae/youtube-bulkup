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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_no_videos(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = []

        result = runner.invoke(app, ["playlist", "orphans"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No uploaded videos found", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_none_orphaned(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_has_orphans(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
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

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = None

        result = runner.invoke(app, ["playlist", "orphans"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Orphan Videos: 1", result.output)
        self.assertIn("- Video 2 (VID2)", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.typer.confirm", return_value=True)
    def test_orphans_fix_yes(
        self, mock_confirm, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_no_history_match(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_from_filepath(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.typer.confirm", return_value=False)
    def test_orphans_fix_abort(
        self, mock_confirm, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Vid 1"}]
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.return_value = {"playlist_name": "MyList"}

        result = runner.invoke(app, ["playlist", "orphans", "--fix"])
        self.assertNotEqual(result.exit_code, 0) # Aborted

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_exception_in_path(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_add_fail(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_create_fail(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
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

class TestOrphansQuotaControl:
    """orphans の予算制・中断・進捗記録。"""

    def test_default_max_items_uses_budget(self, monkeypatch):
        from src.commands import playlist as playlist_cmd

        history = MagicMock()
        history.get_all_records.return_value = []

        # pydantic の PrivateAttr に依存しないよう、メソッドごと差し替える
        # pydantic v2 の BaseModel はインスタンスへの任意属性代入を許さないため、
        # クラス側のメソッドを差し替える (config はインスタンス)
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 1000)

        # 予算 9000 / 50 = 180 件
        assert playlist_cmd._default_max_items(history) == 180

    def test_default_max_items_subtracts_today_uploads(self, monkeypatch):
        import time

        from src.commands import playlist as playlist_cmd

        now = time.time()
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": now} for _ in range(2)
        ]

        # pydantic v2 の BaseModel はインスタンスへの任意属性代入を許さないため、
        # クラス側のメソッドを差し替える (config はインスタンス)
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        # 10000 - 2*1600 = 6800 -> 6800 // 50 = 136
        assert playlist_cmd._default_max_items(history) == 136

    def test_default_max_items_ignores_yesterday_uploads(self, monkeypatch):
        """本日分だけを勘定する (境界の確認)。"""
        import time

        from src.commands import playlist as playlist_cmd

        yesterday = time.time() - 86400 * 2
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": yesterday} for _ in range(5)
        ]

        # pydantic v2 の BaseModel はインスタンスへの任意属性代入を許さないため、
        # クラス側のメソッドを差し替える (config はインスタンス)
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        assert playlist_cmd._default_max_items(history) == 200

    def test_default_max_items_never_negative(self, monkeypatch):
        import time

        from src.commands import playlist as playlist_cmd

        now = time.time()
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": now} for _ in range(100)
        ]

        # pydantic v2 の BaseModel はインスタンスへの任意属性代入を許さないため、
        # クラス側のメソッドを差し替える (config はインスタンス)
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        assert playlist_cmd._default_max_items(history) == 0

    def test_fix_orphans_stops_on_quota_error(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaExceededError, QuotaLedger

        orphans = [
            {"id": f"v{i}", "title": f"動画{i}"} for i in range(5)
        ]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        # 3件目で quota 枯渇
        pl_manager.add_video_to_playlist.side_effect = [
            True, True, QuotaExceededError("out of quota"), True, True
        ]
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=5, yes=True
        )

        assert assigned == 2, "枯渇前の2件だけが成功する"
        assert remaining == 3, "残り3件が報告される"
        assert pl_manager.add_video_to_playlist.call_count == 3, "枯渇後は呼ばない"

    def test_fix_orphans_records_synced_state(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}, {"id": "v2", "title": "動画2"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.side_effect = [True, False]
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        _fix_orphans(orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True)

        history.set_playlist_synced.assert_any_call("v1", True)
        history.set_playlist_synced.assert_any_call("v2", False)

    def test_fix_orphans_respects_max_items(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": f"v{i}", "title": f"動画{i}"} for i in range(10)]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=3, yes=True
        )

        assert assigned == 3
        assert remaining == 7
        assert pl_manager.add_video_to_playlist.call_count == 3

    def test_fix_orphans_stops_when_ledger_exhausted(self):
        """API が 403 を返す前に、帳簿の予算で自主的に止まる。"""
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": f"v{i}", "title": f"動画{i}"} for i in range(10)]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        # 予算 100 units = insert 2回分
        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100), max_items=10, yes=True
        )

        assert assigned == 2
        assert remaining == 8

    def test_fix_orphans_skips_videos_without_history(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}, {"id": "v2", "title": "動画2"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        # v1 は履歴あり、v2 は履歴なし
        history.get_record_by_video_id.side_effect = [
            {"playlist_name": "運動会"}, None
        ]

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True
        )

        assert assigned == 1
        assert pl_manager.add_video_to_playlist.call_count == 1

    def test_fix_orphans_falls_back_to_parent_dir(self):
        """playlist_name が無ければ file_path の親ディレクトリ名を使う (既存挙動)。"""
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {
            "playlist_name": None, "file_path": "/videos/2011運動会/a.mp4"
        }

        _fix_orphans(orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True)

        pl_manager.get_or_create_playlist.assert_called_once_with("2011運動会")


if __name__ == "__main__":
    unittest.main()
