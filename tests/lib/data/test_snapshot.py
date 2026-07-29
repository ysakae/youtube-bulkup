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

    def test_save_with_duplicate_ids_does_not_raise(self, cache):
        """重複した playlist_id を含むリストを渡しても UNIQUE 制約違反にならない。

        呼び出し側 (PlaylistManager._ensure_cache) がページ境界の重複を
        除去していても、キャッシュ層が入力データの品質に依存して落ちるのは
        脆いため、こちら側でも冪等にしておく (防御)。
        """
        playlists_with_dup = PLAYLISTS + [PLAYLISTS[0]]
        cache.save_playlists(playlists_with_dup)  # 例外にならないこと
        loaded = cache.load_playlists()
        assert len(loaded) == len(PLAYLISTS)
        ids = [p["id"] for p in loaded]
        assert len(ids) == len(set(ids))


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


class TestAddPlaylistItem:
    """--fix で1件追加した直後にキャッシュへ増分反映する (Critical 1a)。

    これを怠ると TTL (24時間) 内の再実行で同じ動画が再処理され、
    50 units x N を消費して正味の進捗がゼロになる。
    """

    def test_adds_to_existing_playlist(self, cache):
        cache.save_playlist_items("PL1", {"v1"})
        cache.add_playlist_item("PL1", "v2")
        assert cache.load_playlist_map() == {"PL1": {"v1", "v2"}}

    def test_adds_to_unknown_playlist(self, cache):
        """まだキャッシュに無いプレイリストでも行を作る。"""
        cache.add_playlist_item("PL_NEW", "v1")
        assert cache.load_playlist_map() == {"PL_NEW": {"v1"}}

    def test_is_idempotent(self, cache):
        cache.add_playlist_item("PL1", "v1")
        cache.add_playlist_item("PL1", "v1")
        assert cache.load_playlist_map() == {"PL1": {"v1"}}

    def test_empty_playlist_marker_is_removed(self, cache):
        """空として記録されていたプレイリストに1件追加したら、空ではなくなる。

        empty_playlists の行が残ると load_playlist_map() が
        setdefault で上書きしないため実害は無いが、整合性のため確実に消す。
        """
        cache.save_playlist_items("PL1", set())
        assert cache.load_playlist_map() == {"PL1": set()}

        cache.add_playlist_item("PL1", "v1")

        assert cache.load_playlist_map() == {"PL1": {"v1"}}
        rows = cache.conn.execute(
            "SELECT playlist_id FROM empty_playlists WHERE playlist_id = ?", ("PL1",)
        ).fetchall()
        assert rows == [], "empty_playlists の印が残っている"

    def test_survives_reopen(self, temp_db_path):
        c1 = SnapshotCache(db_path=temp_db_path)
        c1.save_playlist_items("PL1", {"v1"})
        c1.add_playlist_item("PL1", "v2")
        c1.close()

        c2 = SnapshotCache(db_path=temp_db_path)
        assert c2.load_playlist_map() == {"PL1": {"v1", "v2"}}
        c2.close()


class TestPrunePlaylistItems:
    """全走査に含まれなかったプレイリストの行を消す (Important 4)。

    消滅したプレイリストの行が残ると、そこにしか入っていない動画が
    オーファンとして検出されなくなる。
    """

    def test_removes_playlists_not_in_keep_set(self, cache):
        cache.save_playlist_items("PL1", {"v1"})
        cache.save_playlist_items("PL2", {"v2"})
        cache.save_playlist_items("PL3", set())

        cache.prune_playlist_items({"PL1"})

        assert cache.load_playlist_map() == {"PL1": {"v1"}}

    def test_keeps_everything_when_all_ids_given(self, cache):
        cache.save_playlist_items("PL1", {"v1"})
        cache.save_playlist_items("PL2", set())

        cache.prune_playlist_items({"PL1", "PL2"})

        assert cache.load_playlist_map() == {"PL1": {"v1"}, "PL2": set()}

    def test_empty_keep_set_removes_all(self, cache):
        cache.save_playlist_items("PL1", {"v1"})
        cache.save_playlist_items("PL2", set())

        cache.prune_playlist_items(set())

        assert cache.load_playlist_map() == {}

    def test_removes_empty_playlist_markers_too(self, cache):
        cache.save_playlist_items("PL1", set())
        cache.save_playlist_items("PL2", set())

        cache.prune_playlist_items({"PL2"})

        assert cache.load_playlist_map() == {"PL2": set()}


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

    def test_save_with_duplicate_ids_does_not_raise(self, cache):
        """重複した video_id を含むリストを渡しても UNIQUE 制約違反にならない。

        実環境 (10,026件) で get_all_uploaded_videos がページ境界の重複を
        含んだまま返し、IntegrityError でクラッシュしたことがある。
        呼び出し側で重複除去していても、キャッシュ層が入力データの品質に
        依存して落ちるのは脆いため、こちら側でも冪等にしておく (防御)。
        """
        videos_with_dup = VIDEOS + [VIDEOS[0]]
        cache.save_videos(videos_with_dup)  # 例外にならないこと
        loaded = cache.load_videos()
        assert len(loaded) == len(VIDEOS)
        ids = [v["id"] for v in loaded]
        assert len(ids) == len(set(ids))


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
