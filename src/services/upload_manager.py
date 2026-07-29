import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from ..lib.core.quota import QuotaExceededError, count_today_uploads
from ..lib.data.history import HistoryManager
from ..lib.video.metadata import FileMetadataGenerator
from ..lib.video.playlist import PlaylistManager
from ..lib.video.scanner import calculate_hash, scan_directory
from ..lib.video.uploader import VideoUploader

logger = logging.getLogger("youtube_up")
console = Console()

def check_quota_limit(
    dry_run: bool,
    video_files: List[Path],
    history: HistoryManager,
) -> bool:
    """本日アップロードできる本数が残っているかを確認する。

    アップロード可否は「Video Uploads per day」(GCP コンソールの実測で
    既定 100 本/日) という本数ベースの枠で決まる。動画のアップロード
    (videos.insert) は Queries per day (既定 10,000 units) を消費しない
    ため、ユニット換算 (1本 1,600 units) で判定してはいけない。

    ここでの見積もりはあくまで事前の目安であり、本数の強制はしない
    (対象より残りが少なければ警告するだけで処理は続行する)。実際に
    上限へ到達した場合は YouTube が 429 rateLimitExceeded
    ('Video Uploads per day') を返し、handle_upload_error が検知して
    パイプライン全体を停止する。

    Returns: 続行してよければ True。1本もアップロードできないと
    分かっている場合のみ False。
    """
    if dry_run:
        return True

    daily_video_uploads = config.quota.daily_video_uploads
    uploaded_today = count_today_uploads(history)
    remaining_uploads = max(0, daily_video_uploads - uploaded_today)

    if remaining_uploads <= 0:
        console.print(
            f"[bold red]アップロード上限に到達: 本日 {uploaded_today} 本 / "
            f"上限 {daily_video_uploads} 本 (Video Uploads per day)。[/]"
        )
        console.print(
            "[dim]クォータのリセット (太平洋時間の深夜 / 日本時間の16〜17時頃) 後に"
            "再実行するか、settings.yaml の quota.daily_video_uploads を"
            "実際の GCP の上限に設定してください。[/]"
        )
        return False

    if remaining_uploads < len(video_files):
        console.print(
            f"[bold yellow]Quota警告: 本日 {uploaded_today}/{daily_video_uploads} 本"
            f" アップロード済み。残り {remaining_uploads} 件までアップロード可能"
            f"（対象: {len(video_files)} 件）。[/]"
        )
    else:
        console.print(
            f"[dim]本日のアップロード可能残数: {remaining_uploads}/"
            f"{daily_video_uploads} 本 (本日 {uploaded_today} 件アップロード済み)[/]"
        )
    return True

async def check_duplicate(
    file_path: Path,
    simple_check: bool,
    force: bool,
    history: HistoryManager,
    task_id,
    progress
) -> Tuple[Optional[str], Optional[int]]:
    """
    Check if a file has already been uploaded.
    Returns (file_hash, file_size) if not a duplicate, otherwise (None, None).
    """
    if simple_check:
        progress.update(task_id, description=f"[yellow]Checking dup path {file_path.name}...")
        if not force and history.is_uploaded_by_path(str(file_path)):
            progress.console.print(f"[dim]Skipping duplicate (by path): {file_path.name}[/]")
            return None, None
            
    progress.update(task_id, description=f"[yellow]Hashing {file_path.name}...")
    file_size = file_path.stat().st_size
    file_hash = await asyncio.to_thread(calculate_hash, file_path)

    if not force and history.is_uploaded(file_hash):
        progress.console.print(f"[dim]Skipping duplicate: {file_path.name}[/]")
        return None, None
        
    return file_hash, file_size

