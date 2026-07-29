import time
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.lib.core.quota import (
    COSTS,
    QuotaExceededError,
    QuotaLedger,
    count_today_uploads,
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

    def test_non_utf8_content_does_not_raise(self):
        """非 UTF-8 の応答本文でも例外を漏らさない。

        is_quota_error は tenacity の should_retry_exception から
        アップロードのホットパスで呼ばれるため、判定関数が例外を投げると
        リトライ機構ごと壊れる。
        """
        resp = httplib2.Response({"status": 403})
        resp.status = 403
        err = HttpError(resp, b"\xff\xfe invalid utf-8 \x80")

        assert is_quota_error(err) is False

    def test_non_utf8_content_still_detects_quota_exceeded(self):
        """壊れたバイトが混ざっていても、判別キーワードは拾える。"""
        resp = httplib2.Response({"status": 403})
        resp.status = 403
        err = HttpError(resp, b"\xff\xfe quotaExceeded \x80")

        assert is_quota_error(err) is True


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


class TestCountTodayUploads:
    """本日の成功アップロード本数の集計 (Video Uploads per day の消費本数)。"""

    def test_counts_only_today_successful_uploads(self):
        now = time.time()
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": now},
            {"status": "success", "timestamp": now},
            # 一昨日の分は本日の枠を消費しない
            {"status": "success", "timestamp": now - 86400 * 2},
            # 失敗した分もアップロード枠を消費しない
            {"status": "failed", "timestamp": now},
        ]

        assert count_today_uploads(history) == 2

    def test_null_timestamp_is_ignored_without_error(self):
        """timestamp が NULL の行があっても TypeError にならない。"""
        history = MagicMock()
        history.get_all_records.return_value = [
            {"status": "success", "timestamp": None},
            {"status": "success", "timestamp": time.time()},
        ]

        assert count_today_uploads(history) == 1

    def test_empty_history(self):
        history = MagicMock()
        history.get_all_records.return_value = []

        assert count_today_uploads(history) == 0
