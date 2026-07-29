"""pytest 共通フィクスチャ。

テストが誤って本番データファイル (upload_history.db) や実際のキャッシュ
ファイル (youtube_cache.db) を開いてしまうことを防ぐための、
セッション全体に効く安全装置を提供する。

背景: HistoryManager() / SnapshotCache() を引数なしで生成すると、
config.history_db / config.cache.path (既定でリポジトリ直下の
upload_history.db / youtube_cache.db) を開く。過去に、CLI コマンドの
奥深くでこれらが無条件に生成されるコードをテストした際、パッチを
書き忘れたテストが実際に本番の upload_history.db (ユーザーの
10,027件のアップロード履歴) に接続し、スキーマ変更 (ALTER TABLE) を
引き起こしてしまったことがある。個々のテストにパッチを足すだけでは
「次に足し忘れたら再発する」ため、ここでセッション全体に効く
autouse フィクスチャとして多重防御する。
"""

import pathlib

import pytest

from src.lib.core.config import config
from src.lib.data.history import HistoryManager
from src.lib.data.snapshot import SnapshotCache

# 本番データファイルの絶対パス (リポジトリ直下)。比較は resolve() 後に行う。
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FORBIDDEN_PATHS = {
    str((_REPO_ROOT / "upload_history.db").resolve()),
    str((_REPO_ROOT / "youtube_cache.db").resolve()),
}


def _reject_if_production_path(path) -> None:
    """指定パスが本番データファイルと一致するなら例外で止める。

    下の isolate フィクスチャが正しく機能していれば絶対に到達しないはず
    だが、何らかの理由で config の差し替えがすり抜けた場合の
    最終防衛線 (フェイルファスト) として置く。
    """
    if path is None:
        return
    resolved = str(pathlib.Path(path).resolve())
    if resolved in _FORBIDDEN_PATHS:
        raise RuntimeError(
            f"テストが本番データファイル {resolved} を開こうとしました。"
            "tests/conftest.py の _isolate_production_data フィクスチャ、"
            "またはこのテストのモック設定を確認してください。"
        )


@pytest.fixture(autouse=True)
def _isolate_production_data(tmp_path, monkeypatch):
    """全テストで config の参照先を一時ディレクトリへ強制的に差し替える。

    autouse のため、unittest.TestCase 由来のテストを含めテスト全体に
    自動適用される (pytest は unittest.TestCase に対しても autouse
    フィクスチャは実行する。個別に fixture 引数を受け取れないだけ)。

    これにより、コマンド内で `HistoryManager()` / `SnapshotCache()` を
    引数なしで生成するコードが (パッチし忘れて) 実行されても、本番の
    upload_history.db / youtube_cache.db ではなく使い捨ての一時DBを
    開くようになる。
    """
    monkeypatch.setattr(config, "history_db", str(tmp_path / "test_upload_history.db"))
    monkeypatch.setattr(config.cache, "path", str(tmp_path / "test_youtube_cache.db"))

    original_history_init = HistoryManager.__init__
    original_cache_init = SnapshotCache.__init__

    def _guarded_history_init(self, db_path=None):
        _reject_if_production_path(db_path or config.history_db)
        original_history_init(self, db_path)

    def _guarded_cache_init(self, db_path=None, ttl_hours=24):
        _reject_if_production_path(db_path or config.cache.path)
        original_cache_init(self, db_path, ttl_hours)

    monkeypatch.setattr(HistoryManager, "__init__", _guarded_history_init)
    monkeypatch.setattr(SnapshotCache, "__init__", _guarded_cache_init)

    yield
