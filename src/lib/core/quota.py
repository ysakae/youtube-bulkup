"""YouTube Data API のクォータ管理。

クォータ枯渇の判定と、ローカルでの消費ユニット見積もりを提供する。
コストの根拠: https://developers.google.com/youtube/v3/determine_quota_cost

クォータの枠は2種類あることに注意 (GCP コンソールの実測で確認):

- Queries per day (既定 10,000 units): playlistItems.insert (50) や
  *.list (1) など、通常の API 呼び出しがここから引かれる。
- Video Uploads per day (既定 100 本): 動画のアップロード
  (videos.insert) はこの「本数ベースの独立した枠」でカウントされ、
  Queries per day は消費しない。
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_up")

# 操作あたりの消費ユニット (Queries per day から引かれる分)
COSTS: Dict[str, int] = {
    "list": 1,
    "insert": 50,
    "update": 50,
    "delete": 50,
    # videos.insert の「公式ドキュメント上の」コスト。
    # ただし実際の GCP では動画のアップロードは Video Uploads per day
    # (本数ベースの別枠) でカウントされ、Queries per day は消費しない。
    # そのため Queries per day の予算計算には使わないこと。
    # (実測: 1日95〜104本のアップロードが成功しているが、1,600 units 換算
    #  なら7本で 10,000 units の割当を超えるはずで、実態と合わない)
    "upload": 1600,
}


def today_start_timestamp() -> float:
    """「本日」の開始 (ローカル時間の午前0時) の UNIX 時刻を返す。

    実際のクォータのリセットは太平洋時間の深夜 (日本時間の16〜17時頃) に
    起きるためこの境界とはずれるが、ローカル時間の方がユーザーの体感に
    近く、各コマンドの集計を揃える意味もあるためこちらを採る。
    ずれによる誤差 (前日夕方以降の分を数え落とす / リセット後も当日午前の
    分を数え続ける) はあくまで見積もりの範囲内で、実際の枯渇は
    403 quotaExceeded / 429 rateLimitExceeded の検知で止める。
    """
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def is_today_success(
    record: Dict[str, Any], today_start: Optional[float] = None
) -> bool:
    """履歴レコードが「本日成功したアップロード」かどうかを判定する。

    today_start: 本日の開始時刻。多数のレコードを走査する場合は
    呼び出し側で一度だけ計算して渡すこと (省略時は毎回計算する)。
    """
    if today_start is None:
        today_start = today_start_timestamp()
    # timestamp が NULL の行があると None >= float で TypeError になる
    return (
        record.get("status") == "success"
        and (record.get("timestamp") or 0) >= today_start
    )


def count_today_uploads(history: Any) -> int:
    """本日すでにアップロードに成功した本数を返す。

    Video Uploads per day (本数ベースの枠) をどれだけ消費したかの見積もり。

    history: get_all_records(limit=0) を持つ履歴マネージャ
             (HistoryManager と同じインターフェース)。
    """
    today_start = today_start_timestamp()
    return sum(
        1 for r in history.get_all_records(limit=0) if is_today_success(r, today_start)
    )


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

    status = exception.resp.status
    # コンテンツがバイト列の場合はデコード。
    # errors="replace" は必須: この関数は tenacity の
    # should_retry_exception からアップロードのホットパスで呼ばれるため、
    # 非 UTF-8 の応答で UnicodeDecodeError を漏らすとリトライ機構ごと壊れる。
    content = exception.content
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    if status == 403 and "quotaExceeded" in content:
        return True
    if status == 429 and "Video Uploads per day" in content:
        return True
    if status == 400 and "uploadLimitExceeded" in content:
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
