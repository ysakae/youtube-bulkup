# playlist orphans --fix の Quota 枯渇問題 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `yt-up playlist orphans --fix` がクォータを浪費せず、中断しても差分から再開できるようにし、オーファンが毎日量産される発生源を断つ。

**Architecture:** `PlaylistManager` のページネーション未対応（544個中50個しか認識しない）がオーファンの大量誤判定と重複プレイリスト生成を引き起こしているため、これを全件対応に修正する。あわせて YouTube 側の状態を SQLite にキャッシュして再実行時の読み取りを 0 にし、quota 枯渇を専用例外で検知して安全に中断・再開できるようにする。アップロード時のプレイリスト追加失敗も記録するようにして、オーファンの発生源を遮断する。

**Tech Stack:** Python 3.10+ / typer / rich / pydantic / google-api-python-client / SQLite (標準ライブラリ) / pytest / ruff

**設計書:** [docs/superpowers/specs/2026-07-28-playlist-orphans-quota-design.md](../specs/2026-07-28-playlist-orphans-quota-design.md)

## Global Constraints

- 作業ブランチは `fix/playlist-orphans-quota`。`main` に直接コミットしない
- コミットメッセージは Conventional Commits 形式・**日本語**（`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`）
- TDD を厳守する。テストを先に書き、失敗を確認してから実装する
- 型ヒントは既存コードに合わせ `typing` モジュール由来を使う（`Optional[str]`, `Dict[str, str]`, `List[X]`, `Set[str]`）。`str | None` 記法は使わない
- パッケージ管理・実行は `uv` を使う（`uv run pytest`, `uv run ruff`）。`pip` / `poetry` は使わない
- 各タスクの最後に `uv run ruff check src tests` を通す。lint エラーが残っている状態でコミットしない
- ruff 設定: `line-length = 88`, `select = ["E", "F", "I"]`（"I" = import 順序）, `ignore = ["E501"]`
- テストカバレッジは 80% 以上を維持する
- 既存テストの契約を壊さない。特に `tests/lib/video/test_playlist.py` は `manager._playlist_cache` へ**直接代入**している（138, 279, 296, 315, 418, 451行目）ため、この属性は実属性のまま残す
- API コストの定数値（設計書 2.2 より）: `*.list` = 1, `insert` = 50, `update` = 50, `delete` = 50, `videos.insert`（アップロード）= 1600
- テスト中に実際の YouTube API を呼び出さない。すべて `unittest.mock` でモックする

---

## File Structure

| ファイル | 区分 | 責務 |
|---|---|---|
| `src/lib/core/quota.py` | 新規 | quota エラー判定、`QuotaExceededError`、消費ユニットの積算 |
| `src/lib/data/snapshot.py` | 新規 | YouTube 側状態のローカルキャッシュ（専用 SQLite） |
| `src/lib/data/history.py` | 変更 | `playlist_synced` 列の追加とアクセサ |
| `src/lib/core/config.py` | 変更 | `quota` / `cache` 設定セクション |
| `src/lib/video/playlist.py` | 変更 | ページネーション対応、重複検出、quota 例外化、キャッシュ統合 |
| `src/lib/video/uploader.py` | 変更 | quota 判定を `core/quota.py` に一本化 |
| `src/commands/playlist.py` | 変更 | `orphans` の改修、`dedupe` の新設 |
| `src/services/upload_manager.py` | 変更 | プレイリスト追加の成否記録 |

テストは対応する `tests/` 配下に置く。`tests/lib/video/test_playlist.py` は `unittest.TestCase` スタイル、`tests/lib/data/` は pytest fixture スタイルという既存の慣習に従う。

---

## Task 1: quota モジュール

**Files:**
- Create: `src/lib/core/quota.py`
- Test: `tests/lib/core/test_quota.py`

**Interfaces:**
- Consumes: なし（他が依存する土台）
- Produces:
  - `QuotaExceededError(Exception)`
  - `is_quota_error(exception: BaseException) -> bool`
  - `COSTS: Dict[str, int]` — `{"list": 1, "insert": 50, "update": 50, "delete": 50, "upload": 1600}`
  - `QuotaLedger(budget: int)` — `.budget`, `.spent`, `.remaining`（すべて `int` プロパティ）、`.cost_of(op: str, count: int = 1) -> int`、`.can_afford(op: str, count: int = 1) -> bool`、`.charge(op: str, count: int = 1) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/core/test_quota.py` を新規作成:

```python
import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.lib.core.quota import (
    COSTS,
    QuotaExceededError,
    QuotaLedger,
    is_quota_error,
)


def _http_error(status: int, content: str) -> HttpError:
    """指定のステータスと本文を持つ HttpError を組み立てる。"""
    resp = httplib2.Response({"status": status})
    resp.status = status
    return HttpError(resp, content.encode("utf-8"))


class TestIsQuotaError:
    def test_403_quota_exceeded(self):
        err = _http_error(403, '{"error": {"errors": [{"reason": "quotaExceeded"}]}}')
        assert is_quota_error(err) is True

    def test_429_video_uploads_per_day(self):
        err = _http_error(429, "The user has exceeded the number of Video Uploads per day.")
        assert is_quota_error(err) is True

    def test_400_upload_limit_exceeded(self):
        err = _http_error(400, '{"error": {"errors": [{"reason": "uploadLimitExceeded"}]}}')
        assert is_quota_error(err) is True

    def test_403_without_quota_reason_is_not_quota_error(self):
        """403 でも forbidden 等の別理由はクォータ枯渇ではない。"""
        err = _http_error(403, '{"error": {"errors": [{"reason": "forbidden"}]}}')
        assert is_quota_error(err) is False

    def test_transient_429_is_not_quota_error(self):
        """一時的なレート制限はクォータ枯渇ではない (リトライで回復しうる)。"""
        err = _http_error(429, "Too Many Requests")
        assert is_quota_error(err) is False

    def test_500_is_not_quota_error(self):
        err = _http_error(500, "Internal Server Error")
        assert is_quota_error(err) is False

    def test_non_http_error_is_not_quota_error(self):
        assert is_quota_error(ValueError("boom")) is False


class TestQuotaLedger:
    def test_initial_state(self):
        ledger = QuotaLedger(10000)
        assert ledger.budget == 10000
        assert ledger.spent == 0
        assert ledger.remaining == 10000

    def test_negative_budget_is_clamped_to_zero(self):
        ledger = QuotaLedger(-500)
        assert ledger.budget == 0
        assert ledger.remaining == 0

    def test_cost_of_uses_documented_costs(self):
        ledger = QuotaLedger(10000)
        assert ledger.cost_of("list") == 1
        assert ledger.cost_of("insert") == 50
        assert ledger.cost_of("delete") == 50
        assert ledger.cost_of("update") == 50
        assert ledger.cost_of("upload") == 1600
        assert ledger.cost_of("insert", 3) == 150

    def test_cost_of_unknown_op_raises(self):
        ledger = QuotaLedger(10000)
        with pytest.raises(ValueError, match="Unknown quota operation"):
            ledger.cost_of("teleport")

    def test_charge_accumulates(self):
        ledger = QuotaLedger(10000)
        ledger.charge("insert")
        ledger.charge("list", 5)
        assert ledger.spent == 55
        assert ledger.remaining == 9945

    def test_charge_exactly_to_budget_succeeds(self):
        """予算ちょうどは通す (境界値)。"""
        ledger = QuotaLedger(100)
        ledger.charge("insert", 2)
        assert ledger.spent == 100
        assert ledger.remaining == 0

    def test_charge_over_budget_raises_and_does_not_accumulate(self):
        ledger = QuotaLedger(100)
        ledger.charge("insert")
        with pytest.raises(QuotaExceededError):
            ledger.charge("insert", 2)
        assert ledger.spent == 50, "超過した charge は計上されない"

    def test_can_afford(self):
        ledger = QuotaLedger(100)
        assert ledger.can_afford("insert", 2) is True
        assert ledger.can_afford("insert", 3) is False
        ledger.charge("insert")
        assert ledger.can_afford("insert", 2) is False
        assert ledger.can_afford("insert") is True

    def test_costs_table_is_exposed(self):
        assert COSTS["insert"] == 50
        assert COSTS["list"] == 1
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/core/test_quota.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.lib.core.quota'`

- [ ] **Step 3: 実装を書く**

`src/lib/core/quota.py` を新規作成:

```python
"""YouTube Data API のクォータ管理。

クォータ枯渇の判定と、ローカルでの消費ユニット見積もりを提供する。
コストの根拠: https://developers.google.com/youtube/v3/determine_quota_cost
"""

import logging
from typing import Dict

from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_up")

# 操作あたりの消費ユニット
COSTS: Dict[str, int] = {
    "list": 1,
    "insert": 50,
    "update": 50,
    "delete": 50,
    "upload": 1600,  # videos.insert
}


class QuotaExceededError(Exception):
    """クォータを使い切ったことを示す。処理の即時中断を要求する。"""


def is_quota_error(exception: BaseException) -> bool:
    """クォータ枯渇 (リセットまで回復しない) かどうかを判定する。

    YouTube は以下を1日の上限として返す:
      - HTTP 403 + 'quotaExceeded'
      - HTTP 429 + 'Video Uploads per day' (rateLimitExceeded)
      - HTTP 400 + 'uploadLimitExceeded'

    これらはリトライしても回復しないため、即座に中断すべき。
    一時的な 429 (単なるレート超過) はここでは False を返す。
    """
    if not isinstance(exception, HttpError):
        return False

    msg = str(exception)
    status = exception.resp.status

    if status == 403 and "quotaExceeded" in msg:
        return True
    if status == 429 and "Video Uploads per day" in msg:
        return True
    if status == 400 and "uploadLimitExceeded" in msg:
        return True
    return False


class QuotaLedger:
    """消費ユニットを積算する見積もり用の帳簿。

    実際の残量は API 側にしか無いため、これは 403 を受け取る前に
    自主的に止まるための安全弁である。実際の枯渇検知 (is_quota_error)
    と併用すること。
    """

    def __init__(self, budget: int) -> None:
        self._budget = max(0, budget)
        self._spent = 0

    @property
    def budget(self) -> int:
        return self._budget

    @property
    def spent(self) -> int:
        return self._spent

    @property
    def remaining(self) -> int:
        return max(0, self._budget - self._spent)

    def cost_of(self, op: str, count: int = 1) -> int:
        """操作 op を count 回行ったときの消費ユニットを返す。"""
        if op not in COSTS:
            raise ValueError(f"Unknown quota operation: {op}")
        return COSTS[op] * count

    def can_afford(self, op: str, count: int = 1) -> bool:
        """予算内に収まるかを判定する。"""
        return self._spent + self.cost_of(op, count) <= self._budget

    def charge(self, op: str, count: int = 1) -> None:
        """消費を計上する。予算を超える場合は計上せず例外を送出する。"""
        cost = self.cost_of(op, count)
        if self._spent + cost > self._budget:
            raise QuotaExceededError(
                f"予算超過: {self._spent:,} + {cost:,} > {self._budget:,} ユニット"
            )
        self._spent += cost
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/core/test_quota.py -v --no-cov`
Expected: PASS（20件）

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/core/quota.py tests/lib/core/test_quota.py
git commit -m "feat: quota 枯渇の判定と消費ユニット積算のモジュールを追加

QuotaExceededError / is_quota_error / QuotaLedger を新設。
403 quotaExceeded と一時的な 429 を区別し、リトライしても
回復しないケースだけを枯渇と判定する。"
```

---

## Task 2: uploader の quota 判定を一本化

**Files:**
- Modify: `src/lib/video/uploader.py:22-54`
- Test: `tests/lib/video/test_uploader.py`（既存テストが回帰検証を兼ねる）

**Interfaces:**
- Consumes: Task 1 の `is_quota_error(exception: BaseException) -> bool`
- Produces: `should_retry_exception(exception: BaseException) -> bool`（既存の挙動を維持）

既存テスト（`test_uploader.py:105-143`）は `should_retry_exception` のみを参照しており、
内部関数 `_is_daily_upload_quota_error` は直接参照していない。よって内部実装の差し替えは安全。

- [ ] **Step 1: 既存テストが通ることを先に確認（ベースライン）**

Run: `uv run pytest tests/lib/video/test_uploader.py -v --no-cov`
Expected: PASS（変更前の状態を記録しておく）

- [ ] **Step 2: `_is_daily_upload_quota_error` を削除し `is_quota_error` に差し替える**

`src/lib/video/uploader.py` の 22-39 行目（`_is_daily_upload_quota_error` の定義全体）を削除し、
import と `should_retry_exception` を次のように変更する:

```python
from ..core.config import config
from ..core.quota import is_quota_error

