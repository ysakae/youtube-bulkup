import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List

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

from ..lib.core.config import config
from ..lib.data.history import HistoryManager
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.playlist import PlaylistManager
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
    playlist_name: str = None,
    force: bool = False,
    simple_check: bool = False,
    privacy_status: str = None,
) -> bool:
    """
    Process a list of video files: Deduplicate, Metadata, Upload.
    """
    if not video_files:
        console.print("[yellow]No files to process.[/]")
        return False

    # Quota残量チェック（dry-runでない場合のみ）
    COST_PER_UPLOAD = 1600  # 1動画あたりの推定Quotaコスト(ユニット)
    if not dry_run:
        quota_limit = config.upload.daily_quota_limit
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day).timestamp()

        all_records = history.get_all_records(limit=0)
        today_uploads = [
            r for r in all_records
            if r.get("status") == "success" and r.get("timestamp", 0) >= today_start
        ]
        used_units = len(today_uploads) * COST_PER_UPLOAD
        remaining_units = max(0, quota_limit - used_units)
        max_uploadable = remaining_units // COST_PER_UPLOAD

        if remaining_units < COST_PER_UPLOAD:
            console.print(
                f"[bold red]Quota不足: 本日の推定使用量 {used_units:,}/{quota_limit:,} ユニット。"
                f" 残り {remaining_units:,} ユニットでは1件もアップロードできません。[/]"
            )
            console.print("[dim]明日以降に再実行するか、settings.yaml の daily_quota_limit を調整してください。[/]")
            return False
        elif max_uploadable < len(video_files):
            console.print(
                f"[bold yellow]Quota警告: 推定残量 {remaining_units:,}/{quota_limit:,} ユニット。"
                f" 最大 {max_uploadable} 件までアップロード可能（対象: {len(video_files)} 件）。[/]"
            )
        else:
            console.print(
                f"[dim]Quota残量: {remaining_units:,}/{quota_limit:,} ユニット "
                f"(本日 {len(today_uploads)} 件アップロード済み)[/]"
            )

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
        
        # Initialize PlaylistManager
        playlist_manager = PlaylistManager(uploader.credentials) if uploader and not dry_run else None

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
                    if simple_check:
                         progress.update(
                            task_id, description=f"[yellow]Checking dup path {file_path.name}..."
                        )
                         # Check by path FIRST to avoid hash calculation
                         if not force and history.is_uploaded_by_path(str(file_path)):
                            progress.console.print(
                                f"[dim]Skipping duplicate (by path): {file_path.name}[/]"
                            )
                            progress.update(task_id, visible=False)
                            progress.advance(overall_task)
                            return
                    
                    progress.update(
                        task_id, description=f"[yellow]Hashing {file_path.name}..."
                    )
                    file_size = file_path.stat().st_size
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

                    # Override privacy status if specified via CLI
                    if privacy_status:
                        metadata["privacy_status"] = privacy_status

                    if dry_run:
                        target_playlist = playlist_name or file_path.parent.name
                        privacy_display = metadata.get("privacy_status", config.upload.privacy_status)
                        progress.console.print(
                            Panel(
                                f"Title: {metadata['title']}\n"
                                f"Desc: {metadata['description'][:50]}...\n"
                                f"Tags: {metadata['tags']}\n"
                                f"Privacy: {privacy_display}\n"
                                f"Rec Details: {metadata.get('recordingDetails')}\n"
                                f"Thumbnail: {[f.with_suffix(ext).name for ext in ['.jpg', '.jpeg', '.png'] if f.with_suffix(ext).exists()] or 'None'}\n"
                                f"[bold]Playlist:[/] {target_playlist}",
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
                        total=file_size,
                    )

                    def update_prog(p, total):
                        progress.update(task_id, completed=p)

                    video_id = await uploader.upload_video(
                        file_path, metadata, progress_callback=update_prog
                    )


                    if video_id:
                        # Playlist Management
                        target_playlist = playlist_name or file_path.parent.name
                        
                        history.add_record(
                            str(file_path), file_hash, video_id, metadata, playlist_name=target_playlist, file_size=file_size
                        )
                        progress.console.print(
                            f"[bold green]Uploaded {file_path.name} -> {video_id}[/]"
                        )
                        
                        if playlist_manager:
                            try:
                                # Get or create playlist (thread-safe enough for now as cache handles most)
                                # Note: In high concurrency, creating same playlist might be racy. 
                                # But we can rely on API handling or accept minor risk for now.
                                pl_id = await asyncio.to_thread(
                                    playlist_manager.get_or_create_playlist, 
                                    target_playlist, 
                                    config.upload.privacy_status
                                )
                                
                                if pl_id:
                                    await asyncio.to_thread(
                                        playlist_manager.add_video_to_playlist, pl_id, video_id
                                    )
                                    progress.console.print(
                                        f"[dim]Added to playlist: {target_playlist}[/]"
                                    )
                            except Exception as e:
                                logger.error(f"Failed to add to playlist {target_playlist}: {e}")
                                progress.console.print(
                                    f"[red]Warning: Failed to add to playlist: {e}[/]"
                                )
                        
                        # Thumbnail Upload
                        thumbnail_path = None
                        for ext in [".jpg", ".jpeg", ".png"]:
                            possible_thumb = file_path.with_suffix(ext)
                            if possible_thumb.exists():
                                thumbnail_path = possible_thumb
                                break
                        
                        if thumbnail_path:
                            try:
                                progress.console.print(f"[cyan]Found thumbnail: {thumbnail_path.name}[/]")
                                await uploader.upload_thumbnail(video_id, thumbnail_path)
                            except Exception as e:
                                logger.error(f"Failed to upload thumbnail for {video_id}: {e}")
                                progress.console.print(
                                    f"[red]Warning: Failed to upload thumbnail: {e}[/]"
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
                            target_playlist = playlist_name or file_path.parent.name
                            history.add_failure(str(file_path), file_hash, "Quota Exceeded", playlist_name=target_playlist, file_size=file_size)
                    elif e.resp.status == 400 and "uploadLimitExceeded" in str(e):
                        progress.console.print(
                            "[bold red]CRITICAL: Upload Limit Exceeded (Account Limit)![/]"
                        )
                        progress.console.print(
                            "You have reached your daily upload limit for this account."
                        )
                        progress.console.print(
                            "Stopping all further uploads. Please try again in 24 hours."
                        )
                        stop_event.set()
                        if file_hash != "unknown":
                            target_playlist = playlist_name or file_path.parent.name
                            history.add_failure(str(file_path), file_hash, "Account Upload Limit Exceeded", playlist_name=target_playlist, file_size=file_size)
                    else:
                        progress.console.print(
                            f"[bold red]API Error processing {file_path.name}: {e}[/]"
                        )
                    logger.error(f"API Error processing {file_path.name}: {e}")
                    
                    # If not quota error, record failure as usual
                    if not stop_event.is_set() and file_hash != "unknown":
                        target_playlist = playlist_name or file_path.parent.name
                        history.add_failure(str(file_path), file_hash, str(e), playlist_name=target_playlist, file_size=file_size)

                except Exception as e:
                    progress.console.print(
                        f"[bold red]Error processing {file_path.name}: {e}[/]"
                    )
                    logger.exception(f"Error processing {file_path.name}")
                    if file_hash != "unknown":
                        target_playlist = playlist_name or file_path.parent.name
                        # file_size might be unset if error happened before hashing (unlikely given flow but safe to check or init)
                        # Actually file_size is set before hashing now.
                        history.add_failure(str(file_path), file_hash, str(e), playlist_name=target_playlist, file_size=file_size)
                finally:
                    progress.update(task_id, visible=False)
                    progress.advance(overall_task)

        # Prepare tasks
        tasks = []
        for f in video_files:
            tasks.append(process_file(f))

        # Batch processing
        await asyncio.gather(*tasks)
        
        return stop_event.is_set()


async def orchestrate_upload(
    directory: str,
    uploader: VideoUploader,
    history: HistoryManager,
    metadata_gen: FileMetadataGenerator,
    dry_run: bool,
    workers: int,
    playlist: str = None,
    simple_check: bool = False,
    privacy_status: str = None,
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
        video_files, uploader, history, metadata_gen, dry_run, workers, playlist, simple_check=simple_check, privacy_status=privacy_status
    )
