import json
import os
import tempfile
from pathlib import Path
from typing import Generator
import pytest

from src.lib.data.history import HistoryManager


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary DB file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    if os.path.exists(db_path):
        os.remove(db_path)
    # WALモードの関連ファイルも削除
    for suffix in ["-wal", "-shm"]:
        wal_path = db_path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)


@pytest.fixture
def history(temp_db_path) -> Generator[HistoryManager, None, None]:
    """Create a HistoryManager with a temporary database."""
    hm = HistoryManager(db_path=temp_db_path)
    yield hm
    hm.close()


# === 基本テスト ===

def test_add_and_get_record(history: HistoryManager):
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {"title": "Test"})
    
    record = history.get_record("hash1")
    assert record is not None
    assert record["file_path"] == "/tmp/test.mp4"
    assert record["video_id"] == "vid1"
    assert record["status"] == "success"
    assert record["metadata"]["title"] == "Test"


def test_is_uploaded(history: HistoryManager):
    assert not history.is_uploaded("hash1")
    
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {})
    assert history.is_uploaded("hash1")


def test_is_uploaded_by_path(history: HistoryManager):
    assert not history.is_uploaded_by_path("/tmp/test.mp4")
    
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {})
    assert history.is_uploaded_by_path("/tmp/test.mp4")


def test_add_failure(history: HistoryManager):
    history.add_failure("/tmp/fail.mp4", "hash_fail", "Some error")
    
    record = history.get_record("hash_fail")
    assert record is not None
    assert record["status"] == "failed"
    assert "Some error" in record["error"]


def test_get_failed_records(history: HistoryManager):
    history.add_record("/tmp/ok.mp4", "h_ok", "v_ok", {})
    history.add_failure("/tmp/fail1.mp4", "h_f1", "Error 1")
    history.add_failure("/tmp/fail2.mp4", "h_f2", "Error 2")
    
    failed = history.get_failed_records()
    assert len(failed) == 2
    assert all(r["status"] == "failed" for r in failed)


def test_upsert_behavior(history: HistoryManager):
    """同一 file_hash の upsert テスト（failure → success で上書き）"""
    history.add_failure("/tmp/test.mp4", "hash1", "First error")
    assert history.get_record("hash1")["status"] == "failed"
    
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {"title": "Fixed"})
    record = history.get_record("hash1")
    assert record["status"] == "success"
    assert record["video_id"] == "vid1"
    assert history.get_upload_count() == 1


def test_get_all_records_sorted(history: HistoryManager):
    import time
    history.add_record("/tmp/a.mp4", "h_a", "v_a", {})
    time.sleep(0.01)
    history.add_record("/tmp/b.mp4", "h_b", "v_b", {})
    
    records = history.get_all_records()
    assert len(records) == 2
    # タイムスタンプ降順（新しいものが先）
    assert records[0]["file_hash"] == "h_b"
    assert records[1]["file_hash"] == "h_a"


def test_get_all_records_with_limit(history: HistoryManager):
    for i in range(5):
        history.add_record(f"/tmp/{i}.mp4", f"h{i}", f"v{i}", {})
    
    records = history.get_all_records(limit=3)
    assert len(records) == 3


def test_get_record_by_video_id(history: HistoryManager):
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {})
    
    record = history.get_record_by_video_id("vid1")
    assert record is not None
    assert record["file_hash"] == "hash1"
    
    assert history.get_record_by_video_id("nonexistent") is None


def test_get_upload_count(history: HistoryManager):
    assert history.get_upload_count() == 0
    history.add_record("/tmp/a.mp4", "h1", "v1", {})
    assert history.get_upload_count() == 1
    history.add_record("/tmp/b.mp4", "h2", "v2", {})
    assert history.get_upload_count() == 2


def test_add_record_with_playlist_and_filesize(history: HistoryManager):
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {}, playlist_name="MyPlaylist", file_size=1024)
    
    record = history.get_record("hash1")
    assert record["playlist_name"] == "MyPlaylist"
    assert record["file_size"] == 1024


# === 削除テスト ===

def test_delete_record(history: HistoryManager):
    history.add_record("/tmp/test.mp4", "hash1", "vid1", {})
    assert history.delete_record("hash1")
    assert history.get_record("hash1") is None
    assert not history.delete_record("nonexistent")