logger = logging.getLogger("youtube_up")


def should_retry_exception(exception: BaseException) -> bool:
    """Check if the exception is worth retrying."""
    if isinstance(exception, (socket.error, socket.timeout)):
        return True
    if isinstance(exception, HttpError):
        # クォータ枯渇はリトライしない (翌日まで回復しない)
        if is_quota_error(exception):
            return False
        # Retry 5xx server errors, 429 Too Many Requests, and 408 Request Timeout
        if exception.resp.status in [408, 429, 500, 502, 503, 504]:
            return True
        return False
    return False
```

import の並び順は ruff の "I" ルールに従う（`..core.config` の直後に `..core.quota`）。

- [ ] **Step 3: 既存テストが引き続き通ることを確認**

Run: `uv run pytest tests/lib/video/test_uploader.py -v --no-cov`
Expected: PASS — 特に `test_should_retry_exception` と `test_should_retry_transient_429` が
変更前と同じ結果になること（403 quotaExceeded は False、一時的な 429 は True）

- [ ] **Step 4: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 5: コミット**

```bash
git add src/lib/video/uploader.py
git commit -m "refactor: uploader の quota 判定を core/quota に一本化

_is_daily_upload_quota_error を削除し is_quota_error を利用する。
判定条件と挙動は変更していない。"
```

---

## Task 3: SnapshotCache

**Files:**
- Create: `src/lib/data/snapshot.py`
- Test: `tests/lib/data/test_snapshot.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `SnapshotCache(db_path: Optional[str] = None, ttl_hours: int = 24)`
  - `.is_fresh(kind: str) -> bool` — `kind` は `"playlists"` / `"playlist_items"` / `"videos"`
  - `.mark_complete(kind: str) -> None`
  - `.save_playlists(playlists: List[Dict[str, Any]]) -> None` — dict のキーは `id`, `title`, `item_count`, `privacy`, `published_at`
  - `.load_playlists() -> List[Dict[str, Any]]` — 同じキー形式で返す
  - `.save_playlist_items(playlist_id: str, video_ids: Set[str]) -> None`
  - `.load_playlist_map() -> Dict[str, Set[str]]`
  - `.save_videos(videos: List[Dict[str, Any]]) -> None` — dict のキーは `id`, `title`, `privacy`
  - `.load_videos() -> List[Dict[str, Any]]`
  - `.clear(kind: Optional[str] = None) -> None`
  - `.close() -> None`

dict のキー名は既存の `PlaylistManager.list_playlists()` / `VideoManager.get_all_uploaded_videos()`
の戻り値と一致させる（`id` であって `playlist_id` ではない）。DB 列名との変換は `SnapshotCache` 内で行う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/data/test_snapshot.py` を新規作成:

```python
import os
import tempfile
import time
from typing import Generator

import pytest

from src.lib.data.snapshot import SnapshotCache


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    for suffix in ["", "-wal", "-shm"]:
        path = db_path + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def cache(temp_db_path) -> Generator[SnapshotCache, None, None]:
    c = SnapshotCache(db_path=temp_db_path, ttl_hours=24)
    yield c
    c.close()


PLAYLISTS = [
    {"id": "PL1", "title": "運動会", "item_count": 3, "privacy": "private",
     "published_at": "2020-01-01T00:00:00Z"},
    {"id": "PL2", "title": "運動会", "item_count": 1, "privacy": "private",
     "published_at": "2021-06-01T00:00:00Z"},
    {"id": "PL3", "title": "発表会", "item_count": 2, "privacy": "public",
     "published_at": "2019-03-01T00:00:00Z"},
]

VIDEOS = [
    {"id": "v1", "title": "動画1", "privacy": "private"},
    {"id": "v2", "title": "動画2", "privacy": "unlisted"},
]


class TestPlaylists:
    def test_save_and_load_roundtrip(self, cache):
        cache.save_playlists(PLAYLISTS)
        loaded = cache.load_playlists()
        assert len(loaded) == 3
        by_id = {p["id"]: p for p in loaded}
        assert by_id["PL1"]["title"] == "運動会"
        assert by_id["PL1"]["item_count"] == 3
        assert by_id["PL1"]["privacy"] == "private"
        assert by_id["PL1"]["published_at"] == "2020-01-01T00:00:00Z"

    def test_load_empty_returns_empty_list(self, cache):
        assert cache.load_playlists() == []

    def test_save_replaces_previous_snapshot(self, cache):
        """再取得したら古いスナップショットは残らない (削除されたPLが残留しない)。"""
        cache.save_playlists(PLAYLISTS)
        cache.save_playlists([PLAYLISTS[0]])
        loaded = cache.load_playlists()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "PL1"


class TestPlaylistItems:
    def test_save_and_load_map(self, cache):
        cache.save_playlist_items("PL1", {"v1", "v2"})
        cache.save_playlist_items("PL2", {"v3"})
        assert cache.load_playlist_map() == {"PL1": {"v1", "v2"}, "PL2": {"v3"}}

    def test_save_replaces_items_of_that_playlist_only(self, cache):
        cache.save_playlist_items("PL1", {"v1", "v2"})
        cache.save_playlist_items("PL2", {"v3"})
        cache.save_playlist_items("PL1", {"v9"})
        assert cache.load_playlist_map() == {"PL1": {"v9"}, "PL2": {"v3"}}

    def test_empty_playlist_is_recorded_as_empty_set(self, cache):
        cache.save_playlist_items("PL1", set())
        assert cache.load_playlist_map() == {"PL1": set()}

    def test_load_empty_returns_empty_dict(self, cache):
        assert cache.load_playlist_map() == {}


class TestVideos:
    def test_save_and_load_roundtrip(self, cache):
        cache.save_videos(VIDEOS)
        loaded = cache.load_videos()
        assert len(loaded) == 2
        by_id = {v["id"]: v for v in loaded}
        assert by_id["v1"]["title"] == "動画1"
        assert by_id["v2"]["privacy"] == "unlisted"

    def test_save_replaces_previous_snapshot(self, cache):
        cache.save_videos(VIDEOS)
        cache.save_videos([VIDEOS[0]])
        assert len(cache.load_videos()) == 1


class TestFreshness:
    def test_not_fresh_before_mark_complete(self, cache):
        """保存しただけでは新鮮とみなさない (取得が中断した可能性があるため)。"""
        cache.save_playlists(PLAYLISTS)
        assert cache.is_fresh("playlists") is False

    def test_fresh_after_mark_complete(self, cache):
        cache.save_playlists(PLAYLISTS)
        cache.mark_complete("playlists")
        assert cache.is_fresh("playlists") is True

    def test_kinds_are_independent(self, cache):
        cache.mark_complete("playlists")
        assert cache.is_fresh("playlists") is True
        assert cache.is_fresh("videos") is False
        assert cache.is_fresh("playlist_items") is False

    def test_stale_after_ttl(self, temp_db_path):
        cache = SnapshotCache(db_path=temp_db_path, ttl_hours=24)
        cache.mark_complete("playlists")
        cache.close()

        # TTL を 0 にすると、直前に完了したものでも期限切れになる
        expired = SnapshotCache(db_path=temp_db_path, ttl_hours=0)
        time.sleep(0.01)
        assert expired.is_fresh("playlists") is False
        expired.close()

    def test_unknown_kind_raises(self, cache):
        with pytest.raises(ValueError, match="Unknown cache kind"):
            cache.is_fresh("bananas")
        with pytest.raises(ValueError, match="Unknown cache kind"):
            cache.mark_complete("bananas")

    def test_mark_complete_is_idempotent(self, cache):
        cache.mark_complete("playlists")
        cache.mark_complete("playlists")
        assert cache.is_fresh("playlists") is True


class TestClear:
    def test_clear_single_kind(self, cache):
        cache.save_playlists(PLAYLISTS)
        cache.mark_complete("playlists")
        cache.save_videos(VIDEOS)
        cache.mark_complete("videos")

        cache.clear("playlists")

        assert cache.load_playlists() == []
        assert cache.is_fresh("playlists") is False
        assert len(cache.load_videos()) == 2, "他の kind は残る"
        assert cache.is_fresh("videos") is True

    def test_clear_all(self, cache):
        cache.save_playlists(PLAYLISTS)
        cache.save_videos(VIDEOS)
        cache.save_playlist_items("PL1", {"v1"})
        cache.mark_complete("playlists")

        cache.clear()

        assert cache.load_playlists() == []
        assert cache.load_videos() == []
        assert cache.load_playlist_map() == {}
        assert cache.is_fresh("playlists") is False

    def test_clear_unknown_kind_raises(self, cache):
        with pytest.raises(ValueError, match="Unknown cache kind"):
            cache.clear("bananas")


class TestPersistence:
    def test_data_survives_reopen(self, temp_db_path):
        c1 = SnapshotCache(db_path=temp_db_path)
        c1.save_playlists(PLAYLISTS)
        c1.mark_complete("playlists")
        c1.close()

        c2 = SnapshotCache(db_path=temp_db_path)
        assert len(c2.load_playlists()) == 3
        assert c2.is_fresh("playlists") is True
        c2.close()
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/data/test_snapshot.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.lib.data.snapshot'`

- [ ] **Step 3: 実装を書く**

`src/lib/data/snapshot.py` を新規作成:

```python
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
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/data/test_snapshot.py -v --no-cov`
Expected: PASS（21件）

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/data/snapshot.py tests/lib/data/test_snapshot.py
git commit -m "feat: YouTube 側の状態をキャッシュする SnapshotCache を追加

