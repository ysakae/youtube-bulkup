# `playlist orphans --fix` の Quota 枯渇問題 — 設計書

- 作成日: 2026-07-28
- 対象: `src/lib/video/playlist.py`, `src/commands/playlist.py`, `src/services/upload_manager.py`, `src/lib/data/`
- 関連: [QUOTA_INCREASE.md](../../QUOTA_INCREASE.md), [ARCHITECTURE.md](../../ARCHITECTURE.md)

## 1. 問題

大量アップロード後に `uv run yt-up playlist orphans --fix` を実行すると `403 quotaExceeded` で停止する。
1日待って再実行しても、同じ地点で再び枯渇する。

観測されたエラー:

```
Failed to assign 【2011-10-15 にじいろ運動会】20111015085017 -> 2011-10-15 にじいろ運動会
WARNING  Encountered 403 Forbidden with reason "quotaExceeded"
ERROR    Failed to add video mz1l7Crd5bk to playlist PLRb3A4jWIm7s:
         <HttpError 403 ... 'domain': 'youtube.quota', 'reason': 'quotaExceeded'>
```

## 2. 調査結果

### 2.1 環境の実測値

ローカル履歴DB (`upload_history.db`) の集計:

| 項目 | 値 |
|---|---|
| アップロード済み動画 | 10,026 本 |
| `playlist_name` のユニーク数 | 544 種類 |
| 1日あたりのアップロード | 約 90〜100 本 |

調査中に `playlists.list`（1 unit）すら 403 を返した。実行時点でクォータは完全に枯渇していた。

### 2.2 YouTube Data API v3 のコスト

| 操作 | units |
|---|---|
| `*.list` 系（1ページ = 最大50件） | 1 |
| `playlistItems.insert` | 50 |
| `playlists.insert` | 50 |
| `playlistItems.delete` / `playlists.delete` | 50 |
| `videos.insert`（アップロード） | 1,600 |

読み取りは書き込みの 1/50 のコストしかない。**キャッシュ導入だけでは quota 問題は解決しない。**

### 2.3 根本原因

#### 原因1: プレイリスト追加の失敗を握りつぶしている（オーファンの発生源）

`src/services/upload_manager.py:119-139` `post_upload_sync()`:

```python
history.add_record(..., playlist_name=target_playlist, ...)   # 先に success で記録
...
if pl_id:
    await asyncio.to_thread(playlist_manager.add_video_to_playlist, pl_id, video_id)
    progress.console.print(f"[dim]Added to playlist: {target_playlist}[/]")  # 戻り値未検査
```

`add_video_to_playlist()` は失敗時に例外ではなく `False` を返す（`playlist.py:123`）。
その戻り値が検査されていないため、追加が失敗しても「Added to playlist」と表示され、履歴は `success` のまま残る。

アップロード中にクォータが尽きると `videos.insert`(1,600) は通っても後続の `playlistItems.insert`(50) が 403 になる。
この経路で**オーファンが静かに量産される**。

#### 原因2: `_ensure_cache()` が 50 件で打ち止め

`src/lib/video/playlist.py:19-49`:

```python
request = service.playlists().list(
    part="snippet,id", mine=True, maxResults=50)   # ページネーション未対応
response = request.execute()
# Todo: Handle pagination for >50 playlists           ← 33-37行目
```

プレイリストは 544 個あるが、キャッシュに載るのは先頭 50 個のみ。
結果として `get_or_create_playlist()` は残り約 494 個を「存在しない」と判定し、
**既存と同名のプレイリストを新規作成する**（`playlists.insert` = 50 units）。

副作用として、実行のたびに重複プレイリストが増殖する。

#### 原因3: `get_all_playlists_map()` も同じ 50 件制限 — オーファンの大量誤判定

`src/lib/video/playlist.py:363-396` は `_ensure_cache()` の結果を走査するため、
544 個中 50 個のプレイリストの中身しか見ていない。

`src/commands/playlist.py:220-224`:

```python
videos_in_playlists = set()
for vid_set in playlist_map.values():
    videos_in_playlists.update(vid_set)
orphans = [vid for vid in all_videos if vid["id"] not in videos_in_playlists]
```

