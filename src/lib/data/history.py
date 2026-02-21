import csv
import io
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import config

logger = logging.getLogger("youtube_up")

# アップロード履歴テーブルのスキーマ
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    video_id TEXT,
    metadata TEXT DEFAULT '{}',
    timestamp REAL DEFAULT 0,
    status TEXT DEFAULT 'success',
    error TEXT,
    playlist_name TEXT,
    file_size INTEGER DEFAULT 0
);
"""

# パフォーマンス向上のためのインデックス
_CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_file_hash ON uploads (file_hash);",
    "CREATE INDEX IF NOT EXISTS idx_file_path ON uploads (file_path);",
    "CREATE INDEX IF NOT EXISTS idx_video_id ON uploads (video_id);",
    "CREATE INDEX IF NOT EXISTS idx_status ON uploads (status);",
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON uploads (timestamp);",
]


class HistoryManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.history_db
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # WALモードで並行読み取り性能を向上
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()
        self._migrate_from_tinydb()

    def _init_schema(self):
        """テーブルとインデックスを作成する。"""
        self.conn.execute(_CREATE_TABLE_SQL)
        for idx_sql in _CREATE_INDEX_SQL:
            self.conn.execute(idx_sql)
        self.conn.commit()

    def _migrate_from_tinydb(self):
        """
        既存の TinyDB (JSON) ファイルからデータを自動移行する。
        同じディレクトリ内の upload_history.json を検出し、
        まだ移行されていなければデータを読み込んでSQLiteに挿入する。
        """
        # JSONファイルのパスを推定（同ディレクトリ内のみ検索）
        db_dir = Path(self.db_path).parent
        json_candidates = [
            db_dir / "upload_history.json",
        ]

        json_path = None
        for candidate in json_candidates:
            if candidate.exists() and candidate.stat().st_size > 10:
                json_path = candidate
                break

        if not json_path:
            return

        # 既にデータがあるならマイグレーション済みとみなす
        cursor = self.conn.execute("SELECT COUNT(*) FROM uploads")
        count = cursor.fetchone()[0]
        if count > 0:
            return

        logger.info(f"TinyDB からの移行を開始: {json_path}")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # TinyDB の形式: {"uploads": {"1": {...}, "2": {...}, ...}}
            # または {"_default": {...}} の場合もある
            records = []
            if isinstance(data, dict):
                # "uploads" テーブルを探す
                table_data = data.get("uploads", data.get("_default", {}))
                if isinstance(table_data, dict):
                    records = list(table_data.values())
                elif isinstance(table_data, list):
                    records = table_data
            elif isinstance(data, list):
                records = data

            if not records:
                logger.warning("JSONファイルにレコードが見つかりませんでした。")
                return

            migrated = 0
            for record in records:
                if not isinstance(record, dict):
                    continue
                file_hash = record.get("file_hash")
                if not file_hash:
                    continue

                metadata_json = json.dumps(record.get("metadata", {}), ensure_ascii=False)

                self.conn.execute(
                    """INSERT INTO uploads
                       (file_path, file_hash, video_id, metadata, timestamp, status, error, playlist_name, file_size)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.get("file_path", ""),
                        file_hash,
                        record.get("video_id"),
                        metadata_json,
                        record.get("timestamp", 0),
                        record.get("status", "success"),
                        record.get("error"),
                        record.get("playlist_name"),
                        record.get("file_size", 0),
                    ),
                )
                migrated += 1

            self.conn.commit()
            logger.info(f"TinyDB からの移行完了: {migrated} 件のレコードを移行しました。")

        except Exception as e:
            logger.error(f"TinyDB からの移行に失敗: {e}")
            self.conn.rollback()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """sqlite3.Row を辞書に変換。metadata は JSON デシリアライズする。"""
        d = dict(row)
        # metadata をJSONからパース
        meta_str = d.get("metadata", "{}")
        try:
            d["metadata"] = json.loads(meta_str) if meta_str else {}
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
        return d

    def is_uploaded(self, file_hash: str) -> bool:
        """Check if a file with the given hash has already been successfully uploaded."""
        cursor = self.conn.execute(
            "SELECT 1 FROM uploads WHERE file_hash = ? AND status = 'success' LIMIT 1",
            (file_hash,),
        )
        return cursor.fetchone() is not None

    def is_uploaded_by_path(self, file_path: str) -> bool:
        """Check if a file with the given path has already been successfully uploaded."""
        cursor = self.conn.execute(
            "SELECT 1 FROM uploads WHERE file_path = ? AND status = 'success' LIMIT 1",
            (str(file_path),),
        )
        return cursor.fetchone() is not None

    def add_record(
        self,
        file_path: str,
        file_hash: str,
        video_id: str,
        metadata: Dict[str, Any],
        playlist_name: Optional[str] = None,
        file_size: int = 0,
    ):
        """Record a successful upload. file_hash が既存なら上書き (upsert)。"""
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        now = time.time()

        # 既存レコードがあれば更新、なければ挿入
        existing = self.conn.execute(
            "SELECT id FROM uploads WHERE file_hash = ? LIMIT 1", (file_hash,)
        ).fetchone()

        if existing:
            self.conn.execute(
                """UPDATE uploads SET
                   file_path=?, video_id=?, metadata=?, timestamp=?,
                   status='success', error=NULL, playlist_name=?, file_size=?
                   WHERE file_hash=?""",
                (str(file_path), video_id, metadata_json, now, playlist_name, file_size, file_hash),
            )
        else:
            self.conn.execute(
                """INSERT INTO uploads
                   (file_path, file_hash, video_id, metadata, timestamp, status, error, playlist_name, file_size)
                   VALUES (?, ?, ?, ?, ?, 'success', NULL, ?, ?)""",
                (str(file_path), file_hash, video_id, metadata_json, now, playlist_name, file_size),
            )
        self.conn.commit()
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
        metadata_json = json.dumps({}, ensure_ascii=False)
        now = time.time()

        existing = self.conn.execute(
            "SELECT id FROM uploads WHERE file_hash = ? LIMIT 1", (file_hash,)
        ).fetchone()

        if existing:
            self.conn.execute(
                """UPDATE uploads SET
                   file_path=?, video_id=NULL, metadata=?, timestamp=?,
                   status='failed', error=?, playlist_name=?, file_size=?
                   WHERE file_hash=?""",
                (str(file_path), metadata_json, now, str(error_msg), playlist_name, file_size, file_hash),
            )
        else:
            self.conn.execute(
                """INSERT INTO uploads
                   (file_path, file_hash, video_id, metadata, timestamp, status, error, playlist_name, file_size)
                   VALUES (?, ?, NULL, ?, ?, 'failed', ?, ?, ?)""",
                (str(file_path), file_hash, metadata_json, now, str(error_msg), playlist_name, file_size),
            )
        self.conn.commit()
        logger.warning(f"Recorded upload failure for {file_path}")

    def delete_record(self, file_hash: str) -> bool:
        """Delete an upload record by file hash. Returns True if record was found and deleted."""
        cursor = self.conn.execute("DELETE FROM uploads WHERE file_hash = ?", (file_hash,))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Deleted upload history for hash {file_hash}")
            return True
        return False

    def delete_record_by_path(self, file_path: str) -> bool:
        """Delete an upload record by file path. Returns True if record was found and deleted."""
        cursor = self.conn.execute("DELETE FROM uploads WHERE file_path = ?", (str(file_path),))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Deleted upload history for path {file_path}")
            return True
        return False

    def delete_record_by_video_id(self, video_id: str) -> bool:
        """Delete an upload record by video ID. Returns True if record was found and deleted."""
        cursor = self.conn.execute("DELETE FROM uploads WHERE video_id = ?", (video_id,))
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Deleted upload history for video ID {video_id}")
            return True
        return False

    def get_record(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Get an upload record by file hash."""
        cursor = self.conn.execute(
            "SELECT * FROM uploads WHERE file_hash = ? LIMIT 1", (file_hash,)
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def get_record_by_video_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get an upload record by video ID."""
        cursor = self.conn.execute(
            "SELECT * FROM uploads WHERE video_id = ? LIMIT 1", (video_id,)
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def get_upload_count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM uploads")
        return cursor.fetchone()[0]

    def get_all_records(self, limit: Optional[int] = None) -> list:
        """Get all upload records, sorted by timestamp descending."""
        if limit and limit > 0:
            cursor = self.conn.execute(
                "SELECT * FROM uploads ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        else:
            cursor = self.conn.execute("SELECT * FROM uploads ORDER BY timestamp DESC")
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_failed_records(self) -> list:
        """Get all failed upload records."""
        cursor = self.conn.execute(
            "SELECT * FROM uploads WHERE status = 'failed' ORDER BY timestamp DESC"
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def export_records(self, format: str = "json", output_path: str = None) -> str:
        """
        全レコードをJSON/CSV形式でエクスポートする。
        output_path が指定された場合はファイルに書き出し、
        指定されない場合は文字列として返す。
        """
        records = self.get_all_records()

        if format == "csv":
            output = io.StringIO()
            if records:
                fieldnames = [
                    "file_path", "file_hash", "video_id", "status",
                    "timestamp", "error", "playlist_name", "file_size",
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                for record in records:
                    # metadata は複雑な構造なので CSV からは除外
                    row = {k: record.get(k, "") for k in fieldnames}
                    writer.writerow(row)
            content = output.getvalue()
        else:
            # JSON形式
            clean_records = []
            for record in records:
                # 内部ID (id) を除外してクリーンなエクスポート
                clean = {k: v for k, v in record.items() if k != "id"}
                clean_records.append(clean)
            content = json.dumps(clean_records, indent=2, ensure_ascii=False)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Exported {len(records)} records to {output_path}")

        return content

    def import_records(self, records: list) -> tuple:
        """
        レコードリストをインポートする。
        file_hash が既に存在するレコードはスキップする。
        Returns: (imported_count, skipped_count)
        """
        imported = 0
        skipped = 0

        for record in records:
            file_hash = record.get("file_hash")
            if not file_hash:
                logger.warning(f"Skipping record without file_hash: {record}")
                skipped += 1
                continue

            # 既存チェック（hash重複スキップ）
            existing = self.get_record(file_hash)
            if existing:
                logger.debug(f"Skipping existing record: {file_hash}")
                skipped += 1
                continue

            # レコードを挿入
            metadata_json = json.dumps(record.get("metadata", {}), ensure_ascii=False)
            self.conn.execute(
                """INSERT INTO uploads
                   (file_path, file_hash, video_id, metadata, timestamp, status, error, playlist_name, file_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("file_path", ""),
                    file_hash,
                    record.get("video_id"),
                    metadata_json,
                    record.get("timestamp", time.time()),
                    record.get("status", "success"),
                    record.get("error"),
                    record.get("playlist_name"),
                    record.get("file_size", 0),
                ),
            )
            imported += 1

        self.conn.commit()
        logger.info(f"Imported {imported} records, skipped {skipped}")
        return imported, skipped

    def close(self):
        """Close the database connection."""
        self.conn.close()
