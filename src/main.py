import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .ai import MetadataGenerator
from .auth import get_authenticated_service
from .history import HistoryManager
from .logger import setup_logging
from .scanner import calculate_hash, scan_directory
from .uploader import VideoUploader

app = typer.Typer(help="YouTube Bulk Uploader CLI", add_completion=False)
console = Console()
logger = logging.getLogger("youtube_up")


@app.command()
def auth():
    """
    Authenticate with YouTube API and save credentials.
    """
    setup_logging()
    try:
        service = get_authenticated_service()
        console.print("[bold green]Authentication successful![/]")
        # Verify by getting channel info
        request = service.channels().list(part="snippet", mine=True)
        response = request.execute()
        if "items" in response:
            channel_title = response["items"][0]["snippet"]["title"]
            console.print(
                Panel(
                    f"Connected to channel: [bold cyan]{channel_title}[/]",
                    title="Auth Info",
                )
            )
    except Exception as e:
        console.print(f"[bold red]Authentication failed:[/] {e}")
        raise typer.Exit(code=1)


@app.command()
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
    ai_gen = MetadataGenerator()

    # Run async orchestrator
    asyncio.run(
        orchestrate_upload(directory, uploader, history, ai_gen, dry_run, workers)
    )


async def orchestrate_upload(
    directory: str,
    uploader: VideoUploader,
    history: HistoryManager,
    ai: MetadataGenerator,
    dry_run: bool,
    workers: int,
):
    """
    Core async logic for processing video files.
    """
    # 2. Scan Files
    console.print(f"[bold]Scanning {directory}...[/]")
    video_files = list(scan_directory(directory))
    console.print(f"Found [cyan]{len(video_files)}[/] video files.")

    if not video_files:
        return

    # 3. Setup Progress Dashboard
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task(
            "[bold green]Overall Progress", total=len(video_files)
        )

        # Semaphore for concurrency
        sem = asyncio.Semaphore(workers)

        async def process_file(file_path: Path):
            async with sem:
                task_id = progress.add_task(f"Processing {file_path.name}", total=None)

                try:
                    # Deduplication
                    progress.update(
                        task_id, description=f"[yellow]Hashing {file_path.name}..."
                    )
                    file_hash = await asyncio.to_thread(calculate_hash, file_path)

                    if history.is_uploaded(file_hash):
                        progress.console.print(
                            f"[dim]Skipping duplicate: {file_path.name}[/]"
                        )
                        progress.update(task_id, visible=False)
                        progress.advance(overall_task)
                        return

                    # AI Metadata
                    progress.update(
                        task_id,
                        description=f"[blue]Generating Metadata {file_path.name}...",
                    )
                    metadata = await ai.generate_metadata(file_path)

                    if dry_run:
                        progress.console.print(
                            Panel(
                                f"Title: {metadata['title']}\n"
                                f"Desc: {metadata['description'][:50]}...\n"
                                f"Tags: {metadata['tags']}",
                                title=f"[Dry Run] Metadata for {file_path.name}",
                            )
                        )
                        progress.update(task_id, visible=False)
                        progress.advance(overall_task)
                        return

                    # Upload
                    progress.update(
                        task_id,
                        description=f"[red]Uploading {file_path.name}...",
                        total=file_path.stat().st_size,
                    )

                    def update_prog(p, total):
                        progress.update(task_id, completed=p)

                    video_id = await uploader.upload_video(
                        file_path, metadata, progress_callback=update_prog
                    )

                    if video_id:
                        history.add_record(
                            str(file_path), file_hash, video_id, metadata
                        )
                        progress.console.print(
                            f"[bold green]Uploaded {file_path.name} -> {video_id}[/]"
                        )

                except Exception as e:
                    progress.console.print(
                        f"[bold red]Error processing {file_path.name}: {e}[/]"
                    )
                    logger.exception(f"Error processing {file_path.name}")
                finally:
                    progress.update(task_id, visible=False)
                    progress.advance(overall_task)

        # Batch processing
        await asyncio.gather(*(process_file(f) for f in video_files))


if __name__ == "__main__":
    app()
