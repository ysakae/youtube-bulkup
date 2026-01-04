import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from datetime import datetime

from ..lib.data.history import HistoryManager

app = typer.Typer(help="Manage upload history.")
console = Console()

@app.command("history")
def history(
    limit: int = typer.Option(0, help="Number of records to show (0 for all)"),
    status: str = typer.Option(
        None, help="Filter by status (success/failed)"
    ),
):
    """
    Show upload history.
    """
    # setup_logging() # Optional, maybe not needed for just reading DB
    history_manager = HistoryManager()
    # Always fetch all to filter manually
    all_records = history_manager.get_all_records(limit=0)
    
    # Calculate stats
    total = len(all_records)
    failed = len([r for r in all_records if r.get("status") == "failed"])
    success = len([r for r in all_records if r.get("status", "success") == "success"])
    
    console.print(
        Panel(
            f"[bold]Total: {total}[/] | [green]Success: {success}[/] | [red]Failed: {failed}[/]",
            title="Summary",
            expand=False
        )
    )

    records = all_records
    if status:
        records = [r for r in records if r.get("status", "success") == status]

    if limit > 0:
        records = records[:limit]

    if not records:
        console.print("[yellow]No upload history found (matching filter).[/]")
        return

    table = Table(title="Upload History")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Title", style="magenta")
    table.add_column("Video ID / Error", style="green")
    table.add_column("File", style="dim")

    for r in records:
        ts = r.get("timestamp")
        date_str = (
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "N/A"
        )
        status = r.get("status", "success")
        path = Path(r.get("file_path", "")).name
        
        if status == "failed":
            status_str = "[red]Failed[/]"
            title = path
            vid = r.get("error", "Unknown Error")
            # Truncate long error messages
            if len(vid) > 40:
                vid = vid[:37] + "..."
            vid_col = f"[red]{vid}[/]"
        else:
            status_str = "[green]Success[/]"
            vid = r.get("video_id", "N/A")
            vid_col = f"[link=https://youtu.be/{vid}]{vid}[/link]" if vid != "N/A" else "N/A"
            title = r.get("metadata", {}).get("title", "N/A")

        table.add_row(date_str, status_str, title, vid_col, path)

    console.print(table)
