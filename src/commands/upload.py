import asyncio
import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.data.history import HistoryManager
from ..lib.core.logger import setup_logging
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.uploader import VideoUploader
from ..services.upload_manager import orchestrate_upload

app = typer.Typer(help="Upload videos.")
console = Console()

@app.command("upload")
def upload(
    directory: str = typer.Argument(..., help="Directory containing videos"),
    playlist: str = typer.Option(
        None, "--playlist", "-p", help="Playlist name (defaults to folder name)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Scan and generate metadata without uploading"
    ),
    workers: int = typer.Option(
        1, help="Number of concurrent uploads (careful with quota!)"
    ),
    simple_check: bool = typer.Option(
        False, "--simple-check", help="Use simple file path check for deduplication (faster but less robust)"
    ),
):
    """
    Upload videos from a directory.
    """
    setup_logging(level="INFO")

    # 1. Setup components
    try:
        credentials = get_credentials() if not dry_run else None
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

    uploader = VideoUploader(credentials) if credentials else None
    history = HistoryManager()
    meta_gen = FileMetadataGenerator()

    # Run async orchestrator
    # Run async orchestrator
    asyncio.run(
        orchestrate_upload(directory, uploader, history, meta_gen, dry_run, workers, playlist, simple_check=simple_check)
    )