playlists / playlist items / videos を専用 SQLite に保存する。
鮮度は cache_meta で管理し、全件取得を完走したときだけ
mark_complete を記録することで、中断した部分データを
新鮮と誤認しないようにした。"
```

---

## Task 4: history に playlist_synced を追加

**Files:**
- Modify: `src/lib/data/history.py:15-55`（スキーマとマイグレーション）、末尾（アクセサ追加）
- Test: `tests/lib/data/test_history_manager.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `HistoryManager.set_playlist_synced(video_id: str, synced: bool) -> None`
  - `HistoryManager.get_unsynced_records() -> List[Dict[str, Any]]` — `playlist_synced = 0` のレコード
  - `uploads` テーブルに `playlist_synced INTEGER DEFAULT NULL` 列（1=成功 / 0=失敗 / NULL=不明）

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/data/test_history_manager.py` の末尾に追記:

```python
class TestPlaylistSynced:
    def test_column_exists_after_init(self, history):
        cols = [r[1] for r in history.conn.execute("PRAGMA table_info(uploads)")]
        assert "playlist_synced" in cols

    def test_new_record_defaults_to_null(self, history):
        """既存の add_record 経路では未設定 (NULL = 不明) になる。"""
        history.add_record("/a.mp4", "h1", "vid1", {}, playlist_name="PL")
        rec = history.get_record_by_video_id("vid1")
        assert rec["playlist_synced"] is None

    def test_set_playlist_synced_true(self, history):
        history.add_record("/a.mp4", "h1", "vid1", {}, playlist_name="PL")
        history.set_playlist_synced("vid1", True)
        assert history.get_record_by_video_id("vid1")["playlist_synced"] == 1

    def test_set_playlist_synced_false(self, history):
        history.add_record("/a.mp4", "h1", "vid1", {}, playlist_name="PL")
        history.set_playlist_synced("vid1", False)
        assert history.get_record_by_video_id("vid1")["playlist_synced"] == 0

    def test_set_playlist_synced_is_overwritable(self, history):
        """後から --fix で復旧したら 0 -> 1 に更新できる。"""
        history.add_record("/a.mp4", "h1", "vid1", {}, playlist_name="PL")
        history.set_playlist_synced("vid1", False)
        history.set_playlist_synced("vid1", True)
        assert history.get_record_by_video_id("vid1")["playlist_synced"] == 1

    def test_set_playlist_synced_unknown_video_is_noop(self, history):
        """存在しない video_id でも例外を投げない。"""
        history.set_playlist_synced("nope", True)
        assert history.get_record_by_video_id("nope") is None

    def test_get_unsynced_records_returns_only_zero(self, history):
        history.add_record("/a.mp4", "h1", "vid1", {}, playlist_name="PL")
        history.add_record("/b.mp4", "h2", "vid2", {}, playlist_name="PL")
        history.add_record("/c.mp4", "h3", "vid3", {}, playlist_name="PL")
        history.set_playlist_synced("vid1", False)
        history.set_playlist_synced("vid2", True)
        # vid3 は NULL のまま

        unsynced = history.get_unsynced_records()
        assert [r["video_id"] for r in unsynced] == ["vid1"]

    def test_get_unsynced_records_empty(self, history):
        assert history.get_unsynced_records() == []

    def test_migration_is_idempotent_on_existing_db(self, temp_db_path):
        """既存DB (playlist_synced 列なし) を開いても壊れず、既存行は NULL になる。"""
        import sqlite3

        conn = sqlite3.connect(temp_db_path)
        conn.execute(
            """CREATE TABLE uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL, file_hash TEXT NOT NULL, video_id TEXT,
                metadata TEXT DEFAULT '{}', timestamp REAL DEFAULT 0,
                status TEXT DEFAULT 'success', error TEXT,
                playlist_name TEXT, file_size INTEGER DEFAULT 0
            );"""
        )
        conn.execute(
            "INSERT INTO uploads (file_path, file_hash, video_id, status) "
            "VALUES ('/old.mp4', 'oldhash', 'oldvid', 'success')"
        )
        conn.commit()
        conn.close()

        h1 = HistoryManager(db_path=temp_db_path)
        assert h1.get_record_by_video_id("oldvid")["playlist_synced"] is None
        h1.close()

        # 2回目の初期化でも ALTER TABLE が重複実行されない
        h2 = HistoryManager(db_path=temp_db_path)
        assert h2.get_record_by_video_id("oldvid")["playlist_synced"] is None
        h2.close()
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/data/test_history_manager.py::TestPlaylistSynced -v --no-cov`
Expected: FAIL — `assert 'playlist_synced' in cols` が失敗、および
`AttributeError: 'HistoryManager' object has no attribute 'set_playlist_synced'`

- [ ] **Step 3: 実装を書く**

`src/lib/data/history.py` の `_CREATE_TABLE_SQL`（15-28行目）に列を追加:

```python
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
    file_size INTEGER DEFAULT 0,
    playlist_synced INTEGER DEFAULT NULL
);
"""
```

`_CREATE_INDEX_SQL`（31-37行目）にインデックスを追加:

```python
    "CREATE INDEX IF NOT EXISTS idx_playlist_synced ON uploads (playlist_synced);",
```

`_init_schema()`（50-55行目）を、既存DBへのマイグレーションを行うよう変更:

```python
    def _init_schema(self):
        """テーブルとインデックスを作成し、既存DBに不足列があれば追加する。"""
        self.conn.execute(_CREATE_TABLE_SQL)
        self._migrate_add_playlist_synced()
        for idx_sql in _CREATE_INDEX_SQL:
            self.conn.execute(idx_sql)
        self.conn.commit()

    def _migrate_add_playlist_synced(self):
        """playlist_synced 列を後付けする (冪等)。

        値の意味: 1=プレイリスト追加成功 / 0=失敗 / NULL=不明。
        既存レコードを 0 にすると全件がオーファン候補になってしまうため、
        NULL (不明) のままにして 0 と区別する。
        """
        columns = [row[1] for row in self.conn.execute("PRAGMA table_info(uploads)")]
        if "playlist_synced" not in columns:
            self.conn.execute(
                "ALTER TABLE uploads ADD COLUMN playlist_synced INTEGER DEFAULT NULL"
            )
            logger.info("uploads テーブルに playlist_synced 列を追加しました。")
```

`close()` の直前にアクセサを追加:

```python
    def set_playlist_synced(self, video_id: str, synced: bool) -> None:
        """プレイリストへの追加の成否を記録する。

        1=成功 / 0=失敗。該当レコードが無い場合は何もしない。
        """
        self.conn.execute(
            "UPDATE uploads SET playlist_synced = ? WHERE video_id = ?",
            (1 if synced else 0, video_id),
        )
        self.conn.commit()

    def get_unsynced_records(self) -> list:
        """プレイリストへの追加に失敗した (playlist_synced = 0) レコードを返す。

        NULL (不明) は含めない。不明なものは API で実態を確認する必要がある。
        """
        cursor = self.conn.execute(
            "SELECT * FROM uploads WHERE playlist_synced = 0 ORDER BY timestamp DESC"
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/data/test_history_manager.py -v --no-cov`
Expected: PASS（新規9件を含む既存テスト全件）

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/data/history.py tests/lib/data/test_history_manager.py
git commit -m "feat: 履歴に playlist_synced 列を追加しプレイリスト同期状態を記録

1=成功 / 0=失敗 / NULL=不明 の三値とする。
既存レコードを一律 0 にすると全件がオーファン候補になるため
NULL のままとし、0 と明確に区別する。
既存DBへの ALTER TABLE は冪等に実行する。"
```

---

## Task 5: 設定に quota / cache セクションを追加

**Files:**
- Modify: `src/lib/core/config.py:20-53`
- Modify: `settings.yaml`
- Modify: `.gitignore`
- Test: `tests/lib/core/test_config.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `config.quota.daily_limit: int`（既定 10000）、`config.quota.reserve: int`（既定 1000）
  - `config.cache.enabled: bool`（既定 True）、`config.cache.ttl_hours: int`（既定 24）、`config.cache.path: str`（既定 `"youtube_cache.db"`）
  - `config.effective_daily_quota() -> int` — `quota.daily_limit` を返す。ただし `settings.yaml` に
    `quota` セクションが無く `upload.daily_quota_limit` が既定値 10000 から変更されている場合は後者を返す（後方互換）

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/core/test_config.py` の末尾に追記:

```python
class TestQuotaAndCacheConfig:
    def test_defaults(self):
        from src.lib.core.config import AppConfig

        cfg = AppConfig()
        assert cfg.quota.daily_limit == 10000
        assert cfg.quota.reserve == 1000
        assert cfg.cache.enabled is True
        assert cfg.cache.ttl_hours == 24
        assert cfg.cache.path == "youtube_cache.db"

    def test_load_from_yaml(self, tmp_path):
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text(
            "quota:\n"
            "  daily_limit: 500000\n"
            "  reserve: 20000\n"
            "cache:\n"
            "  enabled: false\n"
            "  ttl_hours: 6\n"
            "  path: 'custom_cache.db'\n",
            encoding="utf-8",
        )
        cfg = AppConfig.load(str(path))
        assert cfg.quota.daily_limit == 500000
        assert cfg.quota.reserve == 20000
        assert cfg.cache.enabled is False
        assert cfg.cache.ttl_hours == 6
        assert cfg.cache.path == "custom_cache.db"

    def test_effective_daily_quota_prefers_quota_section(self, tmp_path):
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text(
            "quota:\n  daily_limit: 500000\nupload:\n  daily_quota_limit: 30000\n",
            encoding="utf-8",
        )
        cfg = AppConfig.load(str(path))
        assert cfg.effective_daily_quota() == 500000

    def test_effective_daily_quota_falls_back_to_upload_section(self, tmp_path):
        """quota セクションが無く upload.daily_quota_limit だけ変更されている
        既存の設定ファイルとの後方互換。"""
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text("upload:\n  daily_quota_limit: 30000\n", encoding="utf-8")
        cfg = AppConfig.load(str(path))
        assert cfg.effective_daily_quota() == 30000

    def test_effective_daily_quota_default(self):
        from src.lib.core.config import AppConfig

        cfg = AppConfig()
        assert cfg.effective_daily_quota() == 10000
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/core/test_config.py::TestQuotaAndCacheConfig -v --no-cov`
Expected: FAIL — `AttributeError: 'AppConfig' object has no attribute 'quota'`

- [ ] **Step 3: 実装を書く**

`src/lib/core/config.py` の `MetadataConfig` の後に追加:

```python
class QuotaConfig(BaseModel):
    daily_limit: int = 10000  # 実際の GCP 上限に合わせて調整する
    reserve: int = 1000       # 予備として残すユニット


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_hours: int = 24
    path: str = "youtube_cache.db"
```

`AppConfig` を次のように変更:

```python
class AppConfig(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    history_db: str = "upload_history.db"

    # quota セクションが設定ファイルに明示されていたかを保持する (後方互換の判定用)
    _has_explicit_quota: bool = False

    @classmethod
    def load(cls, path: str = "settings.yaml") -> "AppConfig":
        """Load configuration from a YAML file, with env var overrides."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # Allow individual sections to be partial
            instance = cls(**data)
            instance._has_explicit_quota = "quota" in data
            return instance
        return cls()

    def effective_daily_quota(self) -> int:
        """実効的な日次クォータ上限を返す。

        quota.daily_limit を正とするが、quota セクションが無く
        upload.daily_quota_limit だけが既定値から変更されている
        既存の設定ファイルとの互換性のため、その場合は後者を使う。
        """
        if not self._has_explicit_quota and self.upload.daily_quota_limit != 10000:
            return self.upload.daily_quota_limit
        return self.quota.daily_limit
```

pydantic v2 では `_` 始まりの属性はプライベート属性として扱われるため、
`BaseModel` に直接宣言する場合は `PrivateAttr` を使う。import と宣言を次のようにする:

```python
from pydantic import BaseModel, Field, PrivateAttr  # noqa: E402
```

```python
    _has_explicit_quota: bool = PrivateAttr(default=False)
```

`settings.yaml` に追記（`# Database path` の直前）:

```yaml
# Quota settings
quota:
  daily_limit: 10000   # YouTube Data API 日次クォータ上限 (実際の GCP 上限に合わせる)
  reserve: 1000        # 予備として残すユニット

# Cache settings (YouTube 側の状態のローカルキャッシュ)
cache:
  enabled: true
  ttl_hours: 24
  path: "youtube_cache.db"
```

`.gitignore` の `upload_history.db-shm` の次の行に追記:

```
youtube_cache.db
youtube_cache.db-wal
youtube_cache.db-shm
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/core/test_config.py -v --no-cov`
Expected: PASS（新規5件を含む既存テスト全件）

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/core/config.py settings.yaml .gitignore tests/lib/core/test_config.py
git commit -m "feat: quota / cache の設定セクションを追加

quota.daily_limit と quota.reserve、cache の有効/TTL/保存先を設定可能にした。
既存の upload.daily_quota_limit のみを設定しているファイルとの
後方互換のため effective_daily_quota() を用意した。"
```

---

## Task 6: PlaylistManager のページネーション対応と重複検出

**Files:**
- Modify: `src/lib/video/playlist.py:1-49`（import、`PlaylistInfo`、`_ensure_cache`）、`363-396`（`get_all_playlists_map`）
- Test: `tests/lib/video/test_playlist.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `PlaylistInfo` — `@dataclass(frozen=True)` で `id: str`, `title: str`, `item_count: int`, `privacy: str`, `published_at: str`
  - `PlaylistManager._playlists: List[PlaylistInfo]` — 全件（重複含む）
  - `PlaylistManager._playlist_cache: Dict[str, str]` — title → **正の**ID（既存の実属性のまま）
  - `PlaylistManager._all_playlist_ids() -> List[str]`
  - `PlaylistManager.get_duplicate_playlists() -> Dict[str, List[PlaylistInfo]]`

