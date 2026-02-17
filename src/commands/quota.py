
from datetime import date, datetime

import typer
from rich.console import Console
from rich.panel import Panel

from ..lib.data.history import HistoryManager

app = typer.Typer(help="Check estimated API quota usage.")
console = Console()

# Estimated costs
COST_VIDEO_UPLOAD = 1600
# Playlist creation and item insertion costs are smaller, usually 50 each.
# We will focus on video uploads as the main consumer.

def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

@app.command("quota")
def quota(
    daily_limit: int = typer.Option(
        10000, "--limit", "-l", help="Daily quota limit (default: 10,000)"
    ),
):
    """
    Show estimated API quota usage for today based on upload history.
    Note: This is an estimation. Actual usage may vary.
    """
    history_manager = HistoryManager()
    
    # Get start of today (local time)
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    
    # Fetch all records
    # We fetch all because TinyDB doesn't query by timestamp range efficiently without index,
    # and the history size is expected to be manageable.
    all_records = history_manager.get_all_records(limit=0)
    
    today_uploads = [
        r for r in all_records 
        if r.get("status") == "success" and r.get("timestamp", 0) >= today_start
    ]
    
    count = len(today_uploads)
    estimated_usage = count * COST_VIDEO_UPLOAD
    
    total_size_bytes = sum(r.get("file_size", 0) for r in today_uploads)
    total_size_str = sizeof_fmt(total_size_bytes)
    
    # Calculate percentage
    percent = (estimated_usage / daily_limit) * 100 if daily_limit > 0 else 0
    
    # Color coding
    color = "green"
    if percent > 50:
        color = "yellow"
    if percent > 80:
        color = "red"
        
    console.print(
        Panel(
            f"[bold]Date:[/] {date.today()}\n"
            f"[bold]Uploads Today:[/] {count}\n"
            f"[bold]Total Size:[/] {total_size_str}\n"
            f"[bold]Estimated Usage:[/] [{color}]{estimated_usage:,}[/] / {daily_limit:,} units\n"
            f"[bold]Remaining:[/] {max(0, daily_limit - estimated_usage):,} units",
            title="API Quota Estimation",
            border_style=color,
            expand=False
        )
    )
    
    console.print("[dim]Note: 1 Video Upload ≈ 1,600 units. Other API calls are negligible but add up.[/]")