`videos_in_playlists` が実際の 1/10 程度しか埋まらず、
**すでにプレイリストに入っている動画が大量に「オーファン」と誤判定される**。

原因2と組み合わさると、1本あたり `playlists.insert`(50) + `playlistItems.insert`(50) = **最大 100 units** を消費する。
翌日も同じ誤判定が再現するため、永久に終わらない。

#### 原因4: `_fix_orphans` に中断機構がない

`src/commands/playlist.py:146-189` は quota エラーを検知せず、枯渇後も全件ループを回し切る。
進捗も記録されないため、翌日は最初からやり直しになる。

#### 原因5: `check_quota_limit` が実効性を持っていない

`src/services/upload_manager.py:30-74`:

- `process_video_files` の開始時に **1回だけ**呼ばれ、以降は再評価されない
- 上限超過時も警告を出すだけで、実際の本数制限はしていない（64-68行目）
- コストを `COST_PER_UPLOAD = 1600` のみで計算し、プレイリスト操作（最大 100 units/本）を勘定に入れていない

### 2.4 原因と症状の対応

| 症状 | 原因 |
|---|---|
| 毎日オーファンが増える | 原因1 |
| `--fix` が即座にクォータを溶かす | 原因2・3 |
| 1日待っても同じ地点で枯渇する | 原因3（誤判定が毎回再現）＋ 原因4（進捗が残らない） |
| プレイリストが増えている | 原因2 |

## 3. 設計

### 3.1 全体構成

```
src/lib/core/quota.py       [新規] QuotaExceededError / 判定関数 / QuotaLedger
src/lib/data/snapshot.py    [新規] SnapshotCache（YouTube側状態のキャッシュ）
src/lib/data/history.py     [変更] playlist_synced 列の追加とマイグレーション
src/lib/video/playlist.py   [変更] ページネーション対応・重複検出・quota例外化
src/commands/playlist.py    [変更] orphans の改修 / dedupe コマンド新設
src/services/upload_manager.py [変更] プレイリスト追加の成否を記録
src/lib/core/config.py      [変更] quota / cache セクションの追加
```

### 3.2 A. データ層

#### A-1. `SnapshotCache`（新規 `src/lib/data/snapshot.py`）

YouTube 側の状態を保存する専用 SQLite。`upload_history.db` とは**別ファイル**にする。

責務が異なるため分離する（`HistoryManager` = ローカルのアップロード記録、`SnapshotCache` = リモート状態のキャッシュ）。
片方を削除してももう片方に影響しない点も利点。

```sql
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id  TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    item_count   INTEGER DEFAULT 0,
    privacy      TEXT,
    published_at TEXT,
    fetched_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    fetched_at  REAL NOT NULL,
    PRIMARY KEY (playlist_id, video_id)
);
CREATE TABLE IF NOT EXISTS videos (
    video_id   TEXT PRIMARY KEY,
    title      TEXT,
    privacy    TEXT,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cache_meta (
    kind       TEXT PRIMARY KEY,   -- 'playlists' | 'playlist_items' | 'videos'
    fetched_at REAL NOT NULL       -- 全件取得が「完了」した時刻
);
CREATE INDEX IF NOT EXISTS idx_playlists_title ON playlists (title);
CREATE INDEX IF NOT EXISTS idx_items_video ON playlist_items (video_id);
```

公開インターフェース:

```python
class SnapshotCache:
    def __init__(self, db_path: str | None = None, ttl_hours: int = 24) -> None: ...

    def is_fresh(self, kind: str) -> bool:
        """kind ('playlists' | 'playlist_items' | 'videos') が TTL 内かを判定。"""
    def mark_complete(self, kind: str) -> None:
        """全件取得の完了を記録する。"""

    def save_playlists(self, playlists: list[dict]) -> None: ...
    def load_playlists(self) -> list[dict]: ...

    def save_playlist_items(self, playlist_id: str, video_ids: set[str]) -> None:
        """該当 playlist_id の既存行を削除してから書き直す（全置換）。"""
    def load_playlist_map(self) -> dict[str, set[str]]: ...

    def save_videos(self, videos: list[dict]) -> None: ...
    def load_videos(self) -> list[dict]: ...

    def clear(self, kind: str | None = None) -> None: ...
    def close(self) -> None: ...
```

