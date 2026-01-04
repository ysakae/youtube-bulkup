import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest
from tinydb import TinyDB

from src.history import HistoryManager


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary DB file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def history(temp_db_path: str) -> HistoryManager:
    return HistoryManager(db_path=temp_db_path)


def test_add_and_check_record(history: HistoryManager):
    file_path = "/tmp/test.mp4"
    file_hash = "abc123hash"
    video_id = "vid123"
    metadata = {"title": "Test Video"}

    assert not history.is_uploaded(file_hash)

    history.add_record(file_path, file_hash, video_id, metadata)

    assert history.is_uploaded(file_hash)
    assert history.get_upload_count() == 1


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
