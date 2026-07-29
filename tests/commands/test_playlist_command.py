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
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_list_shows_breakdown_counts(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
        """新設の内訳集計 (割り当て先判明数 / 同期失敗・不明の内訳) を検証する。"""
        mock_get_credentials.return_value = MagicMock()

        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [
            {"id": "VID1", "title": "Video 1"},
            {"id": "VID2", "title": "Video 2"},
            {"id": "VID3", "title": "Video 3"},
        ]

        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_record_by_video_id.side_effect = [
            {"playlist_name": "PlaylistA", "playlist_synced": None},  # 判明・同期状態不明
            {"playlist_name": "PlaylistB", "playlist_synced": 0},  # 判明・同期失敗
            None,  # 割り当て先不明
        ]

        result = runner.invoke(app, ["playlist", "orphans"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("走査したプレイリスト:", result.output)
        self.assertIn("うち履歴から割り当て先が判明: 2", result.output)
        self.assertIn("うち割り当て先不明 (スキップ対象): 1", result.output)
        self.assertIn("追加失敗として記録済み 1", result.output)
        self.assertIn("不明 (この機能より前の記録) 1", result.output)

    def test_orphans_offline_and_fix_mutually_exclusive(self):
        """--offline と --fix は同時指定できない (offline は書き込み不可のため)。"""
        result = runner.invoke(app, ["playlist", "orphans", "--offline", "--fix"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("--offline と --fix は同時に指定できません", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_offline_flag_propagates_to_managers(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
        """--offline が VideoManager/PlaylistManager まで正しく伝播することを検証する。"""
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Video 1"}]
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        result = runner.invoke(app, ["playlist", "orphans", "--offline"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("オフラインモード", result.output)
        mock_vid.get_all_uploaded_videos.assert_called_once_with(refresh=False, offline=True)
        mock_pl.get_all_playlists_map.assert_called_once_with(refresh=False, offline=True)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_quota_exceeded_during_fetch_exits_1(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
        """取得中に QuotaExceededError が出たら exit 1 で案内を出す。"""
        from src.lib.core.quota import QuotaExceededError

        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.side_effect = QuotaExceededError("out of quota")

        result = runner.invoke(app, ["playlist", "orphans"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("クォータを使い切っているため取得できませんでした", result.output)
        self.assertIn("--offline を付けるとキャッシュから調査できます", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    def test_orphans_offline_runtime_error_exits_1(
        self, MockVidManager, MockPlManager, mock_get_credentials, MockHistoryMgr, mock_make_cache
    ):
        """offline でキャッシュが空/未設定なら RuntimeError を案内して exit 1。"""
        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.side_effect = RuntimeError(
            "キャッシュが空のため offline モードで実行できません。"
        )

        result = runner.invoke(app, ["playlist", "orphans", "--offline"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("キャッシュが空のため", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.lib.video.manager.VideoManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_orphans_fix_limit_zero_stops_before_assigning(
        self, MockHistoryMgr, MockVidManager, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        """本日の推定残量が0件なら --fix を指定しても何も割り当てない。"""
        from src.lib.core.config import config

        mock_get_credentials.return_value = MagicMock()
        mock_vid = MockVidManager.return_value
        mock_vid.get_all_uploaded_videos.return_value = [{"id": "VID1", "title": "Video 1"}]
        mock_pl = MockPlManager.return_value
        mock_pl.get_all_playlists_map.return_value = {}

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_all_records.return_value = []
        mock_hist.get_record_by_video_id.return_value = None

        with patch.object(type(config), "effective_daily_quota", lambda self: 0), \
             patch.object(config.quota, "reserve", 0):
            result = runner.invoke(app, ["playlist", "orphans", "--fix", "-y"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("本日の推定残量では1件も処理できません", result.output)
        mock_pl.get_or_create_playlist.assert_not_called()

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

    def test_max_items_does_not_bypass_daily_budget(self, monkeypatch):
        """--max-items に予算より大きい値を渡しても、実際の予算 (本日の残量)

        で頭打ちになることを検証する。--max-items は「予算内での上限」で
        あるべきで、予算そのものを拡張する抜け道になってはいけない。
        """
        from src.commands import playlist as playlist_cmd
        from src.main import app as cli_app

        # effective_daily_quota=10000, reserve=9900, used=0 -> budget=100
        # -> budget_items = 100 // 50 = 2 件
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 9900)

        orphans = [{"id": f"v{i}", "title": f"動画{i}"} for i in range(5)]

        with patch("src.commands.playlist.get_credentials") as mock_get_credentials, \
             patch("src.commands.playlist.PlaylistManager") as MockPlManager, \
             patch("src.lib.video.manager.VideoManager") as MockVidManager, \
             patch("src.commands.playlist.HistoryManager") as MockHistoryMgr, \
             patch("src.commands.playlist._make_cache", return_value=None):

            mock_get_credentials.return_value = MagicMock()
            mock_vid = MockVidManager.return_value
            mock_vid.get_all_uploaded_videos.return_value = orphans
            mock_pl = MockPlManager.return_value
            mock_pl.get_all_playlists_map.return_value = {}
            mock_pl.get_or_create_playlist.return_value = "PL1"
            mock_pl.add_video_to_playlist.return_value = True

            mock_hist = MockHistoryMgr.return_value
            mock_hist.get_all_records.return_value = []
            mock_hist.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

            result = runner.invoke(
                cli_app, ["playlist", "orphans", "--fix", "-y", "--max-items", "5000"]
            )

        assert result.exit_code == 0
        # --max-items 5000 を要求しても、予算 (2件分) で頭打ちになる
        assert mock_pl.add_video_to_playlist.call_count == 2, (
            "--max-items が予算を上書きしてしまっている"
        )
        assert "残り 3 件" in result.output


class TestDedupe:
    """重複プレイリストの統合。"""

    @staticmethod
    def _info(pid, title, published, item_count=0):
        from src.lib.video.playlist import PlaylistInfo

        return PlaylistInfo(
            id=pid, title=title, item_count=item_count,
            privacy="private", published_at=published,
        )

    def test_merge_moves_videos_to_canonical(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1"}, "PL_NEW": {"v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 2
        assert deleted == 1
        assert interrupted is False
        assert pl_manager.add_video_to_playlist.call_count == 2
        pl_manager.add_video_to_playlist.assert_any_call("PL_OLD", "v2")
        pl_manager.add_video_to_playlist.assert_any_call("PL_OLD", "v3")
        pl_manager.delete_playlist.assert_called_once_with("PL_NEW")

    def test_merge_skips_insert_for_already_present_video(self):
        """正にすでに入っている動画は insert を省き delete だけ行う (50 units 節約)。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1", "v2"}, "PL_NEW": {"v2"}}

        pl_manager = MagicMock()
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        pl_manager.add_video_to_playlist.assert_not_called()
        pl_manager.remove_video_from_playlist.assert_called_once_with("PL_NEW", "v2")
        assert moved == 1
        assert deleted == 1
        assert interrupted is False

    def test_merge_stops_on_quota_error(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaExceededError, QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.side_effect = [
            True, QuotaExceededError("out"), True
        ]
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 1
        assert deleted == 0, "全部移せていないので削除しない"
        assert interrupted is True, "quota 枯渇は呼び出し元に伝わらなければならない"
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_does_not_delete_when_max_items_reached(self):
        """上限で打ち切った場合、中身が残るプレイリストは削除しない。

        max_items による打ち切りは自主的なもので実際の quota 枯渇ではないため
        interrupted は False (呼び出し元の外側ループは続けてよい)。
        """
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=2
        )

        assert moved == 2
        assert deleted == 0
        assert interrupted is False
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_empty_duplicate_is_deleted_directly(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1"}, "PL_NEW": set()}

        pl_manager = MagicMock()

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 0
        assert deleted == 1
        assert interrupted is False
        pl_manager.add_video_to_playlist.assert_not_called()
        pl_manager.delete_playlist.assert_called_once_with("PL_NEW")

    # --- Critical: 中身が「不明」なプレイリストを「空」とみなして削除しない ---

    def test_merge_skips_delete_when_dup_not_in_playlist_map(self):
        """playlist_map にキーが無い (中身を把握していない) 重複プレイリストは
        削除しない。dict.get(..., set()) で「空」と混同すると、スナップショットが
        古くて把握できていないだけの中身入りプレイリストを削除してしまう。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z", item_count=5)
        playlist_map = {"PL_OLD": {"v1"}}  # PL_NEW はキーごと無い (未取得)

        pl_manager = MagicMock()

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 0
        assert deleted == 0
        assert interrupted is False
        pl_manager.add_video_to_playlist.assert_not_called()
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_skips_delete_when_item_count_does_not_match(self):
        """把握している動画数 (playlist_map) が実際の item_count より少ない場合、
        未把握の動画が残っている可能性があるため削除しない。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        # 実際は3件あるが playlist_map には2件しか無い (スナップショットが古い)
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z", item_count=3)
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 2, "把握している分は移動してよい"
        assert deleted == 0, "件数が一致しないので削除しない"
        assert interrupted is False
        pl_manager.delete_playlist.assert_not_called()

    # --- Important 4: データ損失に直結する中断経路 ---

    def test_merge_partial_insert_failure_does_not_delete(self):
        """一部の動画で insert が失敗した場合、削除しない。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.side_effect = [True, False, True]
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 2
        assert deleted == 0
        assert interrupted is False
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_partial_remove_failure_does_not_delete(self):
        """一部の動画で remove (プレイリストからの削除) が失敗した場合、
        動画が両方のプレイリストに残ってしまうため、重複側を削除しない。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.side_effect = [True, False, True]

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert deleted == 0
        assert interrupted is False
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_stops_when_ledger_budget_insufficient(self):
        """ledger の残予算が足りない場合、例外を投げずに打ち切り、削除もしない。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        # 150 units = 1本分 (insert 50 + delete 50) しか賄えない
        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(150), max_items=100
        )

        assert moved == 1
        assert deleted == 0
        assert interrupted is False
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_delete_playlist_quota_error_marks_interrupted(self):
        """delete_playlist 自体が quota 枯渇で失敗しても例外を漏らさず
        interrupted=True として呼び出し元に知らせる。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaExceededError, QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1"}, "PL_NEW": set()}

        pl_manager = MagicMock()
        pl_manager.delete_playlist.side_effect = QuotaExceededError("out")

        moved, deleted, interrupted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 0
        assert deleted == 0
        assert interrupted is True


class TestDedupeCommand(unittest.TestCase):
    """`yt-up playlist dedupe` CLI コマンドのテスト。"""

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_dedupe_no_duplicates(
        self, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        mock_get_credentials.return_value = MagicMock()
        mock_pl = MockPlManager.return_value
        mock_pl.get_duplicate_playlists.return_value = {}

        result = runner.invoke(app, ["playlist", "dedupe"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("重複しているプレイリストはありません", result.output)
        mock_pl.get_all_playlists_map.assert_not_called()

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_dedupe_detect_only_does_not_fetch_map(
        self, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        """--fix なしなら検出のみで、動画マップ取得 (課金対象) は行わない。"""
        from src.lib.video.playlist import PlaylistInfo

        mock_get_credentials.return_value = MagicMock()
        mock_pl = MockPlManager.return_value
        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=2,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}

        result = runner.invoke(app, ["playlist", "dedupe"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("運動会", result.output)
        self.assertIn("--fix を付けると統合します", result.output)
        mock_pl.get_all_playlists_map.assert_not_called()

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    def test_dedupe_quota_error_on_detect_exits_1(
        self, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        from src.lib.core.quota import QuotaExceededError

        mock_get_credentials.return_value = MagicMock()
        mock_pl = MockPlManager.return_value
        mock_pl.get_duplicate_playlists.side_effect = QuotaExceededError("out")

        result = runner.invoke(app, ["playlist", "dedupe"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("クォータを使い切っている", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_dedupe_fix_merges_and_clears_cache(
        self, MockHistoryMgr, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        from src.lib.video.playlist import PlaylistInfo

        mock_get_credentials.return_value = MagicMock()
        cache = MagicMock()
        mock_make_cache.return_value = cache

        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_all_records.return_value = []

        mock_pl = MockPlManager.return_value
        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=2,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}
        mock_pl.get_all_playlists_map.return_value = {
            "PL_OLD": {"v1"}, "PL_NEW": {"v2", "v3"}
        }
        mock_pl.add_video_to_playlist.return_value = True
        mock_pl.remove_video_from_playlist.return_value = True
        mock_pl.delete_playlist.return_value = True

        result = runner.invoke(app, ["playlist", "dedupe", "--fix", "-y"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("2 本を移動", result.output)
        self.assertIn("1 個のプレイリストを削除しました", result.output)
        # --fix は破壊的操作なので、24時間キャッシュされたスナップショットではなく
        # 必ず最新の動画マップを取得する (Critical レビュー対応)。
        mock_pl.get_all_playlists_map.assert_called_once_with(refresh=True)
        cache.clear.assert_called_once()
        cache.close.assert_called_once()
        mock_hist.close.assert_called_once()

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_dedupe_fix_quota_error_on_map_exits_1(
        self, MockHistoryMgr, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        from src.lib.core.quota import QuotaExceededError
        from src.lib.video.playlist import PlaylistInfo

        mock_get_credentials.return_value = MagicMock()
        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_all_records.return_value = []

        mock_pl = MockPlManager.return_value
        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=2,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}
        mock_pl.get_all_playlists_map.side_effect = QuotaExceededError("out")

        result = runner.invoke(app, ["playlist", "dedupe", "--fix", "-y"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("クォータを使い切っているため統合できません", result.output)

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.commands.playlist.HistoryManager")
    @patch("src.commands.playlist.typer.confirm", return_value=False)
    def test_dedupe_fix_abort_without_yes(
        self, mock_confirm, MockHistoryMgr, MockPlManager, mock_get_credentials,
        mock_make_cache
    ):
        from src.lib.video.playlist import PlaylistInfo

        mock_get_credentials.return_value = MagicMock()
        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_all_records.return_value = []

        mock_pl = MockPlManager.return_value
        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=2,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}
        mock_pl.get_all_playlists_map.return_value = {
            "PL_OLD": {"v1"}, "PL_NEW": {"v2"}
        }

        result = runner.invoke(app, ["playlist", "dedupe", "--fix"])

        self.assertEqual(result.exit_code, 1)
        mock_pl.add_video_to_playlist.assert_not_called()
        mock_pl.delete_playlist.assert_not_called()

    @patch("src.commands.playlist._make_cache", return_value=None)
    @patch("src.commands.playlist.get_credentials")
    @patch("src.commands.playlist.PlaylistManager")
    @patch("src.commands.playlist.HistoryManager")
    def test_dedupe_fix_reports_remaining_groups_on_quota_exhaustion(
        self, MockHistoryMgr, MockPlManager, mock_get_credentials, mock_make_cache
    ):
        """Important 1: quota 枯渇がグループをまたいで伝播し、
        残りグループ数が正しく報告されること (成功サマリだけで終わらない)。"""
        from src.lib.core.quota import QuotaExceededError
        from src.lib.video.playlist import PlaylistInfo

        mock_get_credentials.return_value = MagicMock()
        mock_hist = MockHistoryMgr.return_value
        mock_hist.get_all_records.return_value = []

        mock_pl = MockPlManager.return_value
        old1 = PlaylistInfo(
            id="PL_OLD1", title="運動会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new1 = PlaylistInfo(
            id="PL_NEW1", title="運動会", item_count=1,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        old2 = PlaylistInfo(
            id="PL_OLD2", title="発表会", item_count=1,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new2 = PlaylistInfo(
            id="PL_NEW2", title="発表会", item_count=1,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )
        mock_pl.get_duplicate_playlists.return_value = {
            "運動会": [old1, new1], "発表会": [old2, new2]
        }
        mock_pl.get_all_playlists_map.return_value = {
            "PL_OLD1": set(), "PL_NEW1": {"v1"},
            "PL_OLD2": set(), "PL_NEW2": {"v2"},
        }
        # 1件目のグループの移動で quota 枯渇。2件目のグループは一切処理されない
        # (何度も「クォータを使い切りました」を繰り返し表示してはいけない)。
        mock_pl.add_video_to_playlist.side_effect = QuotaExceededError("out")

        result = runner.invoke(app, ["playlist", "dedupe", "--fix", "-y"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            result.output.count("クォータを使い切りました"), 1,
            "quota 枯渇メッセージがグループの数だけ繰り返し表示されている",
        )
        self.assertIn("残り 1 グループ", result.output)
        mock_pl.delete_playlist.assert_not_called()


class TestDedupeQuotaControl:
    """dedupe の予算制 (Important 3: 本日の残りクォータから予算を導く)。"""

    def test_dedupe_fix_max_items_does_not_bypass_daily_budget(self, monkeypatch):
        """--max-items に予算より大きい値を渡しても、本日の実残量 (budget_items)
        で頭打ちになることを検証する (dedupe は1本 = insert+delete = 100 units)。"""
        from src.commands import playlist as playlist_cmd
        from src.lib.video.playlist import PlaylistInfo
        from src.main import app as cli_app

        # effective_daily_quota=10000, reserve=9900, used=0 -> budget=100
        # -> unit_cost (insert+delete)=100 -> budget_items = 100 // 100 = 1 件
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 9900)

        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=0,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=2,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )

        with patch("src.commands.playlist.get_credentials") as mock_get_credentials, \
             patch("src.commands.playlist.PlaylistManager") as MockPlManager, \
             patch("src.commands.playlist.HistoryManager") as MockHistoryMgr, \
             patch("src.commands.playlist._make_cache", return_value=None):

            mock_get_credentials.return_value = MagicMock()
            mock_pl = MockPlManager.return_value
            mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}
            mock_pl.get_all_playlists_map.return_value = {
                "PL_OLD": set(), "PL_NEW": {"v1", "v2"}
            }
            mock_pl.add_video_to_playlist.return_value = True
            mock_pl.remove_video_from_playlist.return_value = True
            mock_pl.delete_playlist.return_value = True

            mock_hist = MockHistoryMgr.return_value
            mock_hist.get_all_records.return_value = []

            result = runner.invoke(
                cli_app, ["playlist", "dedupe", "--fix", "-y", "--max-items", "5000"]
            )

        assert result.exit_code == 0
        assert mock_pl.add_video_to_playlist.call_count == 1, (
            "--max-items が本日の予算を上書きしてしまっている"
        )

    def test_dedupe_fix_zero_budget_skips_map_fetch(self, monkeypatch):
        """本日の残予算が0のときは、動画マップ取得 (課金対象) すら行わずに
        即座に中断する。"""
        from src.commands import playlist as playlist_cmd
        from src.lib.video.playlist import PlaylistInfo
        from src.main import app as cli_app

        # effective_daily_quota=10000, reserve=10000, used=0 -> budget=0
        monkeypatch.setattr(
            type(playlist_cmd.config), "effective_daily_quota", lambda self: 10000
        )
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 10000)

        old = PlaylistInfo(
            id="PL_OLD", title="運動会", item_count=0,
            privacy="private", published_at="2020-01-01T00:00:00Z",
        )
        new = PlaylistInfo(
            id="PL_NEW", title="運動会", item_count=1,
            privacy="private", published_at="2024-01-01T00:00:00Z",
        )

        with patch("src.commands.playlist.get_credentials") as mock_get_credentials, \
             patch("src.commands.playlist.PlaylistManager") as MockPlManager, \
             patch("src.commands.playlist.HistoryManager") as MockHistoryMgr, \
             patch("src.commands.playlist._make_cache", return_value=None):

            mock_get_credentials.return_value = MagicMock()
            mock_pl = MockPlManager.return_value
            mock_pl.get_duplicate_playlists.return_value = {"運動会": [old, new]}

            mock_hist = MockHistoryMgr.return_value
            mock_hist.get_all_records.return_value = []

            result = runner.invoke(cli_app, ["playlist", "dedupe", "--fix", "-y"])

        assert result.exit_code == 0
        assert "本日の推定残量では1件も処理できません" in result.output
        mock_pl.get_all_playlists_map.assert_not_called()


if __name__ == "__main__":
    unittest.main()