async def post_upload_sync(
    file_path: Path,
    file_hash: str,
    file_size: int,
    video_id: str,
    metadata: dict,
    target_playlist: str,
    playlist_manager: Optional[PlaylistManager],
    uploader: VideoUploader,
    history: HistoryManager,
    progress
):
    """
    Handle post-upload actions (history logging, playlist adding, thumbnail upload).
    """
    history.add_record(
        str(file_path), file_hash, video_id, metadata, playlist_name=target_playlist, file_size=file_size
    )
    progress.console.print(f"[bold green]Uploaded {file_path.name} -> {video_id}[/]")
    
    # プレイリストへの追加
    if playlist_manager:
        try:
            pl_id = await asyncio.to_thread(
                playlist_manager.get_or_create_playlist,
                target_playlist,
                config.upload.privacy_status
            )
            if pl_id:
                ok = await asyncio.to_thread(
                    playlist_manager.add_video_to_playlist, pl_id, video_id
                )
                history.set_playlist_synced(video_id, ok)
                if ok:
                    progress.console.print(f"[dim]Added to playlist: {target_playlist}[/]")
                else:
                    progress.console.print(
                        f"[yellow]Warning: プレイリストへの追加に失敗しました: {target_playlist}"
                        f" (yt-up playlist orphans --fix で後から復旧できます)[/]"
                    )
            else:
                history.set_playlist_synced(video_id, False)
                progress.console.print(
                    f"[yellow]Warning: プレイリストを取得/作成できませんでした: {target_playlist}[/]"
                )
        except QuotaExceededError:
            # 枯渇状態で走り続けても意味がないので上位へ伝播させ、全体を停止する
            history.set_playlist_synced(video_id, False)
            logger.error(f"Quota exceeded while adding to playlist {target_playlist}")
            raise
        except Exception as e:
            history.set_playlist_synced(video_id, False)
            logger.error(f"Failed to add to playlist {target_playlist}: {e}")
            progress.console.print(f"[red]Warning: Failed to add to playlist: {e}[/]")
            
    # サムネイルのアップロード
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
            progress.console.print(f"[red]Warning: Failed to upload thumbnail: {e}[/]")

def handle_upload_error(
    e: Exception,
    file_path: Path,
    file_hash: str,
    file_size: Optional[int],
    target_playlist: str,
    stop_event: asyncio.Event,
    progress,
    history: HistoryManager,
):
    """
    Handle upload exceptions, log failures, and potentially trigger a stop event.
    """
    if isinstance(e, QuotaExceededError):
        progress.console.print("[bold red]重大: YouTube API のクォータを使い切りました![/]")
        progress.console.print(
            "これ以上のアップロードを停止します。"
            "太平洋時間の深夜（日本時間の16〜17時頃）にリセットされます。"
        )
        stop_event.set()
        return

    if isinstance(e, HttpError):
        if "youtubeSignupRequired" in str(e):
            progress.console.print(f"[bold red]Error processing {file_path.name}: No YouTube channel found.[/]")
        elif e.resp.status == 403 and "quotaExceeded" in str(e):
            progress.console.print("[bold red]CRITICAL: YouTube Upload Quota Exceeded![/]")
            progress.console.print("Stopping all further uploads. Please try again tomorrow.")
            stop_event.set()
            if file_hash != "unknown":
                history.add_failure(str(file_path), file_hash, "Quota Exceeded", playlist_name=target_playlist, file_size=file_size)
        elif e.resp.status == 429 and "Video Uploads per day" in str(e):
            # 429 rateLimitExceeded + 'Video Uploads per day' = 1日のアップロード上限到達
            progress.console.print("[bold red]CRITICAL: Daily Video Upload Quota Exceeded (429)![/]")
            progress.console.print("Stopping all further uploads. Quota resets at midnight Pacific Time.")
            stop_event.set()
            if file_hash != "unknown":
                history.add_failure(str(file_path), file_hash, "Daily Upload Quota Exceeded", playlist_name=target_playlist, file_size=file_size)
        elif e.resp.status == 400 and "uploadLimitExceeded" in str(e):
            progress.console.print("[bold red]CRITICAL: Upload Limit Exceeded (Account Limit)![/]")
            progress.console.print("You have reached your daily upload limit for this account.")
            progress.console.print("Stopping all further uploads. Please try again in 24 hours.")
            stop_event.set()
            if file_hash != "unknown":
                history.add_failure(str(file_path), file_hash, "Account Upload Limit Exceeded", playlist_name=target_playlist, file_size=file_size)
        else:
            progress.console.print(f"[bold red]API Error processing {file_path.name}: {e}[/]")
        logger.error(f"API Error processing {file_path.name}: {e}")

        # クォータエラー等以外での通常の失敗記録
        if not stop_event.is_set() and file_hash != "unknown":
            history.add_failure(str(file_path), file_hash, str(e), playlist_name=target_playlist, file_size=file_size)
    else:
        progress.console.print(f"[bold red]Error processing {file_path.name}: {e}[/]")
        logger.exception(f"Error processing {file_path.name}")
        if file_hash != "unknown":
            history.add_failure(str(file_path), file_hash, str(e), playlist_name=target_playlist, file_size=file_size)

