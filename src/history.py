import logging
import time
from typing import Any, Dict, Optional

from tinydb import Query, TinyDB

from .config import config

logger = logging.getLogger("youtube_up")


class HistoryManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.history_db
        self.db = TinyDB(self.db_path)
        self.table = self.db.table("uploads")

    def is_uploaded(self, file_hash: str) -> bool:
        """Check if a file with the given hash has already been successfully uploaded."""
        File = Query()
        return self.table.contains(
            (File.file_hash == file_hash) & (File.status == "success")
        )

    def add_record(
        self, file_path: str, file_hash: str, video_id: str, metadata: Dict[str, Any]
    ):
        """Record a successful upload."""
        self.table.insert(
            {
                "file_path": str(file_path),
                "file_hash": file_hash,
                "video_id": video_id,
                "metadata": metadata,
                "timestamp": time.time(),
                "status": "success",
            }
        )
        logger.info(f"Recorded upload history for {file_path}")

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
