import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.core.logger import setup_logging
from ..lib.data.history import HistoryManager
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.uploader import VideoUploader
from ..services.upload_manager import process_video_files

app = typer.Typer(help="Retry failed uploads.")
console = Console()

def _filter_failed_records(failed_records, since: str, error: str, limit: int, console: Console):
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
            since_ts = since_dt.timestamp()
            failed_records = [
                r for r in failed_records
                if r.get("timestamp", 0) >= since_ts
            ]
        except ValueError:
            console.print("[red]--since の形式は YYYY-MM-DD にしてください。[/]")
            raise typer.Exit(code=1)

    if error:
        failed_records = [
            r for r in failed_records
            if error.lower() in r.get("error", "").lower()
        ]

    if limit > 0:
        failed_records = failed_records[:limit]
        
    return failed_records

def _group_tasks_by_playlist(failed_records, playlist_override: str):
    tasks_by_playlist = defaultdict(list)
    for record in failed_records:
        f_path = Path(record["file_path"])
        if f_path.exists():
            pl_name = playlist_override if playlist_override else record.get("playlist_name")
            tasks_by_playlist[pl_name].append(f_path)
    return tasks_by_playlist

@app.command("retry")
def retry(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Scan and generate metadata without uploading"
    ),
    workers: int = typer.Option(
        1, help="Number of concurrent uploads (careful with quota!)"
    ),
    playlist: str = typer.Option(
        None, "--playlist", "-p", help="Playlist name (override persisted history or default)"
    ),
    limit: int = typer.Option(
        0, "--limit", "-l", help="Maximum number of files to retry (0 for all)"
    ),
    since: str = typer.Option(
        None, "--since", help="Only retry failures after this date (YYYY-MM-DD)"
    ),
    error: str = typer.Option(
        None, "--error", "-e", help="Only retry failures containing this text in error message"
    ),
):
    """
    Retry uploading failed files.
    """
    setup_logging(level="INFO")

    history = HistoryManager()
    failed_records = history.get_failed_records()

    if not failed_records:
        console.print("[green]No failed uploads found.[/]")
        return

    failed_records = _filter_failed_records(failed_records, since, error, limit, console)

    if not failed_records:
        console.print("[yellow]No failed uploads found matching filters.[/]")
        return

    console.print(f"[bold]Found {len(failed_records)} failed uploads to retry.[/]")

    # Group files by playlist
    tasks_by_playlist = _group_tasks_by_playlist(failed_records, playlist)

    if not tasks_by_playlist:
        console.print("[yellow]No valid files to retry.[/]")
        return

    # Auth
    if not dry_run:
        try:
            credentials = get_credentials()
        except Exception as e:
            console.print(f"[bold red]Auth Error:[/] {e}")
            raise typer.Exit(code=1)
    else:
        credentials = None

    uploader = VideoUploader(credentials) if credentials else None
    meta_gen = FileMetadataGenerator()

    # Process each playlist group
    for pl_name, files in tasks_by_playlist.items():
        if pl_name:
             console.print(f"\n[bold]Retrying {len(files)} files for playlist: '{pl_name}'[/]")
        else:
             console.print(f"\n[bold]Retrying {len(files)} files (default playlist)...[/]")

        is_stopped = asyncio.run(
            process_video_files(
                files, uploader, history, meta_gen, dry_run=dry_run, workers=workers, playlist_name=pl_name
            )
        )
        
        if is_stopped:
            console.print("[bold red]Process halted due to critical error. Stopping remaining playlists.[/]")
            break
