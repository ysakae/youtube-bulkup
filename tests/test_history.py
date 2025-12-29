import pytest
import os
from src.history import HistoryManager
from tinydb import TinyDB

class TestHistoryManager:
    def test_init(self, tmp_path, mocker):
        """Test initialization creates DB."""
        db_path = tmp_path / "test_history.json"
        mocker.patch("src.history.config.history_db", str(db_path))
        
        history = HistoryManager()
        assert os.path.exists(db_path)

    def test_add_and_check_record(self, tmp_path, mocker):
        """Test adding a record and checking for existence."""
        db_path = tmp_path / "test_history.json"
        mocker.patch("src.history.config.history_db", str(db_path))
        
        history = HistoryManager()
        
        file_path = "/path/to/video.mp4"
        file_hash = "abc123hash"
        video_id = "vid123"
        metadata = {"title": "Test Video"}
        
        # Should be empty initially
        assert history.is_uploaded(file_hash) is False
        
        # Add record
        history.add_record(file_path, file_hash, video_id, metadata)
        
        # Should be found now
        assert history.is_uploaded(file_hash) is True
        
        # Verify stored data
        record = history.table.all()[0]
        assert record["file_hash"] == file_hash
        assert record["video_id"] == video_id