**これが最優先の修正。** これ単独で誤判定と重複プレイリスト生成が止まる。

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/video/test_playlist.py` の末尾に追記:

```python
class TestPlaylistPagination(unittest.TestCase):
    def setUp(self):
        self.mock_creds = MagicMock()
        self.manager = PlaylistManager(self.mock_creds)

    @staticmethod
    def _page(items, next_token=None):
        page = {"items": items}
        if next_token:
            page["nextPageToken"] = next_token
        return page

    @staticmethod
    def _item(pid, title, published="2020-01-01T00:00:00Z", count=0):
        return {
            "id": pid,
            "snippet": {"title": title, "publishedAt": published},
            "contentDetails": {"itemCount": count},
            "status": {"privacyStatus": "private"},
        }

    @patch("src.lib.video.playlist.build")
    def test_ensure_cache_follows_pagination(self, mock_build):
        """50件を超えるプレイリストを全件取得する (544個ある環境の回帰テスト)。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        page1 = self._page([self._item(f"PL{i}", f"T{i}") for i in range(50)], "TOKEN")
        page2 = self._page([self._item(f"PL{i}", f"T{i}") for i in range(50, 60)])
        mock_service.playlists().list.return_value.execute.side_effect = [page1, page2]

        self.manager._ensure_cache()

        self.assertEqual(len(self.manager._playlists), 60)
        self.assertEqual(len(self.manager._playlist_cache), 60)
        self.assertIn("T59", self.manager._playlist_cache)

    @patch("src.lib.video.playlist.build")
    def test_pagination_passes_page_token(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        page1 = self._page([self._item("PL1", "T1")], "TOKEN")
        page2 = self._page([self._item("PL2", "T2")])
        mock_service.playlists().list.return_value.execute.side_effect = [page1, page2]

        self.manager._ensure_cache()

        calls = mock_service.playlists().list.call_args_list
        tokens = [c.kwargs.get("pageToken") for c in calls if "pageToken" in c.kwargs]
        self.assertIn("TOKEN", tokens)

    @patch("src.lib.video.playlist.build")
    def test_duplicate_titles_resolve_to_oldest(self, mock_build):
        """同名が複数あるとき、最も古いものを「正」とする。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.side_effect = [
            self._page([
                self._item("PL_NEW", "運動会", "2024-05-01T00:00:00Z"),
                self._item("PL_OLD", "運動会", "2020-01-01T00:00:00Z"),
                self._item("PL_MID", "運動会", "2022-01-01T00:00:00Z"),
            ])
        ]

        self.manager._ensure_cache()

        self.assertEqual(self.manager._playlist_cache["運動会"], "PL_OLD")
        self.assertEqual(len(self.manager._playlists), 3)

    @patch("src.lib.video.playlist.build")
    def test_get_duplicate_playlists(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.side_effect = [
            self._page([
                self._item("PL_NEW", "運動会", "2024-05-01T00:00:00Z"),
                self._item("PL_OLD", "運動会", "2020-01-01T00:00:00Z"),
                self._item("PL_SOLO", "発表会", "2021-01-01T00:00:00Z"),
            ])
        ]

        dups = self.manager.get_duplicate_playlists()

        self.assertEqual(list(dups.keys()), ["運動会"])
        self.assertEqual([p.id for p in dups["運動会"]], ["PL_OLD", "PL_NEW"])
        self.assertNotIn("発表会", dups)

    @patch("src.lib.video.playlist.build")
    def test_get_duplicate_playlists_none(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.side_effect = [
            self._page([self._item("PL1", "A"), self._item("PL2", "B")])
        ]
        self.assertEqual(self.manager.get_duplicate_playlists(), {})

    @patch("src.lib.video.playlist.build")
    def test_all_playlist_ids_includes_duplicates(self, mock_build):
        """重複プレイリストの中身も走査対象に含める。
        漏らすと重複側にだけ入っている動画がオーファン誤判定される。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.side_effect = [
            self._page([
                self._item("PL_OLD", "運動会", "2020-01-01T00:00:00Z"),
                self._item("PL_NEW", "運動会", "2024-05-01T00:00:00Z"),
            ])
        ]

        self.manager._ensure_cache()

        self.assertEqual(sorted(self.manager._all_playlist_ids()), ["PL_NEW", "PL_OLD"])

    def test_all_playlist_ids_falls_back_to_cache(self):
        """_playlists が空のとき (テストが _playlist_cache に直接代入した場合) は
        _playlist_cache の値を使う。"""
        self.manager._playlist_cache = {"A": "PL1", "B": "PL2"}
        self.manager._initialized = True
        self.assertEqual(sorted(self.manager._all_playlist_ids()), ["PL1", "PL2"])

    @patch("src.lib.video.playlist.build")
    def test_get_all_playlists_map_covers_all_playlists(self, mock_build):
        """544個の環境で50個しか走査していなかった問題の回帰テスト。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        pl_items = [self._item(f"PL{i}", f"T{i}") for i in range(50)]
        pl_items2 = [self._item(f"PL{i}", f"T{i}") for i in range(50, 60)]
        mock_service.playlists().list.return_value.execute.side_effect = [
            self._page(pl_items, "TOKEN"),
            self._page(pl_items2),
        ]
        mock_service.playlistItems().list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}]
        }
        mock_service.playlistItems().list_next.return_value = None

        result = self.manager.get_all_playlists_map()

        self.assertEqual(len(result), 60)
        self.assertIn("PL59", result)
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/video/test_playlist.py::TestPlaylistPagination -v --no-cov`
Expected: FAIL — `AttributeError: 'PlaylistManager' object has no attribute '_playlists'`
および `test_ensure_cache_follows_pagination` が `len == 50`（ページネーション未対応）で失敗

- [ ] **Step 3: 実装を書く**

`src/lib/video/playlist.py` の import と冒頭を変更:

```python
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_up")


@dataclass(frozen=True)
class PlaylistInfo:
    """1つのプレイリストのメタ情報。"""

    id: str
    title: str
    item_count: int
    privacy: str
    published_at: str


class PlaylistManager:
    """
    Manages YouTube Playlist interactions.
    """

    def __init__(self, credentials):
        self.credentials = credentials
        # タイトル -> 「正の」プレイリストID。同名が複数ある場合は最古のものを指す。
        self._playlist_cache: Dict[str, str] = {}
        # 全プレイリスト (同名の重複も含む)
        self._playlists: List[PlaylistInfo] = []
        self._initialized = False
```

`_ensure_cache()`（19-49行目）を全面的に書き換える:

```python
    def _ensure_cache(self):
        """
        Populates the cache with existing playlists from the channel.
        This is done lazily to avoid startup latency if not needed.

        全ページを取得する。ページネーションを怠ると既存プレイリストを
        見落として同名のものを重複作成してしまう。
        """
        if self._initialized:
            return

        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )

            playlists: List[PlaylistInfo] = []
            next_page_token = None

            while True:
                response = service.playlists().list(
                    part="snippet,contentDetails,status",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page_token,
                ).execute()

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    playlists.append(
                        PlaylistInfo(
                            id=item["id"],
                            title=snippet.get("title", ""),
                            item_count=item.get("contentDetails", {}).get("itemCount", 0),
                            privacy=item.get("status", {}).get("privacyStatus", "private"),
                            published_at=snippet.get("publishedAt", ""),
                        )
                    )

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

            self._playlists = playlists
            self._playlist_cache = self._build_title_index(playlists)
            self._initialized = True
            logger.debug(
                f"Initialized playlist cache with {len(playlists)} playlists "
                f"({len(self._playlist_cache)} unique titles)."
            )

        except HttpError as e:
            logger.error(f"Failed to list playlists: {e}")
            # 初期化済みにしない (次回リトライできるようにする)

    @staticmethod
    def _build_title_index(playlists: List[PlaylistInfo]) -> Dict[str, str]:
        """タイトル -> 正のプレイリストID の索引を作る。

        同名が複数ある場合は published_at が最も古いものを「正」とする。
        後から誤って作成された重複ではなく、本来のプレイリストを選ぶため。
        """
        index: Dict[str, PlaylistInfo] = {}
        for pl in playlists:
            current = index.get(pl.title)
            if current is None or pl.published_at < current.published_at:
                index[pl.title] = pl
        return {title: pl.id for title, pl in index.items()}

    def _all_playlist_ids(self) -> List[str]:
        """走査対象の全プレイリストID。重複プレイリストも含む。

        _playlists が空のとき (テストが _playlist_cache に直接代入した場合など) は
        _playlist_cache の値にフォールバックする。
        """
        if self._playlists:
            return [p.id for p in self._playlists]
        return list(self._playlist_cache.values())

    def get_duplicate_playlists(self) -> Dict[str, List[PlaylistInfo]]:
        """同名プレイリストが2つ以上あるものを {title: [PlaylistInfo, ...]} で返す。

        各リストは published_at 昇順 (先頭が「正」)。
        """
        self._ensure_cache()

        grouped: Dict[str, List[PlaylistInfo]] = {}
        for pl in self._playlists:
            grouped.setdefault(pl.title, []).append(pl)

        return {
            title: sorted(items, key=lambda p: p.published_at)
            for title, items in grouped.items()
            if len(items) > 1
        }
```

`get_all_playlists_map()`（363-396行目）の走査対象を差し替える:

```python
    def get_all_playlists_map(self) -> Dict[str, set]:
        """
        Returns a map where key is Playlist ID and value is a Set of Video IDs in that playlist.

        重複プレイリストの中身も含める。漏らすと重複側にだけ入っている動画が
        オーファンと誤判定される。
        """
        self._ensure_cache()
        playlist_map = {}

        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )

            for playlist_id in self._all_playlist_ids():
                video_ids = set()

                request = service.playlistItems().list(
                    part="contentDetails",
                    playlistId=playlist_id,
                    maxResults=50
                )

                while request:
                    response = request.execute()
                    for item in response.get("items", []):
                        video_ids.add(item["contentDetails"]["videoId"])

                    request = service.playlistItems().list_next(request, response)

                playlist_map[playlist_id] = video_ids

            return playlist_map

        except HttpError as e:
            logger.error(f"Failed to build playlist map: {e}")
            return {}
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/video/test_playlist.py -v --no-cov`
Expected: PASS — 新規9件に加え、**既存テスト25件がすべて通ること**。
特に `test_get_or_create_existing`, `test_find_playlist_id`, `test_get_all_playlists_map`,
`test_ensure_cache_http_error` が壊れていないことを確認する。

既存の `test_get_or_create_existing` は `{"id": "PL123", "snippet": {"title": "..."}}` の
形のモックを使っており `contentDetails` / `status` / `publishedAt` を持たないが、
実装側で `.get()` によるフォールバックを入れているため通る。

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/video/playlist.py tests/lib/video/test_playlist.py
git commit -m "fix: プレイリスト一覧のページネーション未対応を修正

_ensure_cache が maxResults=50 の1ページしか取得しておらず、
プレイリストが544個ある環境では494個を見落としていた。
その結果 get_or_create_playlist が既存と同名のプレイリストを
重複作成し、get_all_playlists_map がオーファンを大量に誤判定していた。

全ページを取得するようにし、同名が複数ある場合は最古のものを
正として扱う。重複プレイリストの中身も走査対象に含める。"
```

---

## Task 7: PlaylistManager の quota 例外化とキャッシュ統合

**Files:**
- Modify: `src/lib/video/playlist.py`（`__init__`、`_ensure_cache`、`get_or_create_playlist`、`add_video_to_playlist`、`remove_video_from_playlist`、`get_all_playlists_map`）
- Test: `tests/lib/video/test_playlist.py`

**Interfaces:**
- Consumes: Task 1 の `QuotaExceededError`, `is_quota_error`。Task 3 の `SnapshotCache`
- Produces:
  - `PlaylistManager(credentials, cache: Optional[SnapshotCache] = None)`
  - 書き込み系メソッドは quota エラー時に `QuotaExceededError` を送出する（それ以外の `HttpError` は従来どおり `False` / `None`）
  - `get_all_playlists_map(refresh: bool = False, offline: bool = False) -> Dict[str, set]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/lib/video/test_playlist.py` の末尾に追記:

```python
class TestPlaylistQuotaHandling(unittest.TestCase):
    def setUp(self):
        self.mock_creds = MagicMock()
        self.manager = PlaylistManager(self.mock_creds)
        self.manager._playlist_cache = {"Existing": "PL1"}
        self.manager._initialized = True

    @staticmethod
    def _quota_error():
        import httplib2
        from googleapiclient.errors import HttpError

        resp = httplib2.Response({"status": 403})
        resp.status = 403
        return HttpError(resp, b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}')

    @staticmethod
    def _other_error():
        import httplib2
        from googleapiclient.errors import HttpError

        resp = httplib2.Response({"status": 404})
        resp.status = 404
        return HttpError(resp, b"Not Found")

    @patch("src.lib.video.playlist.build")
    def test_add_video_raises_on_quota_error(self, mock_build):
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlistItems().insert.return_value.execute.side_effect = (
            self._quota_error()
        )

        with self.assertRaises(QuotaExceededError):
            self.manager.add_video_to_playlist("PL1", "v1")

    @patch("src.lib.video.playlist.build")
    def test_add_video_returns_false_on_other_error(self, mock_build):
        """quota 以外のエラーは従来どおり False を返す (1件の失敗として扱う)。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlistItems().insert.return_value.execute.side_effect = (
            self._other_error()
        )

        self.assertFalse(self.manager.add_video_to_playlist("PL1", "v1"))

    @patch("src.lib.video.playlist.build")
    def test_get_or_create_raises_on_quota_error(self, mock_build):
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().insert.return_value.execute.side_effect = (
            self._quota_error()
        )

        with self.assertRaises(QuotaExceededError):
            self.manager.get_or_create_playlist("Brand New")

    @patch("src.lib.video.playlist.build")
    def test_get_or_create_returns_none_on_other_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().insert.return_value.execute.side_effect = (
            self._other_error()
        )

        self.assertIsNone(self.manager.get_or_create_playlist("Brand New"))

    @patch("src.lib.video.playlist.build")
    def test_remove_video_raises_on_quota_error(self, mock_build):
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlistItems().list.return_value.execute.return_value = {
            "items": [{"id": "ITEM1"}]
        }
        mock_service.playlistItems().delete.return_value.execute.side_effect = (
            self._quota_error()
        )

        with self.assertRaises(QuotaExceededError):
            self.manager.remove_video_from_playlist("PL1", "v1")

    @patch("src.lib.video.playlist.build")
    def test_ensure_cache_raises_on_quota_error(self, mock_build):
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        manager = PlaylistManager(self.mock_creds)
        mock_service.playlists().list.return_value.execute.side_effect = (
            self._quota_error()
        )

        with self.assertRaises(QuotaExceededError):
            manager._ensure_cache()


class TestPlaylistCacheIntegration(unittest.TestCase):
    def setUp(self):
        import tempfile

        from src.lib.data.snapshot import SnapshotCache

        self.mock_creds = MagicMock()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.cache = SnapshotCache(db_path=self.tmp.name, ttl_hours=24)

    def tearDown(self):
        import os

        self.cache.close()
        for suffix in ["", "-wal", "-shm"]:
            path = self.tmp.name + suffix
            if os.path.exists(path):
                os.remove(path)

    @staticmethod
    def _pl_item(pid, title):
        return {
            "id": pid,
            "snippet": {"title": title, "publishedAt": "2020-01-01T00:00:00Z"},
            "contentDetails": {"itemCount": 1},
            "status": {"privacyStatus": "private"},
        }

    @patch("src.lib.video.playlist.build")
    def test_map_is_saved_to_cache(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.return_value = {
            "items": [self._pl_item("PL1", "A")]
        }
        mock_service.playlistItems().list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}]
        }
        mock_service.playlistItems().list_next.return_value = None

        manager = PlaylistManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_playlists_map()

        self.assertEqual(result, {"PL1": {"v1"}})
        self.assertEqual(self.cache.load_playlist_map(), {"PL1": {"v1"}})
        self.assertTrue(self.cache.is_fresh("playlist_items"))

    @patch("src.lib.video.playlist.build")
    def test_second_call_uses_cache_without_api(self, mock_build):
        self.cache.save_playlist_items("PLX", {"vA", "vB"})
        self.cache.mark_complete("playlist_items")

        manager = PlaylistManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_playlists_map()

        self.assertEqual(result, {"PLX": {"vA", "vB"}})
        mock_build.assert_not_called()

    @patch("src.lib.video.playlist.build")
    def test_refresh_bypasses_cache(self, mock_build):
        self.cache.save_playlist_items("PLX", {"vA"})
        self.cache.mark_complete("playlist_items")

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.return_value = {
            "items": [self._pl_item("PL1", "A")]
        }
        mock_service.playlistItems().list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}]
        }
        mock_service.playlistItems().list_next.return_value = None

        manager = PlaylistManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_playlists_map(refresh=True)

        self.assertEqual(result, {"PL1": {"v1"}})

    @patch("src.lib.video.playlist.build")
    def test_offline_uses_stale_cache_without_api(self, mock_build):
        """TTL 切れでも offline ならキャッシュを使う (quota 枯渇中の調査用)。"""
        self.cache.save_playlist_items("PLX", {"vA"})
        self.cache.mark_complete("playlist_items")
        self.cache.ttl_seconds = 0

        manager = PlaylistManager(self.mock_creds, cache=self.cache)
        result = manager.get_all_playlists_map(offline=True)

        self.assertEqual(result, {"PLX": {"vA"}})
        mock_build.assert_not_called()

    @patch("src.lib.video.playlist.build")
    def test_offline_without_cache_raises(self, mock_build):
        manager = PlaylistManager(self.mock_creds, cache=self.cache)
        with self.assertRaises(RuntimeError):
            manager.get_all_playlists_map(offline=True)
        mock_build.assert_not_called()

    @patch("src.lib.video.playlist.build")
    def test_no_cache_still_works(self, mock_build):
        """cache=None でも従来どおり動作する (後方互換)。"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().list.return_value.execute.return_value = {
            "items": [self._pl_item("PL1", "A")]
        }
        mock_service.playlistItems().list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}]
        }
        mock_service.playlistItems().list_next.return_value = None

        manager = PlaylistManager(self.mock_creds)
        self.assertEqual(manager.get_all_playlists_map(), {"PL1": {"v1"}})
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/lib/video/test_playlist.py::TestPlaylistQuotaHandling tests/lib/video/test_playlist.py::TestPlaylistCacheIntegration -v --no-cov`
Expected: FAIL — `QuotaExceededError` が送出されない（`False` / `None` が返る）、
および `TypeError: __init__() got an unexpected keyword argument 'cache'`

- [ ] **Step 3: 実装を書く**

`src/lib/video/playlist.py` の import に追加:

```python
from ..core.quota import QuotaExceededError, is_quota_error
from ..data.snapshot import SnapshotCache
```

`__init__` を変更:

```python
    def __init__(self, credentials, cache: Optional[SnapshotCache] = None):
        self.credentials = credentials
        # タイトル -> 「正の」プレイリストID。同名が複数ある場合は最古のものを指す。
        self._playlist_cache: Dict[str, str] = {}
        # 全プレイリスト (同名の重複も含む)
        self._playlists: List[PlaylistInfo] = []
        self._initialized = False
        self._cache = cache
```

各メソッドの `except HttpError as e:` ブロックの**先頭**に quota 判定を追加する。
対象は `_ensure_cache`, `get_or_create_playlist`, `add_video_to_playlist`,
`remove_video_from_playlist`, `get_all_playlists_map` の5箇所。パターンは共通:

```python
        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded: {e}")
                raise QuotaExceededError(str(e)) from e
            # 以降は従来どおりのエラー処理
            ...
```

`add_video_to_playlist` は `videoAlreadyInPlaylist` の判定より**前**に quota 判定を置く:

```python
        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while adding {video_id}: {e}")
                raise QuotaExceededError(str(e)) from e

            if "videoAlreadyInPlaylist" in str(e):
                logger.info(f"Video {video_id} already in playlist {playlist_id}")
                return True

            logger.error(f"Failed to add video {video_id} to playlist {playlist_id}: {e}")
            return False
```

`get_all_playlists_map` にキャッシュ制御を組み込む:

```python
    def get_all_playlists_map(
        self, refresh: bool = False, offline: bool = False
    ) -> Dict[str, set]:
        """
        Returns a map where key is Playlist ID and value is a Set of Video IDs in that playlist.

        重複プレイリストの中身も含める。漏らすと重複側にだけ入っている動画が
        オーファンと誤判定される。

        refresh=True: キャッシュを無視して API から取り直す
        offline=True: API を一切叩かず、期限切れでもキャッシュを使う
                      (キャッシュが空なら RuntimeError)
        """
        if offline:
            if self._cache is None:
                raise RuntimeError(
                    "offline モードにはキャッシュが必要です。"
                    "settings.yaml で cache.enabled を有効にしてください。"
                )
            cached = self._cache.load_playlist_map()
            if not cached:
                raise RuntimeError(
                    "キャッシュが空のため offline モードで実行できません。"
                    "クォータに余裕があるときに --refresh 付きで実行してください。"
                )
            return cached

        if self._cache is not None and not refresh and self._cache.is_fresh("playlist_items"):
            cached = self._cache.load_playlist_map()
            if cached:
                logger.info(f"Loaded {len(cached)} playlists from cache.")
                return cached

        self._ensure_cache()
        playlist_map = {}

        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )

            for playlist_id in self._all_playlist_ids():
                video_ids = set()

                request = service.playlistItems().list(
                    part="contentDetails",
                    playlistId=playlist_id,
                    maxResults=50
                )

                while request:
                    response = request.execute()
                    for item in response.get("items", []):
                        video_ids.add(item["contentDetails"]["videoId"])

                    request = service.playlistItems().list_next(request, response)

                playlist_map[playlist_id] = video_ids
                if self._cache is not None:
                    self._cache.save_playlist_items(playlist_id, video_ids)

            if self._cache is not None:
                # 全件を走査し終えたときだけ「完了」を記録する
                self._cache.mark_complete("playlist_items")

            return playlist_map

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while building playlist map: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to build playlist map: {e}")
            return {}
```

`_ensure_cache` でも取得したプレイリスト一覧をキャッシュに保存する。
`self._initialized = True` の直前に追加:

```python
            if self._cache is not None:
                self._cache.save_playlists([
                    {
                        "id": p.id,
                        "title": p.title,
                        "item_count": p.item_count,
                        "privacy": p.privacy,
                        "published_at": p.published_at,
                    }
                    for p in playlists
                ])
                self._cache.mark_complete("playlists")
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/lib/video/test_playlist.py -v --no-cov`
Expected: PASS — 新規12件に加え既存全件。
既存の `test_ensure_cache_http_error`（quota 以外の 500 エラーを想定）と
`test_add_video_to_playlist_http_error` が壊れていないことを確認する。
これらのテストが quota 以外のエラーを使っていることを確認し、
もし 403 quotaExceeded を使っていた場合は該当テストを
「quota 以外のエラー」に修正する（この変更は仕様変更に伴う正当な修正）。

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/lib/video/playlist.py tests/lib/video/test_playlist.py
git commit -m "feat: PlaylistManager に quota 例外化とスナップショットキャッシュを統合

quota 枯渇時は False/None ではなく QuotaExceededError を送出し、
呼び出し側が「1件の失敗」と「全体の中断が必要な状況」を
区別できるようにした。

get_all_playlists_map に refresh / offline を追加し、
クォータ枯渇中でもキャッシュから調査できるようにした。"
```

---

## Task 8: orphans コマンドの改修

**Files:**
- Modify: `src/commands/playlist.py:146-244`
- Modify: `src/lib/video/manager.py:149-215`（`get_all_uploaded_videos` にキャッシュ対応を追加）
- Test: `tests/commands/test_playlist_command.py`

**Interfaces:**
- Consumes: Task 1 の `QuotaExceededError` / `QuotaLedger`、Task 3 の `SnapshotCache`、
  Task 4 の `set_playlist_synced`、Task 5 の `config.quota` / `config.cache`、
  Task 6-7 の `PlaylistManager(credentials, cache=...)` / `get_all_playlists_map(refresh, offline)`
- Produces:
  - `VideoManager(credentials, cache: Optional[SnapshotCache] = None)`
  - `VideoManager.get_all_uploaded_videos(refresh: bool = False, offline: bool = False) -> List[Dict[str, str]]`
  - CLI: `yt-up playlist orphans [--fix] [--max-items N] [--refresh] [--offline] [-y]`
  - `src/commands/playlist.py` の `_default_max_items(history: HistoryManager) -> int`

- [ ] **Step 1: 失敗するテストを書く**

`tests/commands/test_playlist_command.py` の末尾に追記:

```python
class TestOrphansQuotaControl:
    """orphans の予算制・中断・進捗記録。"""

    def test_default_max_items_uses_budget(self, monkeypatch):
        from src.commands import playlist as playlist_cmd

        history = MagicMock()
        history.get_all_records.return_value = []

        # pydantic の PrivateAttr に依存しないよう、メソッドごと差し替える
        monkeypatch.setattr(playlist_cmd.config, "effective_daily_quota", lambda: 10000)
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 1000)

        # 予算 9000 / 50 = 180 件
        assert playlist_cmd._default_max_items(history) == 180

    def test_default_max_items_subtracts_today_uploads(self, monkeypatch):
        import time

        from src.commands import playlist as playlist_cmd

        now = time.time()
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": now} for _ in range(2)
        ]

        monkeypatch.setattr(playlist_cmd.config, "effective_daily_quota", lambda: 10000)
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        # 10000 - 2*1600 = 6800 -> 6800 // 50 = 136
        assert playlist_cmd._default_max_items(history) == 136

    def test_default_max_items_ignores_yesterday_uploads(self, monkeypatch):
        """本日分だけを勘定する (境界の確認)。"""
        import time

        from src.commands import playlist as playlist_cmd

        yesterday = time.time() - 86400 * 2
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": yesterday} for _ in range(5)
        ]

        monkeypatch.setattr(playlist_cmd.config, "effective_daily_quota", lambda: 10000)
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        assert playlist_cmd._default_max_items(history) == 200

    def test_default_max_items_never_negative(self, monkeypatch):
        import time

        from src.commands import playlist as playlist_cmd

        now = time.time()
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": now} for _ in range(100)
        ]

        monkeypatch.setattr(playlist_cmd.config, "effective_daily_quota", lambda: 10000)
        monkeypatch.setattr(playlist_cmd.config.quota, "reserve", 0)

        assert playlist_cmd._default_max_items(history) == 0

    def test_fix_orphans_stops_on_quota_error(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaExceededError, QuotaLedger

        orphans = [
            {"id": f"v{i}", "title": f"動画{i}"} for i in range(5)
        ]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        # 3件目で quota 枯渇
        pl_manager.add_video_to_playlist.side_effect = [
            True, True, QuotaExceededError("out of quota"), True, True
        ]
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=5, yes=True
        )

        assert assigned == 2, "枯渇前の2件だけが成功する"
        assert remaining == 3, "残り3件が報告される"
        assert pl_manager.add_video_to_playlist.call_count == 3, "枯渇後は呼ばない"

    def test_fix_orphans_records_synced_state(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}, {"id": "v2", "title": "動画2"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.side_effect = [True, False]
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        _fix_orphans(orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True)

        history.set_playlist_synced.assert_any_call("v1", True)
        history.set_playlist_synced.assert_any_call("v2", False)

    def test_fix_orphans_respects_max_items(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": f"v{i}", "title": f"動画{i}"} for i in range(10)]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=3, yes=True
        )

        assert assigned == 3
        assert remaining == 7
        assert pl_manager.add_video_to_playlist.call_count == 3

    def test_fix_orphans_stops_when_ledger_exhausted(self):
        """API が 403 を返す前に、帳簿の予算で自主的に止まる。"""
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": f"v{i}", "title": f"動画{i}"} for i in range(10)]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {"playlist_name": "運動会"}

        # 予算 100 units = insert 2回分
        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100), max_items=10, yes=True
        )

        assert assigned == 2
        assert remaining == 8

    def test_fix_orphans_skips_videos_without_history(self):
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}, {"id": "v2", "title": "動画2"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        # v1 は履歴あり、v2 は履歴なし
        history.get_record_by_video_id.side_effect = [
            {"playlist_name": "運動会"}, None
        ]

        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True
        )

        assert assigned == 1
        assert pl_manager.add_video_to_playlist.call_count == 1

    def test_fix_orphans_falls_back_to_parent_dir(self):
        """playlist_name が無ければ file_path の親ディレクトリ名を使う (既存挙動)。"""
        from src.commands.playlist import _fix_orphans
        from src.lib.core.quota import QuotaLedger

        orphans = [{"id": "v1", "title": "動画1"}]
        pl_manager = MagicMock()
        pl_manager.get_or_create_playlist.return_value = "PL1"
        pl_manager.add_video_to_playlist.return_value = True
        history = MagicMock()
        history.get_record_by_video_id.return_value = {
            "playlist_name": None, "file_path": "/videos/2011運動会/a.mp4"
        }

        _fix_orphans(orphans, pl_manager, history, QuotaLedger(100000), max_items=10, yes=True)

        pl_manager.get_or_create_playlist.assert_called_once_with("2011運動会")