**鮮度判定は `cache_meta` テーブルで行う。** 各テーブルの `MAX(fetched_at)` を使うと、
取得が途中で中断して部分的なデータしか無い状態でも「新鮮」と誤判定してしまうため。

`mark_complete(kind)` は全件の取得ループが最後まで完走したときにのみ呼ぶ。
中断した場合は `cache_meta` が更新されないので、次回は必ず API から取り直す（安全側に倒す）。
各テーブルの `fetched_at` 列は個別行の取得時刻として保持し、デバッグと部分更新の判断に使う。

キャッシュの取得モードを 3 つ用意する:

| モード | 挙動 |
|---|---|
| 既定 | TTL 内ならキャッシュ、期限切れなら API を叩いて更新 |
| `--refresh` | TTL を無視して必ず API から取得し直す |
| `--offline` | API を一切叩かない。キャッシュが空なら明示的にエラー終了 |

`--offline` により、**クォータ枯渇中でも `orphans` の調査が完走できる**。

#### A-2. `uploads.playlist_synced` 列の追加

`src/lib/data/history.py` にマイグレーションを追加する。

```sql
ALTER TABLE uploads ADD COLUMN playlist_synced INTEGER DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_playlist_synced ON uploads (playlist_synced);
```

**三値**とする:

| 値 | 意味 |
|---|---|
| `1` | プレイリストへの追加に成功した |
| `0` | 追加に失敗した（オーファンの確定候補） |
| `NULL` | 不明（この機能より前に記録された既存 10,026 件） |

既存レコードを一律 `0` にすると全件がオーファン候補になってしまうため `NULL` と区別する。
今後のアップロードには確実な値が入るので、**将来的にはオーファン検出が API 不要になる**。

マイグレーションは `_init_schema()` 内で `PRAGMA table_info(uploads)` を検査し、
列が無い場合のみ `ALTER TABLE` を実行する（冪等）。

追加メソッド:

```python
def set_playlist_synced(self, video_id: str, synced: bool) -> None: ...
def get_unsynced_records(self) -> list[dict]:
    """playlist_synced = 0 のレコードを返す。"""
```

### 3.3 B. `PlaylistManager` の修正

#### B-1. `_ensure_cache()` のページネーション対応

`playlists().list()` に `part="snippet,contentDetails,status"` と `pageToken` ループを追加し、
544 個すべてを取得する（コスト: 約 11 units）。

**既存の `_playlist_cache: Dict[str, str]` は実属性のまま残す。**
既存テストがこれに直接代入しているため（`test_playlist.py:138, 279, 296, 315, 418, 451`）、
プロパティ化すると壊れる。意味だけを「タイトル → **正の**プレイリストID」に厳密化する。

全件情報を保持する属性を**追加**する:

```python
@dataclass(frozen=True)
class PlaylistInfo:
    id: str
    title: str
    item_count: int
    privacy: str
    published_at: str

# PlaylistManager の内部状態
self._playlist_cache: Dict[str, str] = {}      # title -> 正のID（既存・意味を厳密化）
self._playlists: List[PlaylistInfo] = []       # 全件（重複も含む・新規）
```

`_ensure_cache()` は両方を埋める。同名グループでは `published_at` が最古のものを「正」として
`_playlist_cache` に入れる（後から誤って作成された重複ではなく、本来のプレイリストを選ぶため）。

**外部契約は維持する。** `get_or_create_playlist()` と `find_playlist_id()` は従来どおり
`_playlist_cache` を参照し、単一の `Optional[str]` を返す。

重複プレイリストの中身も走査対象に含める必要があるため、走査用のヘルパーを設ける:

```python
def _all_playlist_ids(self) -> List[str]:
    """走査対象の全プレイリストID。重複プレイリストも含む。
    _playlists が空のとき（テストが _playlist_cache に直接代入した場合など）は
    _playlist_cache の値にフォールバックする。"""
    if self._playlists:
        return [p.id for p in self._playlists]
    return list(self._playlist_cache.values())
```

