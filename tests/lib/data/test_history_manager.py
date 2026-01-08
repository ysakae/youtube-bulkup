import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Generator
import pytest
from tinydb import TinyDB, Query

from src.lib.data.history import HistoryManager


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary DB file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def history(temp_db_path: str) -> Generator[HistoryManager, None, None]:
    manager = HistoryManager(db_path=temp_db_path)
    yield manager
    manager.close()


def test_add_and_check_record(history: HistoryManager):
    file_path = "/tmp/test.mp4"
    file_hash = "abc123hash"
    video_id = "vid123"
    metadata = {"title": "Test Video"}

    assert not history.is_uploaded(file_hash)

    history.add_record(file_path, file_hash, video_id, metadata)

    assert history.is_uploaded(file_hash)
    assert history.is_uploaded(file_hash)
    assert history.get_upload_count() == 1


def test_is_uploaded_by_path(history: HistoryManager):
    file_path = "/tmp/path_test.mp4"
    file_hash = "path_hash"
    video_id = "vid_path"
    metadata = {}

    assert not history.is_uploaded_by_path(file_path)

    history.add_record(file_path, file_hash, video_id, metadata)

    assert history.is_uploaded_by_path(file_path)
    assert not history.is_uploaded_by_path("/tmp/other.mp4")


def test_add_failure(history: HistoryManager):
    file_path = "/tmp/fail.mp4"
    file_hash = "fail_hash"
    error_msg = "Network Error"

    history.add_failure(file_path, file_hash, error_msg)

    assert not history.is_uploaded(file_hash)
    assert history.get_upload_count() == 1
    
    failed = history.get_failed_records()
    assert len(failed) == 1
    assert failed[0]["file_hash"] == file_hash
    assert failed[0]["status"] == "failed"
    assert failed[0]["error"] == error_msg


def test_delete_record(history: HistoryManager):
    file_path = "/tmp/del.mp4"
    file_hash = "del_hash"
    history.add_record(file_path, file_hash, "vid", {})

    assert history.is_uploaded(file_hash)
    
    # Delete existing
    assert history.delete_record(file_hash) is True
    assert not history.is_uploaded(file_hash)
    assert history.get_upload_count() == 0

    # Delete non-existing
    assert history.delete_record("non_existent") is False


def test_get_record(history: HistoryManager):
    file_path = "/tmp/get.mp4"
    file_hash = "get_hash"
    history.add_record(file_path, file_hash, "vid", {})

    record = history.get_record(file_hash)
    assert record is not None
    assert record["file_hash"] == file_hash
    
    assert history.get_record("non_existent") is None


def test_get_record_by_video_id(history: HistoryManager):
    file_path = "/tmp/vid.mp4"
    file_hash = "vid_hash"
    video_id = "target_vid"
    history.add_record(file_path, file_hash, video_id, {})

    record = history.get_record_by_video_id(video_id)
    assert record is not None
    assert record["video_id"] == video_id
    
    assert history.get_record_by_video_id("non_existent") is None


def test_get_all_records(history: HistoryManager):
    history.add_record("f1", "h1", "v1", {})
    time.sleep(0.01) # ensure timestamp diff
    history.add_record("f2", "h2", "v2", {})
    
    records = history.get_all_records()
    assert len(records) == 2
    # Should be sorted by timestamp desc (newest first)
    assert records[0]["file_hash"] == "h2"
    assert records[1]["file_hash"] == "h1"

    # Test limit
    records_limit = history.get_all_records(limit=1)
    assert len(records_limit) == 1
    assert records_limit[0]["file_hash"] == "h2"


def test_schema_migration_v2(temp_db_path):
    """Test that old records without playlist_name are migrated."""
    # 1. Create DB with old schema data
    db = TinyDB(temp_db_path)
    table = db.table("uploads")
    
    # Old record: missing playlist_name
    table.insert({
        "file_path": "/Users/test/videos/my_playlist/video1.mp4",
        "file_hash": "hash1",
        "video_id": "vid1",
        "status": "success"
    })
    
    # Record that already has it (should not change)
    table.insert({
        "file_path": "/Users/test/videos/other/video2.mp4",
        "file_hash": "hash2",
        "video_id": "vid2",
        "status": "success",
        "playlist_name": "Existing Playlist"
    })
    
    # Record with no file path (cannot infer)
    table.insert({
        "file_path": None,
        "file_hash": "hash3",
        "video_id": "vid3",
        "status": "success"
    })
    
    db.close()
    
    # 2. Initialize HistoryManager (triggers migration)
    manager = HistoryManager(db_path=temp_db_path)
    
    # 3. Verify
    rec1 = manager.get_record("hash1")
    assert rec1["playlist_name"] == "my_playlist"
    
    rec2 = manager.get_record("hash2")
    assert rec2["playlist_name"] == "Existing Playlist"
    
    rec3 = manager.get_record("hash3")
    assert rec3.get("playlist_name") is None
    
    manager.close()


def test_delete_by_path_and_video(history: HistoryManager):
    # Setup
    history.add_record("/tmp/p1.mp4", "h1", "v1", {})
    history.add_record("/tmp/p2.mp4", "h2", "v2", {})
    
    assert history.get_upload_count() == 2
    
    # Delete by path
    assert history.delete_record_by_path("/tmp/p1.mp4")
    assert not history.delete_record_by_path("/tmp/nonexistent.mp4")
    assert history.get_upload_count() == 1
    assert history.get_record("h1") is None
    
    # Delete by video_id
    assert history.delete_record_by_video_id("v2")
    assert not history.delete_record_by_video_id("nonexistent")
    assert history.get_upload_count() == 0
    assert history.get_record("h2") is None

