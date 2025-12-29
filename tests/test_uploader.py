import pytest
from unittest.mock import MagicMock
from pathlib import Path
from src.uploader import VideoUploader

@pytest.mark.asyncio
class TestVideoUploader:
    
    @pytest.fixture
    def mock_service(self):
        return MagicMock()

    @pytest.fixture
    def uploader(self, mock_service):
        return VideoUploader(mock_service)

    async def test_upload_video_success(self, uploader, mock_service, tmp_path):
        """Test successful video upload."""
        # Setup mock responses
        # 1. videos().insert() returns request object
        mock_request = MagicMock()
        mock_service.videos().insert.return_value = mock_request
        
        # 2. request.next_chunk() simulation
        # First call: (status=Progress, response=None)
        # Second call: (status=None, response={id: "vid123"})
        mock_status = MagicMock()
        mock_status.progress.return_value = 0.5
        
        mock_request.next_chunk.side_effect = [
            (mock_status, None),
            (None, {"id": "vid123"})
        ]
        
        file_path = tmp_path / "test.mp4"
        file_path.write_text("dummy")
        
        metadata = {
            "title": "Test Title",
            "description": "Desc",
            "tags": ["tag1"]
        }
        
        progress_callback = MagicMock()
        
        video_id = await uploader.upload_video(file_path, metadata, progress_callback)
        
        assert video_id == "vid123"
        assert progress_callback.call_count == 1
        
        # Verify API call args
        args, kwargs = mock_service.videos().insert.call_args
        body = kwargs["body"]
        assert body["snippet"]["title"] == "Test Title"
        assert body["status"]["privacyStatus"] == "private"

    async def test_upload_failure(self, uploader, mock_service, tmp_path):
        """Test upload failure handled gracefully (or re-raised depending on logic)."""
        mock_request = MagicMock()
        mock_service.videos().insert.return_value = mock_request
        
        # Simulate error
        mock_request.next_chunk.side_effect = Exception("Upload Failed")
        
        file_path = tmp_path / "test.mp4"
        file_path.write_text("dummy")
        
        with pytest.raises(Exception, match="Upload Failed"):
            await uploader.upload_video(file_path, {}, None)