新規メソッド:

```python
def get_duplicate_playlists(self) -> dict[str, list[PlaylistInfo]]:
    """同名プレイリストが2つ以上あるものだけを {title: [PlaylistInfo, ...]} で返す。
    各リストは published_at 昇順（先頭が「正」）。"""
```

#### B-2. `get_all_playlists_map()` の全件走査

現在の `self._playlist_cache.items()` を走査する実装を `self._all_playlist_ids()` に置き換える。
これにより 544 個すべて（重複プレイリストを含む）の中身を走査するようになる。

重複プレイリストの中身も含めることが重要で、これを漏らすと
「重複側にだけ入っている動画」がオーファンと誤判定されてしまう。

加えて `SnapshotCache` を経由させ、TTL 内ならキャッシュから復元する。

コンストラクタでキャッシュを注入可能にする（依存性逆転・テスト容易性のため）:

```python
def __init__(self, credentials, cache: SnapshotCache | None = None) -> None: ...
```

`cache=None` の場合はキャッシュを使わない（既存の呼び出し側との互換性を保つ）。

#### B-3. quota エラーの例外化（新規 `src/lib/core/quota.py`）

`src/lib/video/uploader.py:22` の `_is_daily_upload_quota_error` をここへ移して共通化する。

```python
class QuotaExceededError(Exception):
    """YouTube API のクォータを使い切ったことを示す。処理の即時中断を要求する。"""

def is_quota_error(exc: HttpError) -> bool:
    """403 quotaExceeded / 429 rateLimitExceeded('Video Uploads per day') を判定。"""
```

`uploader.py` は `is_quota_error` を再利用する形に置き換える（既存の判定ロジックと挙動は変えない）。

`PlaylistManager` の書き込み系メソッド（`get_or_create_playlist`, `add_video_to_playlist`,
`remove_video_from_playlist`）は、**quota エラーのときだけ `False`/`None` を返さず
`QuotaExceededError` を送出する**。それ以外の `HttpError` は従来どおり `False`/`None` を返す。

呼び出し側が「1件の失敗」と「全体の中断が必要な状況」を区別できるようにするため。

#### B-4. `QuotaLedger`（`src/lib/core/quota.py`）

ローカルで消費 units を積算する。

```python
COST = {"list": 1, "insert": 50, "delete": 50, "update": 50, "upload": 1600}

class QuotaLedger:
    def __init__(self, budget: int) -> None: ...
    def charge(self, op: str, count: int = 1) -> None:
        """消費を計上する。budget を超える場合は QuotaExceededError を送出。"""
    def can_afford(self, op: str, count: int = 1) -> bool: ...
    @property
    def spent(self) -> int: ...
    @property
    def remaining(self) -> int: ...
```

API が 403 を返す前に自主的に止まるための仕組み。実際の残量は API 側にしか無いため、
これは**見積もりに基づく安全弁**であり、実際の 403 検知（B-3）と併用する。

### 3.4 C. コマンド層

#### C-1. `orphans` の改修

```
yt-up playlist orphans [--fix] [--max-items N] [--refresh] [--offline] [-y]
```

| オプション | 既定 | 説明 |
|---|---|---|
| `--fix` | off | 履歴に基づきプレイリストへ割り当てる |
| `--max-items N` | 設定の予算から自動算出 | 1回の実行で処理する最大件数 |
| `--refresh` | off | キャッシュを無視して API から取り直す |
| `--offline` | off | API を叩かずキャッシュのみで判定する（0 units） |
| `-y` / `--yes` | off | 確認プロンプトを省略 |

処理の流れ:

1. **収集** — `SnapshotCache` 経由で全動画一覧と全プレイリストマップを構築する（原因3が解消し、誤判定が消える）。
   API を叩いた分の読み取りコストも `QuotaLedger` に計上する（キャッシュヒット時は 0）
2. **判定** — オーファンを算出し、内訳を表示する:
   - 履歴あり（割り当て先が判明）
   - 履歴なし（割り当て先不明 → スキップ対象）
   - `playlist_synced` 別の件数
