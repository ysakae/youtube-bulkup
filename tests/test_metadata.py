import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.metadata import FileMetadataGenerator

class TestFileMetadataGenerator:
    @pytest.fixture
    def generator(self):
        return FileMetadataGenerator()

    @patch("src.metadata.createParser")
    @patch("src.metadata.extractMetadata")
    def test_generate_with_date(self, mock_extract, mock_parser, generator):
        """Test metadata generation when creation date is found."""
        # Setup Mocks
        file_path = Path("/path/to/EVENT_NAME/video.mp4")
        
        mock_meta = MagicMock()
        mock_meta.has.side_effect = lambda key: key in ["creation_date"]
        # Use a fixed date: 2023-01-01 12:00:00
        mock_meta.get.side_effect = lambda key: datetime(2023, 1, 1, 12, 0, 0) if key == "creation_date" else None
        
        mock_extract.return_value = mock_meta

        # Execute
        result = generator.generate(file_path, index=1, total=5)

        # Verify
        assert result["title"] == "【EVENT_NAME】video"
        assert "EVENT_NAME" in result["description"]
        assert "No. 1/5" in result["description"]
        assert "Captured: 2023-01-01 12:00:00" in result["description"]
        assert "EVENT_NAME" in result["tags"]
        assert "2023" in result["tags"]
        assert result["recordingDetails"]["recordingDate"] == "2023-01-01T12:00:00Z"

    @patch("src.metadata.createParser")
    def test_generate_no_metadata(self, mock_parser, generator):
        """Test fallback when no metadata can be extracted."""
        # Setup Mocks to fail parsing
        mock_parser.return_value = None
        
        file_path = Path("/path/to/Folder/test.mov")

        # Execute
        result = generator.generate(file_path, index=2, total=2)

        # Verify
        assert result["title"] == "【Folder】test"
        assert "Captured: Unknown" in result["description"]
        # Should still have basic tags
        assert "Folder" in result["tags"]
        # recordingDate should not be present
        assert "recordingDate" not in result["recordingDetails"]

    @patch("src.metadata.createParser")
    @patch("src.metadata.extractMetadata")
    def test_generate_with_gps(self, mock_extract, mock_parser, generator):
        """Test metadata generation when GPS data is found."""
        # Setup Mocks
        file_path = Path("/path/to/EVENT_NAME/video.mp4")
        
        mock_meta = MagicMock()
        
        # Mocking .has() behavior for GPS
        def has_side_effect(key):
            return key in ["creation_date", "latitude", "longitude", "altitude"]
        mock_meta.has.side_effect = has_side_effect
        
        # Mocking .get() behavior
        def get_side_effect(key):
            data = {
                "creation_date": datetime(2023, 1, 1, 12, 0, 0),
                "latitude": 35.6895,
                "longitude": 139.6917,
                "altitude": 10.5
            }
            return data.get(key)
        mock_meta.get.side_effect = get_side_effect
        
        mock_extract.return_value = mock_meta

        # Execute
        result = generator.generate(file_path, index=1, total=1)

        # Verify
        rec_details = result["recordingDetails"]
        assert "location" in rec_details
        assert rec_details["location"]["latitude"] == 35.6895
        assert rec_details["location"]["longitude"] == 139.6917
        assert rec_details["location"]["altitude"] == 10.5
