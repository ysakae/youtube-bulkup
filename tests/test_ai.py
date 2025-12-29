import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
from src.ai import MetadataGenerator
from src.config import config

@pytest.mark.asyncio
class TestMetadataGenerator:
    
    async def test_init_disabled(self, mocker):
        """Test initialization when AI is disabled."""
        mocker.patch.object(config.ai, 'enabled', False)
        # Verify logger warning called if enabled=True but no key, 
        # but here we disable it, so just check it initializes without error.
        ai = MetadataGenerator()
        assert ai.enabled is False

    async def test_init_no_key(self, mocker):
        """Test initialization when enabled but no API key."""
        mocker.patch.object(config.ai, 'enabled', True)
        mocker.patch.object(config.ai, 'api_key', None)
        mocker.patch("os.getenv", return_value=None)
        
        mock_logger = mocker.patch("src.ai.logger")
        
        ai = MetadataGenerator()
        mock_logger.warning.assert_called_once()
        assert hasattr(ai, 'client') is False

    async def test_generate_metadata_success(self, mocker, mock_google_client, mock_env):
        """Test successful metadata generation with directory context."""
        mocker.patch.object(config.ai, 'enabled', True)
        mocker.patch.object(config.ai, 'api_key', 'test_key')
        mocker.patch.object(config.ai, 'language', 'ja')
        
        ai = MetadataGenerator()
        
        # Mock response
        expected_json = {
            "title": "Test Title",
            "description": "Test Description",
            "tags": ["tag1"]
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(expected_json)
        
        # Setup async mock for client.aio.models.generate_content
        mock_generate = AsyncMock(return_value=mock_response)
        ai.client.aio.models.generate_content = mock_generate
        
        # Test file path
        file_path = Path("/path/to/EventName/video.mp4")
        
        metadata = await ai.generate_metadata(file_path)
        
        assert metadata["title"] == "Test Title"
        assert metadata["description"] == "Test Description"
        
        # Verify prompt contains directory name
        call_args = mock_generate.call_args
        assert call_args is not None
        _, kwargs = call_args
        prompt = kwargs["contents"]
        assert "EventName" in prompt
        assert "Japanese" in prompt

    async def test_generate_metadata_error(self, mocker, mock_google_client):
        """Test error handling during generation."""
        mocker.patch.object(config.ai, 'enabled', True)
        mocker.patch.object(config.ai, 'api_key', 'test_key')
        
        ai = MetadataGenerator()
        
        # Mock error
        ai.client.aio.models.generate_content = AsyncMock(side_effect=Exception("API Error"))
        
        file_path = Path("video.mp4")
        metadata = await ai.generate_metadata(file_path)
        
        # Should return defaults
        assert metadata["title"] == "Video"
        assert metadata["tags"] == ["auto-upload"]

    async def test_generate_metadata_disabled_returns_defaults(self, mocker):
        """Test that disabled generator returns defaults immediately."""
        mocker.patch.object(config.ai, 'enabled', False)
        
        ai = MetadataGenerator()
        file_path = Path("video.mp4")
        
        metadata = await ai.generate_metadata(file_path)
        assert metadata["title"] == "Video"
