"""upload_manager.handle_upload_error の単体テスト。"""
import asyncio
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from src.services.upload_manager import handle_upload_error


def _make_http_error(status: int, content: bytes) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "Error"
    return HttpError(resp, content)


def test_handle_upload_error_429_daily_video_upload_quota_stops_pipeline():
    """429 + 'Video Uploads per day' は1日のアップロード上限超過。
    `stop_event` をセットし、失敗履歴に記録する。"""
    err = _make_http_error(
        429,
        (
            b"Quota exceeded for quota metric 'Video Uploads' "
            b"and limit 'Video Uploads per day' of service 'youtube.googleapis.com'"
        ),
    )
    file_path = MagicMock()
    file_path.name = "v1.m2ts"
    file_path.__str__.return_value = "/tmp/v1.m2ts"
    progress = MagicMock()
    history = MagicMock()
    stop_event = asyncio.Event()

    handle_upload_error(
        err,
        file_path=file_path,
        file_hash="hash1",
        file_size=1000,
        target_playlist="pl",
        stop_event=stop_event,
        progress=progress,
        history=history,
    )

    assert stop_event.is_set(), "1日のアップロード上限超過時は stop_event がセットされるべき"
    history.add_failure.assert_called_once()
    # 失敗内容に "Daily Upload Quota Exceeded" 等の明示的な理由が含まれることを確認
    args, kwargs = history.add_failure.call_args
    failure_reason = args[2] if len(args) >= 3 else kwargs.get("reason", "")
    assert "Quota" in failure_reason or "Upload" in failure_reason


def test_handle_upload_error_403_quota_exceeded_stops_pipeline():
    """既存挙動の回帰テスト: 403 + 'quotaExceeded' は全停止。"""
    err = _make_http_error(403, b"quotaExceeded")
    file_path = MagicMock()
    file_path.name = "v1.mp4"
    progress = MagicMock()
    history = MagicMock()
    stop_event = asyncio.Event()

    handle_upload_error(
        err,
        file_path=file_path,
        file_hash="hash1",
        file_size=1000,
        target_playlist="pl",
        stop_event=stop_event,
        progress=progress,
        history=history,
    )

    assert stop_event.is_set()
    history.add_failure.assert_called_once()


def test_handle_upload_error_generic_500_does_not_stop_pipeline():
    """一般的なサーバーエラーでは stop_event をセットしない。"""
    err = _make_http_error(500, b"Internal Server Error")
    file_path = MagicMock()
    file_path.name = "v1.mp4"
    progress = MagicMock()
    history = MagicMock()
    stop_event = asyncio.Event()

    handle_upload_error(
        err,
        file_path=file_path,
        file_hash="hash1",
        file_size=1000,
        target_playlist="pl",
        stop_event=stop_event,
        progress=progress,
        history=history,
    )

    assert not stop_event.is_set()
    history.add_failure.assert_called_once()


class TestPostUploadPlaylistSync:
    """プレイリスト追加の成否を履歴に記録する。"""

    @staticmethod
    def _args(playlist_manager, history):
        """post_upload_sync の共通引数を組み立てる。"""
        from pathlib import Path

        progress = MagicMock()
        return dict(
            file_path=Path("/videos/運動会/a.mp4"),
            file_hash="h1",
            file_size=100,
            video_id="vid1",
            metadata={"title": "t"},
            target_playlist="運動会",
            playlist_manager=playlist_manager,
            uploader=MagicMock(),
            history=history,
            progress=progress,
        )

    @pytest.mark.asyncio
    async def test_records_success(self):
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.return_value = True
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", True)

    @pytest.mark.asyncio
    async def test_records_failure_when_add_returns_false(self):
        """戻り値 False を握りつぶさず記録する (オーファンの発生源)。"""
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.return_value = False
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_records_failure_when_playlist_not_created(self):
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = None
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_quota_error_is_recorded_and_propagated(self):
        """quota 枯渇は記録した上で上位に伝播させ、アップロード全体を止める。"""
        from src.lib.core.quota import QuotaExceededError
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.side_effect = QuotaExceededError("out")
        history = MagicMock()

        with pytest.raises(QuotaExceededError):
            await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_generic_exception_is_recorded_and_swallowed(self):
        """quota 以外の例外は従来どおり握りつぶすが、記録は残す。"""
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.side_effect = ValueError("boom")
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_no_playlist_manager_does_not_record(self):
        """プレイリスト管理を使わない場合は記録しない (NULL のまま)。"""
        from src.services.upload_manager import post_upload_sync

        history = MagicMock()
        args = self._args(None, history)

        await post_upload_sync(**args)

        history.set_playlist_synced.assert_not_called()
