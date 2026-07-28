"""YouTube 側の状態をローカルにキャッシュするスナップショット。

アップロード履歴 (HistoryManager) とは責務が異なるため、別の SQLite ファイルに保存する。
こちらは「リモートの状態の写し」であり、いつ捨てても再取得できる。
"""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("youtube_up")

# 鮮度管理の単位
KINDS = ("playlists", "playlist_items", "videos")

_CREATE_SQL = [
    """CREATE TABLE IF NOT EXISTS playlists (
        playlist_id  TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        item_count   INTEGER DEFAULT 0,
        privacy      TEXT,
        published_at TEXT,
        fetched_at   REAL NOT NULL
    );""",
    """CREATE TABLE IF NOT EXISTS playlist_items (
        playlist_id TEXT NOT NULL,
        video_id    TEXT NOT NULL,
        fetched_at  REAL NOT NULL,
        PRIMARY KEY (playlist_id, video_id)
    );""",
    """CREATE TABLE IF NOT EXISTS empty_playlists (
        playlist_id TEXT PRIMARY KEY,
        fetched_at  REAL NOT NULL
    );""",
    """CREATE TABLE IF NOT EXISTS videos (
        video_id   TEXT PRIMARY KEY,
        title      TEXT,
        privacy    TEXT,
        fetched_at REAL NOT NULL
    );""",
    """CREATE TABLE IF NOT EXISTS cache_meta (
        kind       TEXT PRIMARY KEY,
        fetched_at REAL NOT NULL
    );""",
    "CREATE INDEX IF NOT EXISTS idx_playlists_title ON playlists (title);",
    "CREATE INDEX IF NOT EXISTS idx_items_video ON playlist_items (video_id);",
]


class SnapshotCache:
    """YouTube の playlists / playlist items / videos のスナップショット。"""

    def __init__(self, db_path: Optional[str] = None, ttl_hours: int = 24) -> None:
        self.db_path = db_path or "youtube_cache.db"
        self.ttl_seconds = max(0, ttl_hours) * 3600
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        for sql in _CREATE_SQL:
            self.conn.execute(sql)
        self.conn.commit()

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"Unknown cache kind: {kind}")

    # --- 鮮度管理 ---

    def is_fresh(self, kind: str) -> bool:
        """全件取得が完了しており、かつ TTL 内かを判定する。

        保存しただけでは新鮮とみなさない。取得が途中で中断した場合に
        部分的なデータを「完全」と誤認しないため。
        """
        self._validate_kind(kind)
        row = self.conn.execute(
            "SELECT fetched_at FROM cache_meta WHERE kind = ?", (kind,)
        ).fetchone()
        if row is None:
            return False
        return (time.time() - row["fetched_at"]) < self.ttl_seconds

    def mark_complete(self, kind: str) -> None:
        """全件取得の完了を記録する。取得ループを完走したときだけ呼ぶこと。"""
        self._validate_kind(kind)
        self.conn.execute(
            "INSERT INTO cache_meta (kind, fetched_at) VALUES (?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET fetched_at = excluded.fetched_at",
            (kind, time.time()),
        )
        self.conn.commit()

    # --- playlists ---

    def save_playlists(self, playlists: List[Dict[str, Any]]) -> None:
        """プレイリスト一覧を全置換で保存する。"""
        now = time.time()
        self.conn.execute("DELETE FROM playlists")
        self.conn.executemany(
            "INSERT INTO playlists "
            "(playlist_id, title, item_count, privacy, published_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    p["id"],
                    p.get("title", ""),
                    p.get("item_count", 0),
                    p.get("privacy"),
                    p.get("published_at"),
                    now,
                )
                for p in playlists
            ],
        )
        self.conn.commit()

    def load_playlists(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT playlist_id, title, item_count, privacy, published_at FROM playlists"
        ).fetchall()
        return [
            {
                "id": r["playlist_id"],
                "title": r["title"],
                "item_count": r["item_count"],
                "privacy": r["privacy"],
                "published_at": r["published_at"],
            }
            for r in rows
        ]

    # --- playlist items ---

    def save_playlist_items(self, playlist_id: str, video_ids: Set[str]) -> None:
        """指定プレイリストの中身を全置換で保存する。

        空のプレイリストも「取得済みで空」として記録する
        (未取得と区別するため empty_playlists に印を残す)。
        """
        now = time.time()
        self.conn.execute(
            "DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,)
        )
        self.conn.execute(
            "DELETE FROM empty_playlists WHERE playlist_id = ?", (playlist_id,)
        )
        if video_ids:
            self.conn.executemany(
                "INSERT INTO playlist_items (playlist_id, video_id, fetched_at) "
                "VALUES (?, ?, ?)",
                [(playlist_id, vid, now) for vid in video_ids],
            )
        else:
            self.conn.execute(
                "INSERT INTO empty_playlists (playlist_id, fetched_at) VALUES (?, ?)",
                (playlist_id, now),
            )
        self.conn.commit()

    def load_playlist_map(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for row in self.conn.execute(
            "SELECT playlist_id, video_id FROM playlist_items"
        ):
            result.setdefault(row["playlist_id"], set()).add(row["video_id"])
        for row in self.conn.execute("SELECT playlist_id FROM empty_playlists"):
            result.setdefault(row["playlist_id"], set())
        return result

    # --- videos ---

    def save_videos(self, videos: List[Dict[str, Any]]) -> None:
        now = time.time()
        self.conn.execute("DELETE FROM videos")
        self.conn.executemany(
            "INSERT INTO videos (video_id, title, privacy, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            [(v["id"], v.get("title", ""), v.get("privacy"), now) for v in videos],
        )
        self.conn.commit()

    def load_videos(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT video_id, title, privacy FROM videos"
        ).fetchall()
        return [
            {"id": r["video_id"], "title": r["title"], "privacy": r["privacy"]}
            for r in rows
        ]

    # --- 管理 ---

    def clear(self, kind: Optional[str] = None) -> None:
        """キャッシュを破棄する。kind 省略時はすべて。"""
        if kind is None:
            targets = list(KINDS)
        else:
            self._validate_kind(kind)
            targets = [kind]

        for k in targets:
            if k == "playlists":
                self.conn.execute("DELETE FROM playlists")
            elif k == "playlist_items":
                self.conn.execute("DELETE FROM playlist_items")
                self.conn.execute("DELETE FROM empty_playlists")
            elif k == "videos":
                self.conn.execute("DELETE FROM videos")
            self.conn.execute("DELETE FROM cache_meta WHERE kind = ?", (k,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
