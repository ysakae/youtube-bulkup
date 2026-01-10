import logging
import time
from typing import Any, Dict, Optional

from tinydb import Query, TinyDB

from ..core.config import config

logger = logging.getLogger("youtube_up")


class HistoryManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.history_db
        self.db = TinyDB(
            self.db_path, indent=4, separators=(",", ": "), encoding="utf-8"
        )
        self.table = self.db.table("uploads")
        self.table = self.db.table("uploads")
        self._migrate_schema_v2()
        self._migrate_schema_v3()

    def _migrate_schema_v2(self):
        """
        Migrate existing records to include 'playlist_name' field if missing.
        """
        # This is strictly optional if we use .get('playlist_name') everywhere,
        # but good for consistency.
        current_records = self.table.all()
        updates = []
        for record in current_records:

            if "playlist_name" not in record or record["playlist_name"] is None:
                # Infer from file parent name if possible
                file_path_str = record.get("file_path")
                new_playlist_name = None
                if file_path_str:
                    try:
                        from pathlib import Path
                        new_playlist_name = Path(file_path_str).parent.name
                    except Exception:
                        pass
                
                updates.append((record.doc_id, {"playlist_name": new_playlist_name}))
        
        if updates:
            logger.info(f"Migrating {len(updates)} records to schema v2 (add playlist_name)...")

            
            # Simple loop update
            for doc_id, change in updates:
                self.table.update(change, doc_ids=[doc_id])

    def _migrate_schema_v3(self):
        """
        Migrate existing records to include 'file_size' field if missing.
        Backfill from actual file system if possible.
        """
        current_records = self.table.all()
        updates = []
        for record in current_records:
            if "file_size" not in record:
                file_path_str = record.get("file_path")
                size = 0
                if file_path_str:
                    try:
                        from pathlib import Path
                        p = Path(file_path_str)
                        if p.exists():
                            size = p.stat().st_size
                    except Exception:
                        pass
                updates.append((record.doc_id, {"file_size": size}))
        
        if updates:
            logger.info(f"Migrating {len(updates)} records to schema v3 (add file_size)...")
            for doc_id, change in updates:
                self.table.update(change, doc_ids=[doc_id])

    def is_uploaded(self, file_hash: str) -> bool:
        """Check if a file with the given hash has already been successfully uploaded."""
        File = Query()
        return self.table.contains(
            (File.file_hash == file_hash) & (File.status == "success")
        )

    def is_uploaded_by_path(self, file_path: str) -> bool:
        """Check if a file with the given path has already been successfully uploaded."""
        File = Query()
        # Ensure we use exact string match for the path
        return self.table.contains(
            (File.file_path == str(file_path)) & (File.status == "success")
        )


    def add_record(
        self,
        file_path: str,
        file_hash: str,
        video_id: str,
        metadata: Dict[str, Any],
        playlist_name: Optional[str] = None,
        file_size: int = 0,
    ):
        """Record a successful upload."""
        File = Query()
        self.table.upsert(
            {
                "file_path": str(file_path),
                "file_hash": file_hash,
                "video_id": video_id,
                "metadata": metadata,
                "timestamp": time.time(),
                "status": "success",
                "error": None,
                "playlist_name": playlist_name,
                "file_size": file_size,
            },
            File.file_hash == file_hash,
        )
        logger.info(f"Recorded upload history for {file_path}")

    def add_failure(
        self,
        file_path: str,
        file_hash: str,
        error_msg: str,
        playlist_name: Optional[str] = None,
        file_size: int = 0,
    ):
        """Record a failed upload."""
        File = Query()
        self.table.upsert(
            {
                "file_path": str(file_path),
                "file_hash": file_hash,
                "video_id": None,
                "metadata": {},
                "timestamp": time.time(),
                "status": "failed",
                "error": str(error_msg),
                "playlist_name": playlist_name,
                "file_size": file_size,
            },
            File.file_hash == file_hash,
        )
        logger.warning(f"Recorded upload failure for {file_path}")

    def delete_record(self, file_hash: str) -> bool:
        """Delete an upload record by file hash. Returns True if record was found and deleted."""
        File = Query()
        deleted_ids = self.table.remove(File.file_hash == file_hash)
        if deleted_ids:
            logger.info(f"Deleted upload history for hash {file_hash}")
            return True
        return False

    def delete_record_by_path(self, file_path: str) -> bool:
        """Delete an upload record by file path. Returns True if record was found and deleted."""
        File = Query()
        # TinyDB path matching should be exact string match
        deleted_ids = self.table.remove(File.file_path == str(file_path))
        if deleted_ids:
            logger.info(f"Deleted upload history for path {file_path}")
            return True
        return False

    def delete_record_by_video_id(self, video_id: str) -> bool:
        """Delete an upload record by video ID. Returns True if record was found and deleted."""
        File = Query()
        deleted_ids = self.table.remove(File.video_id == video_id)
        if deleted_ids:
            logger.info(f"Deleted upload history for video ID {video_id}")
            return True
        return False

    def get_record(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Get an upload record by file hash."""
        File = Query()
        result = self.table.search(File.file_hash == file_hash)
        return result[0] if result else None

    def get_record_by_video_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get an upload record by video ID."""
        File = Query()
        result = self.table.search(File.video_id == video_id)
        return result[0] if result else None

    def get_upload_count(self) -> int:
        return len(self.table)

    def get_all_records(self, limit: Optional[int] = None) -> list:
        """Get all upload records, sorted by timestamp descending."""
        records = self.table.all()
        # Sort by timestamp desc, handling missing timestamps
        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        if limit and limit > 0:
            return records[:limit]
        return records

    def get_failed_records(self) -> list:
        """Get all failed upload records."""
        File = Query()
        return self.table.search(File.status == "failed")

    def close(self):
        """Close the database connection."""
        self.db.close()

