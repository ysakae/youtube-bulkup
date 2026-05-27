from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.lib.video.uploader import VideoUploader


@pytest.fixture
def mock_service():
    return MagicMock()



@pytest.fixture
def uploader():
    return VideoUploader(MagicMock())


@pytest.fixture(autouse=True)
def mock_media_file_upload():
    with patch("src.lib.video.uploader.MediaFileUpload") as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_build(mock_service):
    with patch("src.lib.video.uploader.build") as mock:
        mock.return_value = mock_service
        yield mock


@pytest.mark.asyncio
async def test_upload_video_success(uploader, mock_service):
    # Setup mock chain
    mock_insert = mock_service.videos().insert
    mock_request = mock_insert.return_value
    
    # Mock next_chunk behavior
    mock_status = MagicMock()
    mock_status.progress.return_value = 0.5
    
    mock_request.next_chunk.side_effect = [
        (mock_status, None),
        (None, {"id": "vid_success"})
    ]

    path = MagicMock()
    path.__str__.return_value = "/tmp/test.mp4"
    path.name = "test.mp4"
    
    metadata = {
        "title": "Title",
        "description": "Desc",
        "tags": ["tag"],
        "recordingDetails": {}
    }

    # Execute
    video_id = await uploader.upload_video(path, metadata)

    assert video_id == "vid_success"
    mock_insert.assert_called_once()
    assert mock_request.next_chunk.call_count == 2


@pytest.mark.asyncio
async def test_upload_video_api_error(uploader, mock_service):
    mock_insert = mock_service.videos().insert
    mock_request = mock_insert.return_value
    
    # Simulate HttpError
    resp = MagicMock()
    resp.status = 500
    # The retry logic catches this and retries. 
    # To avoid long waits, we can patch the sleep/wait behavior or just expect RetryError from tenacity
    # tenacity raises RetryError wrapping the original exception
    
    mock_request.next_chunk.side_effect = HttpError(resp, b"Error")
    
    path = MagicMock()
    path.__str__.return_value = "/tmp/test.mp4"
    
    from tenacity import RetryError
    with pytest.raises(RetryError):
        await uploader.upload_video(path, {})


@pytest.mark.asyncio
async def test_upload_video_unexpected_failure(uploader, mock_service):
    mock_insert = mock_service.videos().insert
    mock_request = mock_insert.return_value
    
    # Mock response without ID
    mock_request.next_chunk.return_value = (None, {"error": "Unknown"})
    
    path = MagicMock()
    path.__str__.return_value = "/tmp/test.mp4"
    path.name = "test.mp4"
    
    video_id = await uploader.upload_video(path, {})
    assert video_id is None


def test_should_retry_exception():
    import socket

    from src.lib.video.uploader import should_retry_exception

    assert should_retry_exception(socket.error()) is True
    assert should_retry_exception(socket.timeout()) is True

    # HttpError
    resp = MagicMock()
    resp.status = 503
    assert should_retry_exception(HttpError(resp, b"")) is True

    resp.status = 404
    assert should_retry_exception(HttpError(resp, b"")) is False

    assert should_retry_exception(ValueError()) is False


def test_should_not_retry_daily_upload_quota_429():
    """1日のアップロード上限超過 (429 + 'Video Uploads per day') はリトライしない。"""
    from src.lib.video.uploader import should_retry_exception

    resp = MagicMock()
    resp.status = 429
    content = (
        b"Quota exceeded for quota metric 'Video Uploads' "
        b"and limit 'Video Uploads per day' of service 'youtube.googleapis.com'"
    )
    assert should_retry_exception(HttpError(resp, content)) is False


def test_should_retry_transient_429():
    """通常の429 (一時的なレート制限) はリトライ対象として扱う。"""
    from src.lib.video.uploader import should_retry_exception

    resp = MagicMock()
    resp.status = 429
    assert should_retry_exception(HttpError(resp, b"Too Many Requests")) is True
