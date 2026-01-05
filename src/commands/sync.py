import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..lib.auth.auth import get_authenticated_service
from ..lib.data.history import HistoryManager
from ..lib.core.logger import setup_logging
from ..services.sync_manager import SyncManager

app = typer.Typer(help="Synchronize local history with YouTube.")
console = Console()

@app.command("sync")
def sync(
    dry_run: bool = typer.Option(
        True, "--dry-run", help="Currently only supports dry-run (report only)."
    ),
):
    """
    Compare local history with actual YouTube uploads.
    """
    setup_logging(level="INFO")
    
    # Auth is required for sync
    try:
        service = get_authenticated_service()
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

    history = HistoryManager()
    manager = SyncManager(service, history)

    console.print("[bold cyan]Fetching remote video list (this may take a while)...[/]")
    try:
        in_sync, missing_local, missing_remote = manager.compare()
    except Exception as e:
        console.print(f"[bold red]Error fetching/comparing videos:[/] {e}")
        raise typer.Exit(code=1)

    # Report
    total_remote = len(in_sync) + len(missing_local)
    total_local = len(in_sync) + len(missing_remote)

    console.print(Panel(
        f"Remote Videos: {total_remote}\n"
        f"Local Records: {total_local}\n"
        f"In Sync: {len(in_sync)}",
        title="Sync Summary",
        expand=False
    ))

    # Show Discrepancies
    if missing_local:
        table = Table(title="Missing in Local (Exists on YouTube but not in local history)")
        table.add_column("Video ID", style="cyan")
        table.add_column("Title", style="magenta")
        for item in missing_local:
            vid = item['video_id']
            link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
            table.add_row(link, item["remote_title"])
        console.print(table)

    if missing_remote:
        table = Table(title="Missing in Remote (Exists in local history but not on YouTube)")
        table.add_column("Video ID", style="cyan")
        table.add_column("Local Path", style="dim")
        for item in missing_remote:
            vid = item['video_id']
            link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
            table.add_row(link, item["local_path"])
        console.print(table)

    if not missing_local and not missing_remote:
        console.print("[bold green]Local history is perfectly in sync with YouTube![/]")