def test_delete_by_path_and_video(history: HistoryManager):
    history.add_record("/tmp/p1.mp4", "h1", "v1", {})
    history.add_record("/tmp/p2.mp4", "h2", "v2", {})
    
    assert history.get_upload_count() == 2
    
    assert history.delete_record_by_path("/tmp/p1.mp4")
    assert not history.delete_record_by_path("/tmp/nonexistent.mp4")
    assert history.get_upload_count() == 1
    assert history.get_record("h1") is None
    
    assert history.delete_record_by_video_id("v2")
    assert not history.delete_record_by_video_id("nonexistent")
    assert history.get_upload_count() == 0
    assert history.get_record("h2") is None


# === Export / Import テスト ===

def test_export_records_json(history: HistoryManager):
    history.add_record("/tmp/e1.mp4", "exp_h1", "exp_v1", {"title": "Export Test"})
    history.add_record("/tmp/e2.mp4", "exp_h2", "exp_v2", {})

    content = history.export_records(format="json")
    data = json.loads(content)

    assert len(data) == 2
    hashes = {d["file_hash"] for d in data}
    assert "exp_h1" in hashes
    assert "exp_h2" in hashes


def test_export_records_csv(history: HistoryManager):
    import csv
    import io

    history.add_record("/tmp/c1.mp4", "csv_h1", "csv_v1", {})

    content = history.export_records(format="csv")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["file_hash"] == "csv_h1"
    assert rows[0]["video_id"] == "csv_v1"


def test_export_records_to_file(history: HistoryManager, tmp_path):
    history.add_record("/tmp/f1.mp4", "file_h1", "file_v1", {})

    output_path = str(tmp_path / "export.json")
    history.export_records(format="json", output_path=output_path)

    with open(output_path, "r") as f:
        data = json.loads(f.read())
    assert len(data) == 1
    assert data[0]["file_hash"] == "file_h1"


def test_import_records(history: HistoryManager):
    records = [
        {"file_path": "/tmp/i1.mp4", "file_hash": "imp_h1", "video_id": "imp_v1", "status": "success"},
        {"file_path": "/tmp/i2.mp4", "file_hash": "imp_h2", "video_id": "imp_v2", "status": "success"},
    ]

    imported, skipped = history.import_records(records)

    assert imported == 2
    assert skipped == 0
    assert history.get_upload_count() == 2
    assert history.get_record("imp_h1") is not None


def test_import_records_duplicate_skip(history: HistoryManager):
    history.add_record("/tmp/dup.mp4", "dup_h1", "dup_v1", {})

    records = [
        {"file_path": "/tmp/dup.mp4", "file_hash": "dup_h1", "video_id": "dup_v1", "status": "success"},
        {"file_path": "/tmp/new.mp4", "file_hash": "new_h1", "video_id": "new_v1", "status": "success"},
    ]

    imported, skipped = history.import_records(records)

    assert imported == 1
    assert skipped == 1
    assert history.get_upload_count() == 2


def test_import_records_no_hash(history: HistoryManager):
    records = [
        {"file_path": "/tmp/nohash.mp4", "video_id": "v1"},
    ]

    imported, skipped = history.import_records(records)

    assert imported == 0
    assert skipped == 1


# === TinyDB マイグレーションテスト ===

def test_migrate_from_tinydb(tmp_path):
    """既存の upload_history.json から自動マイグレーションするテスト"""
    # TinyDB形式のJSONを作成
    tinydb_data = {
        "uploads": {
            "1": {
                "file_path": "/tmp/old.mp4",
                "file_hash": "old_hash",
                "video_id": "old_vid",
                "metadata": {"title": "Old Video"},
                "timestamp": 1700000000,
                "status": "success",
                "error": None,
                "playlist_name": "OldPlaylist",
                "file_size": 2048,
            },
            "2": {
                "file_path": "/tmp/old2.mp4",
                "file_hash": "old_hash2",
                "video_id": "old_vid2",
                "metadata": {},
                "timestamp": 1700000100,
                "status": "failed",
                "error": "Quota Exceeded",
                "playlist_name": None,
                "file_size": 0,
            },
        }
    }

    json_path = tmp_path / "upload_history.json"
    json_path.write_text(json.dumps(tinydb_data))

    db_path = tmp_path / "upload_history.db"
    hm = HistoryManager(db_path=str(db_path))

    try:
        assert hm.get_upload_count() == 2

        record1 = hm.get_record("old_hash")
        assert record1 is not None
        assert record1["video_id"] == "old_vid"
        assert record1["metadata"]["title"] == "Old Video"
        assert record1["playlist_name"] == "OldPlaylist"
        assert record1["file_size"] == 2048

        record2 = hm.get_record("old_hash2")
        assert record2 is not None
        assert record2["status"] == "failed"
        assert record2["error"] == "Quota Exceeded"
    finally:
        hm.close()