```

冒頭に必要な import（ファイル先頭の既存 import に合わせて追加）:

```python
from unittest.mock import MagicMock
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/commands/test_playlist_command.py::TestOrphansQuotaControl -v --no-cov`
Expected: FAIL — `ImportError: cannot import name '_default_max_items'` および
`_fix_orphans` のシグネチャ不一致（現在は `(orphans, pl_manager, yes)`）

- [ ] **Step 3: `VideoManager` にキャッシュ対応を追加**

`src/lib/video/manager.py` の import と `__init__` を変更:

```python
import logging
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..core.quota import QuotaExceededError, is_quota_error
from ..data.snapshot import SnapshotCache

logger = logging.getLogger("youtube_up")


class VideoManager:
    """
    Manages general YouTube Video interactions (metadata, settings, deletion).
    """

    def __init__(self, credentials, cache: Optional[SnapshotCache] = None):
        self.credentials = credentials
        self._cache = cache
```

`get_all_uploaded_videos`（149行目〜）のシグネチャと前後を変更:

```python
    def get_all_uploaded_videos(
        self, refresh: bool = False, offline: bool = False
    ) -> List[Dict[str, str]]:
        """
        Retrieves all videos uploaded by the authenticated user.
        公開状態 (privacyStatus) も含めて返す。

        refresh=True: キャッシュを無視して API から取り直す
        offline=True: API を叩かず、期限切れでもキャッシュを使う
                      (キャッシュが空なら RuntimeError)
        """
        if offline:
            if self._cache is None:
                raise RuntimeError(
                    "offline モードにはキャッシュが必要です。"
                    "settings.yaml で cache.enabled を有効にしてください。"
                )
            cached = self._cache.load_videos()
            if not cached:
                raise RuntimeError(
                    "キャッシュが空のため offline モードで実行できません。"
                    "クォータに余裕があるときに --refresh 付きで実行してください。"
                )
            return cached

        if self._cache is not None and not refresh and self._cache.is_fresh("videos"):
            cached = self._cache.load_videos()
            if cached:
                logger.info(f"Loaded {len(cached)} videos from cache.")
                return cached

        try:
```

これ以降の `try:` ブロック本体（現行 154-209行目の `channels().list` から
privacy の batch fetch まで）は**一切変更しない**。

続く `logger.info(...)` と `return videos`（210-211行目）および
`except HttpError` ブロック（213-215行目）を、次のように置き換える:

```python
            if self._cache is not None:
                self._cache.save_videos(videos)
                self._cache.mark_complete("videos")

            logger.info(f"Found {len(videos)} uploaded videos.")
            return videos

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while fetching videos: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to fetch uploaded videos: {e}")
            return []
```

- [ ] **Step 4: `orphans` コマンドを書き換える**

`src/commands/playlist.py` の import を変更:

```python
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..lib.auth.auth import get_credentials
from ..lib.core.config import config
from ..lib.core.logger import setup_logging
from ..lib.core.quota import COSTS, QuotaExceededError, QuotaLedger
from ..lib.data.history import HistoryManager
from ..lib.data.snapshot import SnapshotCache
from ..lib.video.playlist import PlaylistManager
```

ファイル末尾のヘルパーとコマンドを次のように置き換える（既存の `_fix_orphans` と
`list_orphans` を削除して差し替え）:

```python
def _make_cache():
    """設定に応じて SnapshotCache を作る。無効なら None。"""
    if not config.cache.enabled:
        return None
    return SnapshotCache(db_path=config.cache.path, ttl_hours=config.cache.ttl_hours)


