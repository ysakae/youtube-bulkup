import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..lib.auth.auth import get_authenticated_service
from ..lib.core.logger import setup_logging
from ..lib.data.history import HistoryManager
from ..services.sync_manager import SyncManager

app = typer.Typer(help="Synchronize local history with YouTube.")
console = Console()

def _print_missing_local(missing_local, console: Console):
    table = Table(title="Missing in Local (Exists on YouTube but not in local history)")
    table.add_column("Video ID", style="cyan")
    table.add_column("Title", style="magenta")
    for item in missing_local:
        vid = item['video_id']
        link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
        table.add_row(link, item["remote_title"])
    console.print(table)

def _print_missing_remote(missing_remote, console: Console):
    table = Table(title="Missing in Remote (Exists in local history but not on YouTube)")
    table.add_column("Video ID", style="cyan")
    table.add_column("Local Path", style="dim")
    for item in missing_remote:
        vid = item['video_id']
        link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
        table.add_row(link, item["local_path"])
    console.print(table)

@app.command("sync")
def sync(
    dry_run: bool = typer.Option(
        True, "--dry-run", help="Currently only supports dry-run (report only)."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Remove local-only records (videos deleted from YouTube)."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip confirmation prompt for --fix."
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
        _print_missing_local(missing_local, console)

    if missing_remote:
        _print_missing_remote(missing_remote, console)

    if not missing_local and not missing_remote:
        console.print("[bold green]Local history is perfectly in sync with YouTube![/]")
        return

    # --fix: ローカルにだけあるレコードを削除
    if fix and missing_remote:
        console.print(f"\n[bold yellow]--fix: {len(missing_remote)} local-only records will be deleted.[/]")

        if not yes:
            if not typer.confirm("Continue?"):
                console.print("[yellow]Aborted.[/]")
                raise typer.Abort()

        deleted, failed = manager.fix_missing_remote(missing_remote)
        console.print(
            f"[green]Fix complete:[/] {deleted} deleted, {failed} failed"
        )
    elif fix and not missing_remote:
        console.print("[green]No local-only records to fix.[/]")