3. **見積もり** — `--fix` 時は着手前に提示する: `対象 N 件 × 50 units = X units。処理しますか？`
4. **実行** — 1件ずつ処理し、`QuotaLedger` で予算を監視する
5. **中断** — `QuotaExceededError` を捕捉したら**即座にループを抜け**、`N 件完了 / M 件残り` を報告する
6. **記録** — 成功したものは `history.set_playlist_synced(video_id, True)` を書き戻す
   → 翌日は残りだけを処理できる（差分再開）

`--fix` は既存プレイリストが確実に見つかるようになるため、`playlists.insert`（50 units）は
本当に新規のプレイリストにしか発生しない。

#### C-2. `dedupe` コマンド（新規）

```
yt-up playlist dedupe [--fix] [--max-items N] [--refresh] [-y]
```

原因2 によってすでに生成された同名の重複プレイリストを整理する。

- **検出のみ（既定）**: `get_duplicate_playlists()` の結果をキャッシュから表示する（**0 units**）
- **`--fix`**:
  1. 各グループの最古のプレイリストを「正」とする
  2. 重複側の動画を正へ移動する（`playlistItems.insert` 50 + `playlistItems.delete` 50 = **100 units/本**）
     - すでに正に存在する動画は insert を省略し、delete のみ行う（50 units）
  3. 空になった重複プレイリストを削除する（`playlists.delete` = 50 units）
- 見積もり提示・予算制・`QuotaExceededError` での中断は `orphans` と共通の仕組みを使う

コストが大きいため、`--fix` は既定で確認プロンプトを出す。

#### C-3. `upload` の修正（オーファンの発生源を断つ）

`src/services/upload_manager.py` の `post_upload_sync()`:

```python
if playlist_manager:
    try:
        pl_id = await asyncio.to_thread(
            playlist_manager.get_or_create_playlist, target_playlist, config.upload.privacy_status)
        if pl_id:
            ok = await asyncio.to_thread(
                playlist_manager.add_video_to_playlist, pl_id, video_id)
            history.set_playlist_synced(video_id, ok)          # ← 成否を記録
            if ok:
                progress.console.print(f"[dim]Added to playlist: {target_playlist}[/]")
            else:
                progress.console.print(
                    f"[yellow]Warning: プレイリストへの追加に失敗: {target_playlist}"
                    f" (yt-up playlist orphans --fix で後から復旧できます)[/]")
        else:
            history.set_playlist_synced(video_id, False)
    except QuotaExceededError:
        history.set_playlist_synced(video_id, False)
        raise                                                   # 上位の stop_event へ伝播
    except Exception as e:
        history.set_playlist_synced(video_id, False)
        logger.error(f"Failed to add to playlist {target_playlist}: {e}")
        progress.console.print(f"[red]Warning: Failed to add to playlist: {e}[/]")
```

`QuotaExceededError` は `handle_upload_error()` へ伝播させ、既存の `stop_event` 機構で
アップロード全体を停止する（枯渇状態で走り続けても意味がないため）。

### 3.5 D. 設定の追加

`src/lib/core/config.py`:

```python
class QuotaConfig(BaseModel):
    daily_limit: int = 10000   # 実際の GCP 上限に合わせて調整する
    reserve: int = 1000        # 予備として残す units

class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_hours: int = 24
    path: str = "youtube_cache.db"

class AppConfig(BaseModel):
    ...
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
```

`settings.yaml` に対応するセクションを追記する。
`upload.daily_quota_limit` は後方互換のため残すが、`quota.daily_limit` が指定されていればそちらを優先する。

`--max-items` の既定値は次式で算出する:

```
本日のアップロード件数 = uploads テーブルの status='success' かつ timestamp >= 本日0時 の件数
推定使用済み          = 本日のアップロード件数 × 1600
予算                  = max(0, quota.daily_limit - quota.reserve - 推定使用済み)
--max-items の既定値  = 予算 // 50
```

これは既存の `check_quota_limit()`（`upload_manager.py:44-52`）と同じ算出方法である。
実際の残量は API 側にしか無いため厳密ではないが、`QuotaLedger` と 403 検知（B-3）と
併用することで、過大評価しても実害が出ないようにする。

`.gitignore` に `youtube_cache.db` とその WAL/SHM ファイルを追加する。