def prepare_folder_map(video_files: List[Path]) -> Dict[Path, Tuple[int, int]]:
    """Create a map of file_path to (index, total_in_folder) for metadata generation."""
    folder_map = {}
    files_by_folder = defaultdict(list)
    for f in video_files:
        files_by_folder[f.parent].append(f)
    for folder, files in files_by_folder.items():
        files.sort(key=lambda x: x.name)
        total = len(files)
        for i, f in enumerate(files, start=1):
            folder_map[f] = (i, total)
    return folder_map

def preview_metadata(file_path: Path, metadata: Dict[str, Any], target_playlist: str, progress):
    """Dry-run metadata preview."""
    privacy_display = metadata.get("privacy_status", config.upload.privacy_status)
    thumb_files = [file_path.with_suffix(ext).name for ext in ['.jpg', '.jpeg', '.png'] if file_path.with_suffix(ext).exists()]
    progress.console.print(
        Panel(
            f"Title: {metadata['title']}\n"
            f"Desc: {metadata['description'][:50]}...\n"
            f"Tags: {metadata['tags']}\n"
            f"Privacy: {privacy_display}\n"
            f"Rec Details: {metadata.get('recordingDetails')}\n"
            f"Thumbnail: {thumb_files or 'None'}\n"
            f"[bold]Playlist:[/] {target_playlist}",
            title=f"[Dry Run] Metadata for {file_path.name}",
        )
    )

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

    if not check_quota_limit(dry_run, video_files, history):
        return False

    folder_map = prepare_folder_map(video_files)
    playlist_manager = PlaylistManager(uploader.credentials) if uploader and not dry_run else None

    # Setup Progress Dashboard
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall_task = progress.add_task("[bold green]Overall Progress", total=len(video_files))
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
                file_size = None
                target_playlist = playlist_name or file_path.parent.name

                try:
                    # Deduplication
                    file_hash, file_size = await check_duplicate(
                        file_path, simple_check, force, history, task_id, progress
                    )
                    if file_hash is None:
                        # It is a duplicate
                        progress.update(task_id, visible=False)
                        progress.advance(overall_task)
                        return

                    # Metadata
                    idx, tot = folder_map.get(file_path, (0, 0))
                    metadata = metadata_gen.generate(file_path, idx, tot)
                    if privacy_status:
                        metadata["privacy_status"] = privacy_status

                    if dry_run:
                        preview_metadata(file_path, metadata, target_playlist, progress)
                        progress.update(task_id, visible=False)
                        progress.advance(overall_task)
                        return

                    # Upload
                    progress.update(task_id, description=f"[red]Uploading {file_path.name}...", total=file_size)
                    
                    def update_prog(p, total):
                        progress.update(task_id, completed=p)

                    video_id = await uploader.upload_video(file_path, metadata, progress_callback=update_prog)

                    if video_id:
                        await post_upload_sync(
                            file_path, file_hash, file_size, video_id, metadata, 
                            target_playlist, playlist_manager, uploader, history, progress
                        )

                except Exception as e:
                    handle_upload_error(
                        e, file_path, file_hash, file_size, target_playlist, 
                        stop_event, progress, history
                    )
                finally:
                    progress.update(task_id, visible=False)
                    progress.advance(overall_task)

        # Execute
        tasks = [process_file(f) for f in video_files]
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
    console.print(f"[bold]Scanning {directory}...[/]")
    video_files = list(scan_directory(directory))
    console.print(f"Found [cyan]{len(video_files)}[/] video files.")

    if not video_files:
        return

    await process_video_files(
        video_files, uploader, history, metadata_gen, dry_run, workers, playlist, simple_check=simple_check, privacy_status=privacy_status
    )
