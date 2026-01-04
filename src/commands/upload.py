import asyncio
import typer
from rich.console import Console

from ..lib.auth.auth import get_authenticated_service
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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Scan and generate metadata without uploading"
    ),
    workers: int = typer.Option(
        1, help="Number of concurrent uploads (careful with quota!)"
    ),
):
    """
    Upload videos from a directory.
    """
    setup_logging(level="INFO")

    # 1. Setup components
    try:
        service = get_authenticated_service() if not dry_run else None
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

    uploader = VideoUploader(service) if service else None
    history = HistoryManager()
    meta_gen = FileMetadataGenerator()

    # Run async orchestrator
    asyncio.run(
        orchestrate_upload(directory, uploader, history, meta_gen, dry_run, workers)
    )
