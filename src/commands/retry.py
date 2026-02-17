import asyncio
from collections import defaultdict
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

    console.print(f"[bold]Found {len(failed_records)} failed uploads.[/]")

    # Group files by playlist
    tasks_by_playlist = defaultdict(list)
    
    for record in failed_records:
        f_path = Path(record["file_path"])
        if f_path.exists():
            # Priority: CLI override > Persisted History > None (default logic)
            pl_name = playlist if playlist else record.get("playlist_name")
            tasks_by_playlist[pl_name].append(f_path)

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