def _default_max_items(history: HistoryManager) -> int:
    """本日の残り予算から処理可能な件数を見積もる。

    本日のアップロード件数 x 1600 を使用済みとみなす。実際の残量は
    API 側にしか無いため厳密ではないが、QuotaLedger と 403 検知で補う。

    「本日」の境界は既存の check_quota_limit (upload_manager.py:44-45) と
    揃えてローカル時間の午前0時とする。
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    records = history.get_all_records(limit=0)
    today_uploads = [
        r for r in records
        if r.get("status") == "success" and r.get("timestamp", 0) >= today_start
    ]
    used = len(today_uploads) * COSTS["upload"]
    budget = max(0, config.effective_daily_quota() - config.quota.reserve - used)
    return budget // COSTS["insert"]


def _resolve_target_playlist(record) -> str:
    """履歴レコードから割り当て先のプレイリスト名を決める。

    playlist_name を優先し、無ければファイルパスの親ディレクトリ名を使う。
    """
    if not record:
        return None

    target = record.get("playlist_name")
    if target:
        return target

    file_path = record.get("file_path")
    if file_path:
        try:
            return Path(file_path).parent.name
        except Exception:
            return None
    return None


def _fix_orphans(orphans, pl_manager, history, ledger, max_items, yes):
    """オーファンをプレイリストへ割り当てる。

    Returns: (assigned, remaining) — 成功件数と未処理件数。
    quota 枯渇・予算超過・max_items 到達のいずれかで中断する。
    """
    targets = orphans[:max_items]

    if not yes:
        estimated = ledger.cost_of("insert", len(targets))
        console.print(
            f"\n[bold]見積もり:[/] {len(targets)} 件 x {COSTS['insert']} units "
            f"= {estimated:,} units"
        )
        if not typer.confirm(
            f"{len(targets)} 件をローカル履歴に基づいてプレイリストへ割り当てますか?"
        ):
            raise typer.Abort()

    console.print("\n[bold]Assigning Orphans...[/]")

    assigned = 0
    processed = 0

    for orphan in targets:
        vid_id = orphan["id"]
        record = history.get_record_by_video_id(vid_id)
        target_playlist = _resolve_target_playlist(record)

        if not target_playlist:
            console.print(f"[dim]Skipping {orphan['title']} (no history/playlist found)[/]")
            processed += 1
            continue

        if not ledger.can_afford("insert"):
            console.print(
                f"[bold yellow]予算上限に達しました "
                f"({ledger.spent:,}/{ledger.budget:,} units)。中断します。[/]"
            )
            break

        try:
            pl_id = pl_manager.get_or_create_playlist(target_playlist)
            if not pl_id:
                console.print(
                    f"[red]Failed to get/create playlist {target_playlist} "
                    f"for {orphan['title']}[/]"
                )
                processed += 1
                continue

            ok = pl_manager.add_video_to_playlist(pl_id, vid_id)
            ledger.charge("insert")
            history.set_playlist_synced(vid_id, ok)

            if ok:
                assigned += 1
                console.print(f"[green]Assigned {orphan['title']} -> {target_playlist}[/]")
            else:
                console.print(f"[red]Failed to assign {orphan['title']} -> {target_playlist}[/]")

            processed += 1

        except QuotaExceededError:
            console.print(
                "\n[bold red]クォータを使い切りました。処理を中断します。[/]"
            )
            console.print(
                "[dim]太平洋時間の深夜 (日本時間の16〜17時頃) にリセットされます。"
                "リセット後に同じコマンドを再実行すると、残りから再開します。[/]"
            )
            break

    remaining = len(orphans) - processed
    return assigned, remaining


@app.command("orphans")
def list_orphans(
    fix: bool = typer.Option(False, "--fix", help="Automatically assign orphans to playlists based on history"),
    max_items: int = typer.Option(None, "--max-items", help="1回の実行で処理する最大件数 (既定: 本日の残り予算から算出)"),
    refresh: bool = typer.Option(False, "--refresh", help="キャッシュを無視してAPIから取得し直す"),
    offline: bool = typer.Option(False, "--offline", help="APIを叩かずキャッシュのみで判定する (0 units)"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation for fix"),
):
    """
    Find videos not in any playlist (orphans) and optionally fix them.
    """
    setup_logging(level="INFO")

    if offline and fix:
        console.print("[bold red]--offline と --fix は同時に指定できません。[/]")
        raise typer.Exit(code=1)

    cache = _make_cache()
    history = HistoryManager()

    try:
        credentials = get_credentials()
        pl_manager = PlaylistManager(credentials, cache=cache)
        from ..lib.video.manager import VideoManager
        vid_manager = VideoManager(credentials, cache=cache)

        if offline:
            console.print("[yellow]オフラインモード: キャッシュから読み込みます (0 units)[/]")
        else:
            console.print("[yellow]Fetching all uploaded videos and playlist data... (this may take a while)[/]")

        try:
            all_videos = vid_manager.get_all_uploaded_videos(refresh=refresh, offline=offline)
            playlist_map = pl_manager.get_all_playlists_map(refresh=refresh, offline=offline)
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため取得できませんでした。[/]")
            console.print("[dim]--offline を付けるとキャッシュから調査できます。[/]")
            raise typer.Exit(code=1)
        except RuntimeError as e:
            console.print(f"[bold red]{e}[/]")
            raise typer.Exit(code=1)

        if not all_videos:
            console.print("[red]No uploaded videos found or API error.[/]")
            return

        videos_in_playlists = set()
        for vid_set in playlist_map.values():
            videos_in_playlists.update(vid_set)

        orphans = [vid for vid in all_videos if vid["id"] not in videos_in_playlists]

        console.print(f"[bold]Total Videos:[/] {len(all_videos)}")
        console.print(f"[bold]Playlists Scanned:[/] {len(playlist_map)}")
        console.print(f"[bold]Videos in Playlists:[/] {len(videos_in_playlists)}")
        console.print(f"[bold red]Orphan Videos:[/] {len(orphans)}")

        if not orphans:
            console.print("[green]No orphan videos found. All videos are in at least one playlist.[/]")
            return

        # 内訳を集計する (割り当て先の有無と、記録済みの同期状態)
        with_history = 0
        synced_failed = 0
        synced_unknown = 0
        for o in orphans:
            record = history.get_record_by_video_id(o["id"])
            if _resolve_target_playlist(record):
                with_history += 1
            if record is not None:
                if record.get("playlist_synced") == 0:
                    synced_failed += 1
                elif record.get("playlist_synced") is None:
                    synced_unknown += 1

        console.print(f"[bold]  うち履歴から割り当て先が判明:[/] {with_history}")
        console.print(f"[bold]  うち割り当て先不明 (スキップ対象):[/] {len(orphans) - with_history}")
        console.print(
            f"[dim]  同期状態の内訳: 追加失敗として記録済み {synced_failed} / "
            f"不明 (この機能より前の記録) {synced_unknown}[/]"
        )

        console.print("\n[bold]Orphan Videos:[/]")
        for orphan in orphans:
            console.print(f"- {orphan['title']} ({orphan['id']})")

        if not fix:
            console.print("\n[dim]Run with --fix to attempt automatic assignment based on local history.[/]")
            return

        limit = max_items if max_items is not None else _default_max_items(history)
        if limit <= 0:
            console.print(
                "[bold red]本日の推定残量では1件も処理できません。"
                "クォータのリセット後に再実行してください。[/]"
            )
            return

        ledger = QuotaLedger(limit * COSTS["insert"])
        assigned, remaining = _fix_orphans(orphans, pl_manager, history, ledger, limit, yes)

        console.print(
            f"\n[bold green]完了: {assigned} 件を割り当てました[/] "
            f"(消費 約 {ledger.spent:,} units)"
        )
        if remaining > 0:
            console.print(
                f"[bold yellow]残り {remaining} 件[/] — "
                "同じコマンドを再実行すると残りから再開します。"
            )

    finally:
        history.close()
        if cache is not None:
            cache.close()
```

- [ ] **Step 5: テストを実行して成功を確認**

Run: `uv run pytest tests/commands/test_playlist_command.py -v --no-cov`
Expected: PASS — 新規8件に加え既存全件

- [ ] **Step 6: 全テストを実行して回帰がないことを確認**

Run: `uv run pytest -q`
Expected: 全件 PASS、カバレッジ 80% 以上

- [ ] **Step 7: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 8: コミット**

```bash
git add src/commands/playlist.py src/lib/video/manager.py tests/commands/test_playlist_command.py
git commit -m "feat: orphans に予算制・quota 中断・差分再開・オフライン調査を追加

--max-items で1回の処理件数を制限し、QuotaLedger で API が 403 を
返す前に自主的に停止する。quota 枯渇時は即座に中断して
残件数を報告するようにした。

成功したものは playlist_synced に記録するため、再実行時は
残りから再開できる。--offline でキャッシュのみを使えば
クォータ枯渇中でも調査できる。"
```

---

## Task 9: アップロード時のプレイリスト追加失敗を記録

**Files:**
- Modify: `src/services/upload_manager.py:104-155`（`post_upload_sync`）
- Test: `tests/services/test_upload_manager.py`

**Interfaces:**
- Consumes: Task 1 の `QuotaExceededError`、Task 4 の `HistoryManager.set_playlist_synced`
- Produces: なし（既存の `post_upload_sync` の挙動変更）

**これがオーファンの発生源を断つ修正。**

- [ ] **Step 1: 失敗するテストを書く**

`tests/services/test_upload_manager.py` の末尾に追記:

```python
class TestPostUploadPlaylistSync:
    """プレイリスト追加の成否を履歴に記録する。"""

    @staticmethod
    def _args(playlist_manager, history):
        """post_upload_sync の共通引数を組み立てる。"""
        from pathlib import Path

        progress = MagicMock()
        return dict(
            file_path=Path("/videos/運動会/a.mp4"),
            file_hash="h1",
            file_size=100,
            video_id="vid1",
            metadata={"title": "t"},
            target_playlist="運動会",
            playlist_manager=playlist_manager,
            uploader=MagicMock(),
            history=history,
            progress=progress,
        )

    @pytest.mark.asyncio
    async def test_records_success(self):
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.return_value = True
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", True)

    @pytest.mark.asyncio
    async def test_records_failure_when_add_returns_false(self):
        """戻り値 False を握りつぶさず記録する (オーファンの発生源)。"""
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.return_value = False
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_records_failure_when_playlist_not_created(self):
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = None
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_quota_error_is_recorded_and_propagated(self):
        """quota 枯渇は記録した上で上位に伝播させ、アップロード全体を止める。"""
        from src.lib.core.quota import QuotaExceededError
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.return_value = "PL1"
        pl.add_video_to_playlist.side_effect = QuotaExceededError("out")
        history = MagicMock()

        with pytest.raises(QuotaExceededError):
            await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_generic_exception_is_recorded_and_swallowed(self):
        """quota 以外の例外は従来どおり握りつぶすが、記録は残す。"""
        from src.services.upload_manager import post_upload_sync

        pl = MagicMock()
        pl.get_or_create_playlist.side_effect = ValueError("boom")
        history = MagicMock()

        await post_upload_sync(**self._args(pl, history))

        history.set_playlist_synced.assert_called_once_with("vid1", False)

    @pytest.mark.asyncio
    async def test_no_playlist_manager_does_not_record(self):
        """プレイリスト管理を使わない場合は記録しない (NULL のまま)。"""
        from src.services.upload_manager import post_upload_sync

        history = MagicMock()
        args = self._args(None, history)

        await post_upload_sync(**args)

        history.set_playlist_synced.assert_not_called()
```

ファイル先頭に必要な import が無ければ追加:

```python
import pytest
from unittest.mock import MagicMock
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/services/test_upload_manager.py::TestPostUploadPlaylistSync -v --no-cov`
Expected: FAIL — `AssertionError: Expected 'set_playlist_synced' to have been called once`
（現在は成否を記録していないため）

- [ ] **Step 3: 実装を書く**

`src/services/upload_manager.py` の import に追加:

```python
from ..lib.core.quota import QuotaExceededError
```

`post_upload_sync` のプレイリスト追加部分（124-139行目）を置き換える:

```python
    # プレイリストへの追加
    if playlist_manager:
        try:
            pl_id = await asyncio.to_thread(
                playlist_manager.get_or_create_playlist,
                target_playlist,
                config.upload.privacy_status
            )
            if pl_id:
                ok = await asyncio.to_thread(
                    playlist_manager.add_video_to_playlist, pl_id, video_id
                )
                history.set_playlist_synced(video_id, ok)
                if ok:
                    progress.console.print(f"[dim]Added to playlist: {target_playlist}[/]")
                else:
                    progress.console.print(
                        f"[yellow]Warning: プレイリストへの追加に失敗しました: {target_playlist}"
                        f" (yt-up playlist orphans --fix で後から復旧できます)[/]"
                    )
            else:
                history.set_playlist_synced(video_id, False)
                progress.console.print(
                    f"[yellow]Warning: プレイリストを取得/作成できませんでした: {target_playlist}[/]"
                )
        except QuotaExceededError:
            # 枯渇状態で走り続けても意味がないので上位へ伝播させ、全体を停止する
            history.set_playlist_synced(video_id, False)
            logger.error(f"Quota exceeded while adding to playlist {target_playlist}")
            raise
        except Exception as e:
            history.set_playlist_synced(video_id, False)
            logger.error(f"Failed to add to playlist {target_playlist}: {e}")
            progress.console.print(f"[red]Warning: Failed to add to playlist: {e}[/]")
```

`handle_upload_error` が `QuotaExceededError` を quota 枯渇として扱えるよう、
関数冒頭（170行目 `if isinstance(e, HttpError):` の直前）に分岐を追加:

```python
    if isinstance(e, QuotaExceededError):
        progress.console.print("[bold red]CRITICAL: YouTube API Quota Exceeded![/]")
        progress.console.print("Stopping all further uploads. Please try again tomorrow.")
        stop_event.set()
        return

    if isinstance(e, HttpError):
        ...
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `uv run pytest tests/services/test_upload_manager.py -v --no-cov`
Expected: PASS — 新規6件に加え既存全件

- [ ] **Step 5: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: コミット**

```bash
git add src/services/upload_manager.py tests/services/test_upload_manager.py
git commit -m "fix: プレイリスト追加の失敗を握りつぶさず記録する

post_upload_sync が add_video_to_playlist の戻り値を検査せず、
失敗しても Added to playlist と表示していた。履歴も success の
まま残るため、オーファンが静かに量産されていた。

成否を playlist_synced に記録し、失敗時は警告を表示する。
quota 枯渇は上位に伝播させてアップロード全体を停止する。"
```

---

## Task 10: dedupe コマンド

**Files:**
- Modify: `src/commands/playlist.py`（コマンド追加）
- Test: `tests/commands/test_playlist_command.py`

**Interfaces:**
- Consumes: Task 1 の `QuotaExceededError` / `QuotaLedger` / `COSTS`、
  Task 6 の `get_duplicate_playlists()` / `PlaylistInfo`、
  Task 7 の `PlaylistManager(credentials, cache=...)`
- Produces:
  - CLI: `yt-up playlist dedupe [--fix] [--max-items N] [--refresh] [-y]`
  - `src/commands/playlist.py` の `_merge_duplicate_group(canonical, duplicates, pl_manager, playlist_map, ledger, max_items) -> Tuple[int, int]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/commands/test_playlist_command.py` の末尾に追記:

```python
class TestDedupe:
    """重複プレイリストの統合。"""

    @staticmethod
    def _info(pid, title, published):
        from src.lib.video.playlist import PlaylistInfo

        return PlaylistInfo(
            id=pid, title=title, item_count=0, privacy="private", published_at=published
        )

    def test_merge_moves_videos_to_canonical(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1"}, "PL_NEW": {"v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 2
        assert deleted == 1
        assert pl_manager.add_video_to_playlist.call_count == 2
        pl_manager.add_video_to_playlist.assert_any_call("PL_OLD", "v2")
        pl_manager.add_video_to_playlist.assert_any_call("PL_OLD", "v3")
        pl_manager.delete_playlist.assert_called_once_with("PL_NEW")

    def test_merge_skips_insert_for_already_present_video(self):
        """正にすでに入っている動画は insert を省き delete だけ行う (50 units 節約)。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1", "v2"}, "PL_NEW": {"v2"}}

        pl_manager = MagicMock()
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        pl_manager.add_video_to_playlist.assert_not_called()
        pl_manager.remove_video_from_playlist.assert_called_once_with("PL_NEW", "v2")
        assert moved == 1
        assert deleted == 1

    def test_merge_stops_on_quota_error(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaExceededError, QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.side_effect = [
            True, QuotaExceededError("out"), True
        ]
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 1
        assert deleted == 0, "全部移せていないので削除しない"
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_does_not_delete_when_max_items_reached(self):
        """上限で打ち切った場合、中身が残るプレイリストは削除しない。"""
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": set(), "PL_NEW": {"v1", "v2", "v3"}}

        pl_manager = MagicMock()
        pl_manager.add_video_to_playlist.return_value = True
        pl_manager.remove_video_from_playlist.return_value = True

        moved, deleted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=2
        )

        assert moved == 2
        assert deleted == 0
        pl_manager.delete_playlist.assert_not_called()

    def test_merge_empty_duplicate_is_deleted_directly(self):
        from src.commands.playlist import _merge_duplicate_group
        from src.lib.core.quota import QuotaLedger

        canonical = self._info("PL_OLD", "運動会", "2020-01-01T00:00:00Z")
        dup = self._info("PL_NEW", "運動会", "2024-01-01T00:00:00Z")
        playlist_map = {"PL_OLD": {"v1"}, "PL_NEW": set()}

        pl_manager = MagicMock()

        moved, deleted = _merge_duplicate_group(
            canonical, [dup], pl_manager, playlist_map, QuotaLedger(100000), max_items=100
        )

        assert moved == 0
        assert deleted == 1
        pl_manager.add_video_to_playlist.assert_not_called()
        pl_manager.delete_playlist.assert_called_once_with("PL_NEW")
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `uv run pytest tests/commands/test_playlist_command.py::TestDedupe -v --no-cov`
Expected: FAIL — `ImportError: cannot import name '_merge_duplicate_group'`

- [ ] **Step 3: `PlaylistManager.delete_playlist` を追加**

`src/lib/video/playlist.py` の `rename_playlist` の直後に追加:

```python
    def delete_playlist(self, playlist_id: str) -> bool:
        """プレイリストを削除する (中の動画自体は削除されない)。"""
        try:
            service = build(
                "youtube", "v3", credentials=self.credentials, cache_discovery=False
            )
            service.playlists().delete(id=playlist_id).execute()

            # キャッシュからも取り除く
            self._playlists = [p for p in self._playlists if p.id != playlist_id]
            self._playlist_cache = self._build_title_index(self._playlists)

            logger.info(f"Deleted playlist {playlist_id}")
            return True

        except HttpError as e:
            if is_quota_error(e):
                logger.error(f"Quota exceeded while deleting {playlist_id}: {e}")
                raise QuotaExceededError(str(e)) from e
            logger.error(f"Failed to delete playlist {playlist_id}: {e}")
            return False
```

