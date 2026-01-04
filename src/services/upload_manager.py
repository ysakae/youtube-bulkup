import asyncio
import logging
from pathlib import Path
from typing import List
from collections import defaultdict

from googleapiclient.errors import HttpError
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

from ..lib.video.metadata import FileMetadataGenerator
from ..lib.data.history import HistoryManager
from ..lib.video.scanner import calculate_hash, scan_directory
from ..lib.video.uploader import VideoUploader

logger = logging.getLogger("youtube_up")
console = Console()

async def process_video_files(
    video_files: List[Path],
    uploader: VideoUploader,
    history: HistoryManager,
    metadata_gen: FileMetadataGenerator,
    dry_run: bool,
    workers: int,
    force: bool = False,
):
    """
    Process a list of video files: Deduplicate, Metadata, Upload.
    """
    if not video_files:
        console.print("[yellow]No files to process.[/]")
        return

    # Setup Progress Dushboard
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

        # Pre-calculate per-folder indices
        # Map: file_path -> (index, total)
        folder_map = {}
        files_by_folder = defaultdict(list)
        
        for f in video_files:
            files_by_folder[f.parent].append(f)
            
        for folder, files in files_by_folder.items():
            # Sort files by name to ensure consistent ordering
            files.sort(key=lambda x: x.name)
            total_in_folder = len(files)
            for i, f in enumerate(files, start=1):
                folder_map[f] = (i, total_in_folder)

        # Semaphore for concurrency
        sem = asyncio.Semaphore(workers)
        stop_event = asyncio.Event()

        async def process_file(file_path: Path):
            if stop_event.is_set():
                progress.advance(overall_task)
                return

            async with sem:
                if stop_event.is_set():
                    progress.advance(overall_task)
                    return

                task_id = progress.add_task(f"Processing {file_path.name}", total=None)
                file_hash = "unknown"

                try:
                    # Deduplication
                    progress.update(
                        task_id, description=f"[yellow]Hashing {file_path.name}..."
                    )
                    file_hash = await asyncio.to_thread(calculate_hash, file_path)

                    if not force and history.is_uploaded(file_hash):
                        progress.console.print(
                            f"[dim]Skipping duplicate: {file_path.name}[/]"
                        )
                        progress.update(task_id, visible=False)
                        progress.advance(overall_task)
                        return

                    # Metadata
                    # Get per-folder index/total
                    idx, tot = folder_map.get(file_path, (0, 0))
                    metadata = metadata_gen.generate(file_path, idx, tot)

                    if dry_run:
                        progress.console.print(
                            Panel(
                                f"Title: {metadata['title']}\n"
                                f"Desc: {metadata['description'][:50]}...\n"
                                f"Tags: {metadata['tags']}\n"
                                f"Rec Details: {metadata.get('recordingDetails')}",
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

                except HttpError as e:
                    if "youtubeSignupRequired" in str(e):
                        progress.console.print(
                            f"[bold red]Error processing {file_path.name}: No YouTube channel found.[/]"
                        )
                    elif e.resp.status == 403 and "quotaExceeded" in str(e):
                        progress.console.print(
                            "[bold red]CRITICAL: YouTube Upload Quota Exceeded![/]"
                        )
                        progress.console.print(
                            "Stopping all further uploads. Please try again tomorrow."
                        )
                        stop_event.set()
                        # Record this failure too so it can be retried later
                        if file_hash != "unknown":
                            history.add_failure(str(file_path), file_hash, "Quota Exceeded")
                    else:
                        progress.console.print(
                            f"[bold red]API Error processing {file_path.name}: {e}[/]"
                        )
                    logger.error(f"API Error processing {file_path.name}: {e}")
                    
                    # If not quota error, record failure as usual
                    if not stop_event.is_set() and file_hash != "unknown":
                        history.add_failure(str(file_path), file_hash, str(e))

                except Exception as e:
                    progress.console.print(
                        f"[bold red]Error processing {file_path.name}: {e}[/]"
                    )
                    logger.exception(f"Error processing {file_path.name}")
                    if file_hash != "unknown":
                        history.add_failure(str(file_path), file_hash, str(e))
                finally:
                    progress.update(task_id, visible=False)
                    progress.advance(overall_task)

        # Prepare tasks
        tasks = []
        for f in video_files:
            tasks.append(process_file(f))

        # Batch processing
        await asyncio.gather(*tasks)


async def orchestrate_upload(
    directory: str,
    uploader: VideoUploader,
    history: HistoryManager,
    metadata_gen: FileMetadataGenerator,
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

    await process_video_files(
        video_files, uploader, history, metadata_gen, dry_run, workers
    )
