"""upload_manager.handle_upload_error の単体テスト。"""
import asyncio
from unittest.mock import MagicMock

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
