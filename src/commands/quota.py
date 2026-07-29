
from datetime import date
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..lib.core.config import config
from ..lib.core.quota import COSTS, is_today_success, today_start_timestamp
from ..lib.data.history import HistoryManager

app = typer.Typer(help="Check estimated API quota usage.")
console = Console()


def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

@app.command("quota")
def quota(
    daily_limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Queries per day の上限 (既定: settings.yaml の quota.daily_limit)",
    ),
):
    """本日のクォータ使用状況を履歴から推定して表示する。

    クォータの枠は2種類ある (GCP コンソールの実測):
      - Video Uploads per day (既定 100 本/日): 動画のアップロードはこの
        本数ベースの枠でカウントされ、Queries per day は消費しない。
      - Queries per day (既定 10,000 units): アップロード時のプレイリスト
        追加 (playlistItems.insert = 50 units) などがここから引かれる。

    あくまで履歴に基づく推定であり、実際の使用量とは異なりうる。
    """
    history_manager = HistoryManager()

    # 本日のアップロード本数 (Video Uploads per day の消費分)。
    # サイズ集計にも使うため、履歴の走査は1回で済ませる。
    today_start = today_start_timestamp()
    today_uploads = [
        r
        for r in history_manager.get_all_records(limit=0)
        if is_today_success(r, today_start)
    ]
    count = len(today_uploads)
    upload_limit = config.quota.daily_video_uploads

    # 本日の Queries per day 消費の推定。アップロード自体は消費しないが、
    # アップロードのたびにプレイリストへ追加している分を計上する。
    queries_limit = (
        daily_limit if daily_limit is not None else config.effective_daily_quota()
    )
    estimated_units = count * COSTS["insert"]

    total_size_bytes = sum(r.get("file_size", 0) or 0 for r in today_uploads)
    total_size_str = sizeof_fmt(total_size_bytes)

    # 表示色は「先に上限へ到達する方」の逼迫度で決める
    upload_percent = (count / upload_limit) * 100 if upload_limit > 0 else 0
    units_percent = (estimated_units / queries_limit) * 100 if queries_limit > 0 else 0
    percent = max(upload_percent, units_percent)

    color = "green"
    if percent > 50:
        color = "yellow"
    if percent > 80:
        color = "red"

    console.print(
        Panel(
            f"[bold]Date:[/] {date.today()}\n"
            f"[bold]Uploads Today:[/] [{color}]{count}[/] / {upload_limit:,} 本 "
            f"(Video Uploads per day)\n"
            f"[bold]Remaining Uploads:[/] {max(0, upload_limit - count):,} 本\n"
            f"[bold]Total Size:[/] {total_size_str}\n"
            f"[bold]Estimated Queries Usage:[/] {estimated_units:,} / "
            f"{queries_limit:,} units (Queries per day)\n"
            f"[bold]Remaining Units:[/] {max(0, queries_limit - estimated_units):,} units",
            title="API Quota Estimation",
            border_style=color,
            expand=False
        )
    )

    console.print(
        "[dim]Note: 動画のアップロードは Video Uploads per day (本数) の枠で"
        "カウントされ、Queries per day (ユニット) は消費しません。"
        "ユニットの推定はアップロード時のプレイリスト追加 "
        f"({COSTS['insert']} units/本) 分です。[/]"
    )