## 4. 期待される効果

| 項目 | 現在 | 修正後 |
|---|---|---|
| オーファン判定 | **誤判定多数**（544個中50個のPLしか見ていない） | 正確 |
| 読み取りコスト | 約 950 units（毎回） | 初回 950 / 2回目以降 **0**（TTL内） |
| 書き込みコスト | 誤判定分 × 最大 100 units | 真のオーファン数 × 50 units |
| クォータ枯渇時 | 調査すら不可 | `--offline` で調査可能 |
| 中断時の挙動 | 進捗が残らず翌日やり直し | `playlist_synced` により差分再開 |
| 重複プレイリスト | 実行のたびに増殖 | 生成されない ＋ `dedupe` で整理可能 |
| アップロード時の失敗 | 無言で握りつぶし（虚偽の成功表示） | 記録・警告し、後から復旧可能 |

## 5. テスト方針

CLAUDE.md の TDD 原則に従い、各項目でテストを先に書く。

| ファイル | 対象 |
|---|---|
| `tests/lib/core/test_quota.py`（新規） | `is_quota_error` の判定、`QuotaLedger` の予算超過、`QuotaExceededError` |
| `tests/lib/data/test_snapshot.py`（新規） | 保存・復元、TTL 判定、`clear`、全置換の挙動 |
| `tests/lib/data/test_history_manager.py` | `playlist_synced` のマイグレーション冪等性、三値の読み書き |
| `tests/lib/video/test_playlist.py` | **50件超のページネーション**、重複検出と最古優先、quota 例外化、キャッシュ経由の `get_all_playlists_map` |
| `tests/commands/test_playlist_command.py` | `orphans` の正確な判定、`--offline`、`--max-items`、quota 中断と残件報告、`dedupe` の検出と統合 |
| `tests/services/test_upload_manager.py` | `add_video_to_playlist` 失敗時の `playlist_synced=0` 記録、`QuotaExceededError` の伝播 |

既存テストの契約維持（`_playlist_cache` プロパティ、`get_or_create_playlist` の戻り値型）も確認する。
カバレッジは 80% 以上を維持する。Lint は `ruff` を通す。

## 6. 実装順序

依存関係の順に、それぞれ独立して検証できる単位で進める。

1. `src/lib/core/quota.py` — 他が依存する土台
2. `src/lib/data/snapshot.py` — 独立したデータ層
3. `src/lib/data/history.py` の `playlist_synced` 対応
4. `src/lib/core/config.py` の設定追加
5. `src/lib/video/playlist.py` のページネーション・重複検出・例外化（**最優先の修正**）
6. `src/commands/playlist.py` の `orphans` 改修
7. `src/services/upload_manager.py` の成否記録（発生源の遮断）
8. `src/commands/playlist.py` の `dedupe` 新設

5 を単独で適用するだけでも誤判定と重複生成は止まるため、段階的に検証しながら進められる。

## 7. 検証手順

クォータがリセットされた後（太平洋時間の深夜 = 日本時間の 16:00〜17:00 頃）に実施する。

1. `uv run yt-up playlist list` — プレイリスト総数を確認する（544 より多ければ重複が生成されている）
2. `uv run yt-up playlist dedupe` — 重複の実態を把握する（0 units）
3. `uv run yt-up playlist orphans` — 修正後の**真の**オーファン件数を確認する
4. `uv run yt-up playlist orphans --offline` — キャッシュのみで同じ結果が出ることを確認する
5. `uv run yt-up playlist orphans --fix --max-items 10` — 少数で挙動と実消費を確認する
6. 問題なければ `--max-items` を予算いっぱいまで広げて実行する

## 8. スコープ外

- GCP のクォータ上限そのものの引き上げ申請（[QUOTA_INCREASE.md](../../QUOTA_INCREASE.md) を参照）
- `check_quota_limit()` の本格的な作り直し（原因5）。今回は `orphans` / `dedupe` 側に
  `QuotaLedger` による予算制を入れるにとどめ、アップロード経路の逐次的なクォータ再評価は別件とする
- 重複プレイリストの自動命名変更やマージ以外の整理（並び順の統一など）
