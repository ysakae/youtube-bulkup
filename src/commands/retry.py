import asyncio
import typer
from pathlib import Path
from rich.console import Console

from ..lib.auth.auth import get_authenticated_service
from ..lib.data.history import HistoryManager
from ..lib.core.logger import setup_logging
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.uploader import VideoUploader
from ..services.upload_manager import process_video_files

app = typer.Typer(help="Retry failed uploads.")
console = Console()

@app.command("retry")
def retry(
    workers: int = typer.Option(
        1, help="Number of concurrent uploads (careful with quota!)"
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

    # Verify if files exist
    files_to_retry = []
    for record in failed_records:
        file_path = Path(record["file_path"])
        if file_path.exists():
            files_to_retry.append(file_path)
        else:
            console.print(f"[yellow]File missing: {file_path}[/]")

    if not files_to_retry:
        console.print("[yellow]No valid files to retry.[/]")
        return

    # Auth
    try:
        service = get_authenticated_service()
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

    uploader = VideoUploader(service)
    meta_gen = FileMetadataGenerator()

    asyncio.run(
        process_video_files(
            files_to_retry, uploader, history, meta_gen, dry_run=False, workers=workers
        )
    )