対応するテストを `tests/lib/video/test_playlist.py` の `TestPlaylistQuotaHandling` に追記:

```python
    @patch("src.lib.video.playlist.build")
    def test_delete_playlist_success(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        self.assertTrue(self.manager.delete_playlist("PL1"))
        mock_service.playlists().delete.assert_called_with(id="PL1")

    @patch("src.lib.video.playlist.build")
    def test_delete_playlist_raises_on_quota_error(self, mock_build):
        from src.lib.core.quota import QuotaExceededError

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().delete.return_value.execute.side_effect = (
            self._quota_error()
        )
        with self.assertRaises(QuotaExceededError):
            self.manager.delete_playlist("PL1")

    @patch("src.lib.video.playlist.build")
    def test_delete_playlist_returns_false_on_other_error(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.playlists().delete.return_value.execute.side_effect = (
            self._other_error()
        )
        self.assertFalse(self.manager.delete_playlist("PL1"))
```

- [ ] **Step 4: `dedupe` コマンドを書く**

`src/commands/playlist.py` の末尾に追加:

```python
def _merge_duplicate_group(
    canonical, duplicates, pl_manager, playlist_map, ledger, max_items
):
    """1つの重複グループを統合する。

    canonical に動画を集約し、空になった重複プレイリストを削除する。

    Returns: (moved, deleted) — 移動した動画数と削除したプレイリスト数。
    途中で中断した場合、中身が残るプレイリストは削除しない。
    """
    canonical_videos = set(playlist_map.get(canonical.id, set()))
    moved = 0
    deleted = 0

    for dup in duplicates:
        dup_videos = playlist_map.get(dup.id, set())
        fully_moved = True

        for video_id in sorted(dup_videos):
            if moved >= max_items:
                fully_moved = False
                break

            needs_insert = video_id not in canonical_videos
            required = ledger.cost_of("insert") if needs_insert else 0
            required += ledger.cost_of("delete")
            if ledger.remaining < required:
                fully_moved = False
                break

            try:
                if needs_insert:
                    if not pl_manager.add_video_to_playlist(canonical.id, video_id):
                        console.print(
                            f"[red]移動失敗: {video_id} -> {canonical.title}[/]"
                        )
                        fully_moved = False
                        continue
                    ledger.charge("insert")
                    canonical_videos.add(video_id)

                if not pl_manager.remove_video_from_playlist(dup.id, video_id):
                    console.print(f"[red]削除失敗: {video_id} from {dup.id}[/]")
                    fully_moved = False
                    continue
                ledger.charge("delete")
                moved += 1

            except QuotaExceededError:
                console.print("\n[bold red]クォータを使い切りました。中断します。[/]")
                return moved, deleted

        if fully_moved:
            try:
                if pl_manager.delete_playlist(dup.id):
                    deleted += 1
                    console.print(f"[green]重複プレイリストを削除: {dup.id}[/]")
            except QuotaExceededError:
                console.print("\n[bold red]クォータを使い切りました。中断します。[/]")
                return moved, deleted

    return moved, deleted


@app.command("dedupe")
def dedupe_playlists(
    fix: bool = typer.Option(False, "--fix", help="重複を統合する (動画を最古のプレイリストへ移動し、空になった方を削除)"),
    max_items: int = typer.Option(50, "--max-items", help="1回の実行で移動する最大動画数"),
    refresh: bool = typer.Option(False, "--refresh", help="キャッシュを無視してAPIから取得し直す"),
    yes: bool = typer.Option(False, "-y", "--yes", help="確認プロンプトを省略"),
):
    """
    同名の重複プレイリストを検出し、必要なら統合する。

    検出のみ (--fix なし) はキャッシュがあれば 0 units で実行できる。
    """
    setup_logging(level="INFO")

    cache = _make_cache()

    try:
        credentials = get_credentials()
        pl_manager = PlaylistManager(credentials, cache=cache)

        try:
            duplicates = pl_manager.get_duplicate_playlists()
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため取得できませんでした。[/]")
            raise typer.Exit(code=1)

        if not duplicates:
            console.print("[green]重複しているプレイリストはありません。[/]")
            return

        total_dups = sum(len(v) - 1 for v in duplicates.values())
        console.print(f"[bold red]重複しているタイトル:[/] {len(duplicates)}")
        console.print(f"[bold red]余剰プレイリスト:[/] {total_dups}")

        table = Table(title="Duplicate Playlists")
        table.add_column("Title", style="magenta")
        table.add_column("正 (最古)", style="green")
        table.add_column("重複", style="yellow")
        for title, items in duplicates.items():
            table.add_row(
                title, items[0].id, ", ".join(p.id for p in items[1:])
            )
        console.print(table)

        if not fix:
            console.print("\n[dim]--fix を付けると統合します。[/]")
            return

        try:
            playlist_map = pl_manager.get_all_playlists_map(refresh=refresh)
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため統合できません。[/]")
            raise typer.Exit(code=1)

        movable = sum(
            len(playlist_map.get(p.id, set()))
            for items in duplicates.values()
            for p in items[1:]
        )
        target_count = min(movable, max_items)
        estimated = target_count * (COSTS["insert"] + COSTS["delete"]) + total_dups * COSTS["delete"]

        console.print(
            f"\n[bold]見積もり:[/] 最大 {target_count} 本の移動 + "
            f"{total_dups} 個の削除 = 約 {estimated:,} units"
        )

        if not yes:
            if not typer.confirm("統合を実行しますか?"):
                raise typer.Abort()

        ledger = QuotaLedger(estimated)
        total_moved = 0
        total_deleted = 0

        for title, items in duplicates.items():
            if total_moved >= max_items:
                break
            console.print(f"\n[bold]統合中: {title}[/]")
            moved, deleted = _merge_duplicate_group(
                items[0], items[1:], pl_manager, playlist_map,
                ledger, max_items - total_moved,
            )
            total_moved += moved
            total_deleted += deleted

        console.print(
            f"\n[bold green]完了: {total_moved} 本を移動、"
            f"{total_deleted} 個のプレイリストを削除しました[/] "
            f"(消費 約 {ledger.spent:,} units)"
        )
        if cache is not None:
            cache.clear()
            console.print("[dim]キャッシュを破棄しました (次回は最新を取得します)。[/]")

    finally:
        if cache is not None:
            cache.close()
```

- [ ] **Step 5: テストを実行して成功を確認**

Run: `uv run pytest tests/commands/test_playlist_command.py tests/lib/video/test_playlist.py -v --no-cov`
Expected: PASS — 新規8件に加え既存全件

- [ ] **Step 6: 全テストとカバレッジを確認**

Run: `uv run pytest`
Expected: 全件 PASS、`TOTAL` のカバレッジが 80% 以上

- [ ] **Step 7: lint を通す**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 8: README を更新**

`README.md` のプレイリスト操作のセクションに `dedupe` と `orphans` の新オプションを追記する。
既存の記述スタイル（コマンド例＋短い説明）に合わせること。追記する内容:

```markdown
# 孤立動画（どのプレイリストにも入っていない動画）を検出
yt-up playlist orphans
yt-up playlist orphans --offline           # キャッシュのみで判定 (0 units)
yt-up playlist orphans --fix --max-items 50  # 50件だけ割り当てる

# 同名の重複プレイリストを検出・統合
yt-up playlist dedupe                      # 検出のみ (キャッシュがあれば 0 units)
yt-up playlist dedupe --fix --max-items 50
```

`Quota (API割り当て) について` のセクションに、プレイリスト操作のコストを追記:

```markdown
各操作の消費ユニット:

| 操作 | units |
|---|---|
| 動画のアップロード (`videos.insert`) | 1,600 |
| プレイリストへの追加 (`playlistItems.insert`) | 50 |
| プレイリストの作成・削除 | 50 |
| 一覧の取得 (`*.list`、1ページ50件) | 1 |

`playlist orphans --fix` は1本あたり 50 units を消費します。
`--max-items` で1回の処理件数を制限でき、クォータを使い切った場合は
自動的に中断して残件数を報告します。翌日に同じコマンドを再実行すると
残りから再開します。
```

- [ ] **Step 9: コミット**

```bash
git add src/commands/playlist.py src/lib/video/playlist.py README.md tests/
git commit -m "feat: 重複プレイリストを検出・統合する dedupe コマンドを追加

ページネーション未対応のバグによって生成された同名プレイリストを
整理する。検出のみならキャッシュから 0 units で実行できる。

--fix は最古のプレイリストへ動画を集約し、空になった重複を削除する。
正にすでに存在する動画は insert を省いて delete のみ行い、
中断時は中身が残るプレイリストを削除しない。"
```

---

## 完了後の検証手順

実装完了後、クォータがリセットされてから（太平洋時間の深夜 = 日本時間の 16:00〜17:00 頃）実施する。

- [ ] **1. 全テストと lint**

```bash
uv run pytest
uv run ruff check src tests
```

- [ ] **2. プレイリストの実態を確認**

```bash
uv run yt-up playlist list | tail -5
```

544 より多ければ、バグによって重複が生成されていたことになる。

- [ ] **3. 重複の実態を把握**

```bash
uv run yt-up playlist dedupe
```

- [ ] **4. 修正後の真のオーファン件数を確認**

```bash
uv run yt-up playlist orphans
```

修正前と比べて激減しているはず（誤判定が消えるため）。

- [ ] **5. キャッシュが効いていることを確認**

```bash
uv run yt-up playlist orphans --offline
```

手順4と同じ結果が、API を叩かずに返ること。

- [ ] **6. 少数で --fix の挙動と実消費を確認**

```bash
uv run yt-up playlist orphans --fix --max-items 10
```

10件で止まること、消費ユニットの表示が `500 units` 程度であること、
再実行すると残りから再開することを確認する。

- [ ] **7. 問題なければ予算いっぱいまで実行**

```bash
uv run yt-up playlist orphans --fix
```

- [ ] **8. PR を作成**

```bash
git push -u origin fix/playlist-orphans-quota
gh pr create --title "fix: playlist orphans --fix の Quota 枯渇問題を修正" --body "$(cat <<'EOF'
## 背景

大量アップロード後に `yt-up playlist orphans --fix` が 403 quotaExceeded で停止し、
1日待って再実行しても同じ地点で枯渇する問題を修正しました。

## 原因

1. **`_ensure_cache` のページネーション未対応** — プレイリストが544個ある環境で
   先頭50個しか認識しておらず、`get_or_create_playlist` が既存と同名のプレイリストを
   重複作成し（50 units）、`get_all_playlists_map` がオーファンを大量に誤判定していた
2. **プレイリスト追加失敗の握りつぶし** — `post_upload_sync` が
   `add_video_to_playlist` の戻り値を検査せず、失敗しても「Added to playlist」と
   表示して履歴を success のまま残していた（オーファンの発生源）
3. **中断機構と進捗記録の欠如** — quota 枯渇後も全件ループを回し切り、
   翌日は最初からやり直しになっていた

## 変更内容

- プレイリスト一覧を全ページ取得するよう修正。同名が複数ある場合は最古を正とする
- 重複プレイリストの中身も走査対象に含める
- quota 枯渇を `QuotaExceededError` として送出し、1件の失敗と区別する
- `orphans` に `--max-items` / `--refresh` / `--offline` を追加し、
  予算制・即時中断・差分再開に対応
- YouTube 側の状態を SQLite にキャッシュし、再実行時の読み取りを 0 units にする
- プレイリスト追加の成否を `playlist_synced` 列に記録する
- 重複プレイリストを統合する `playlist dedupe` コマンドを追加

## 効果

| | 修正前 | 修正後 |
|---|---|---|
| オーファン判定 | 誤判定多数 | 正確 |
| 読み取り | 約950 units（毎回） | 初回950 / 2回目以降 0 |
| 書き込み | 誤判定分 × 最大100 units | 真のオーファン × 50 units |
| 枯渇時 | 調査すら不可 | `--offline` で調査可能 |
| 中断時 | 翌日やり直し | 差分再開 |

## テスト

- 新規テスト: quota / snapshot / ページネーション / 重複検出 / 中断 / 差分再開
- `uv run pytest` 全件パス、カバレッジ 80% 以上
- `uv run ruff check src tests` パス

設計書: `docs/superpowers/specs/2026-07-28-playlist-orphans-quota-design.md`
EOF
)"
```
