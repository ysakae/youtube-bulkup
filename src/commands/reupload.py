import asyncio
from pathlib import Path
from typing import List

import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.core.logger import setup_logging
from ..lib.data.history import HistoryManager
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.scanner import calculate_hash
from ..lib.video.uploader import VideoUploader
from ..services.upload_manager import process_video_files

app = typer.Typer(help="Re-upload videos.")
console = Console()

def _resolve_files_to_reupload(files: List[Path], hashes: List[str], video_ids: List[str], history: HistoryManager, console: Console) -> set:
    valid_files = set()

    # Resolve files from paths
    if files:
        for f in files:
            if f.exists():
                valid_files.add(f.resolve())
            else:
                console.print(f"[red]File not found: {f}[/]")

    # Resolve files from hashes
    if hashes:
        for h in hashes:
            record = history.get_record(h)
            if record:
                f_path = Path(record["file_path"])
                if f_path.exists():
                    valid_files.add(f_path.resolve())
                else:
                    console.print(f"[yellow]File for hash {h} not found at {f_path}[/]")
            else:
                console.print(f"[red]No history found for hash: {h}[/]")

    # Resolve files from video IDs
    if video_ids:
        for vid in video_ids:
            record = history.get_record_by_video_id(vid)
            if record:
                f_path = Path(record["file_path"])
                if f_path.exists():
                    valid_files.add(f_path.resolve())
                else:
                    console.print(f"[yellow]File for video ID {vid} not found at {f_path}[/]")
            else:
                console.print(f"[red]No history found for video ID: {vid}[/]")
                
    return valid_files

@app.command("reupload")
def reupload(
    files: List[Path] = typer.Argument(None, help="Files to re-upload (must exist locally)"),
    hashes: List[str] = typer.Option(None, "--hash", help="File hashes to re-upload"),
    video_ids: List[str] = typer.Option(None, "--video-id", help="Video IDs to re-upload"),
    workers: int = typer.Option(
        1, help="Number of concurrent uploads (careful with quota!)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate re-upload without deleting history or uploading"
    ),
    playlist: str = typer.Option(
        None, "--playlist", "-p", help="Playlist name (defaults to folder name)"
    ),
):
    """
    Force re-upload of specific files by clearing their history.
    """
    setup_logging(level="INFO")

    if not files and not hashes and not video_ids:
        console.print("[yellow]No files, hashes, or video IDs provided.[/]")
        return

    history = HistoryManager()
    valid_files = _resolve_files_to_reupload(files, hashes, video_ids, history, console)

    if not valid_files:
        console.print("[red]No valid files to process.[/]")
        raise typer.Exit(code=1)

    # Auth
    try:
        credentials = get_credentials() if not dry_run else None
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

    uploader = VideoUploader(credentials) if credentials else None
    meta_gen = FileMetadataGenerator()

    # Clear history for these files (unless dry run)
    files_to_process = list(valid_files)
    console.print(f"[bold]Preparing to re-upload {len(files_to_process)} files...[/]")
    
    for f in files_to_process:
        file_hash = calculate_hash(f)
        if dry_run:
             console.print(f"[dim][Dry Run] Would clear history for: {f.name} (Hash: {file_hash})[/]")
        else:
            if history.delete_record(file_hash):
                console.print(f"[green]Cleared history for: {f.name}[/]")
            else:
                console.print(f"[dim]No history found for: {f.name} (will proceed to upload)[/]")

    # Process
    # If dry_run is True, we force processing because history wasn't deleted (so is_uploaded would be true)
    asyncio.run(
        process_video_files(
            files_to_process, uploader, history, meta_gen, dry_run=dry_run, workers=workers, force=dry_run, playlist_name=playlist
        )
    )
