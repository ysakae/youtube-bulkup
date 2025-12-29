import asyncio
import logging
from datetime import datetime
from pathlib import Path

import typer
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
from rich.table import Table

from .ai import MetadataGenerator
from .auth import authenticate_new_profile, get_authenticated_service
from .history import HistoryManager
from .logger import setup_logging
from .profiles import get_active_profile, list_profiles, set_active_profile
from .scanner import calculate_hash, scan_directory
from .uploader import VideoUploader

app = typer.Typer(help="YouTube Bulk Uploader CLI", add_completion=False)
auth_app = typer.Typer(help="Manage authentication profiles.")
app.add_typer(auth_app, name="auth")
console = Console()
logger = logging.getLogger("youtube_up")


@auth_app.callback(invoke_without_command=True)
def auth_main(ctx: typer.Context):
    """
    Manage authentication profiles.
    Running 'yt-up auth' without arguments shows the current status.
    """
    if ctx.invoked_subcommand is None:
        show_status()


def show_status():
    """Show current authentication status."""
    setup_logging()
    try:
        active = get_active_profile()
        console.print(f"Active Profile: [bold cyan]{active}[/]")

        service = get_authenticated_service()

        # Verify by getting channel info
        request = service.channels().list(part="snippet", mine=True)
        response = request.execute()
        if "items" in response:
            snippet = response["items"][0]["snippet"]
            channel_title = snippet["title"]
            custom_url = snippet.get("customUrl", "No Handle")
            console.print(
                Panel(
                    f"Connected to channel: [bold cyan]{channel_title}[/] ({custom_url})",
                    title=f"Auth Info ({active})",
                )
            )
        else:
            console.print(
                "[bold yellow]Authentication successful, but NO channel found![/]"
            )
            console.print(
                "Please create a YouTube channel to upload videos: https://www.youtube.com/create_channel"
            )
    except Exception as e:
        console.print(f"[bold red]Authentication failed:[/] {e}")
        raise typer.Exit(code=1)


@auth_app.command("login")
def login(name: str):
    """Create/Login to a new profile."""
    setup_logging()
    try:
        console.print(f"[bold]Logging in as new profile: {name}...[/]")
        authenticate_new_profile(name)
        console.print(f"[bold green]Successfully authenticated profile: {name}[/]")
        show_status()
    except Exception as e:
        console.print(f"[bold red]Login failed:[/] {e}")
        raise typer.Exit(code=1)


@auth_app.command("switch")
def switch(name: str):
    """Switch to an existing profile."""
    setup_logging()
    profiles = list_profiles()
    if name not in profiles:
        console.print(f"[bold red]Profile '{name}' not found.[/]")
        console.print(f"Available: {', '.join(profiles)}")
        raise typer.Exit(code=1)

    set_active_profile(name)
    console.print(f"[bold green]Switched to profile: {name}[/]")
    show_status()


@auth_app.command("list")
def list_cmd():
    """List all profiles."""
    profiles = list_profiles()
    active = get_active_profile()
    console.print("[bold]Available Profiles:[/]")
    for p in profiles:
        mark = "*" if p == active else " "
        console.print(f" {mark} {p}")


@app.command()
def history(
    limit: int = typer.Option(10, help="Number of records to show"),
):
    """
    Show upload history.
    """
    # setup_logging() # Optional, maybe not needed for just reading DB
    history_manager = HistoryManager()
    records = history_manager.get_all_records(limit=limit)

    if not records:
        console.print("[yellow]No upload history found.[/]")
        return

    table = Table(title="Upload History")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Video ID", style="green")
    table.add_column("File", style="dim")

    for r in records:
        ts = r.get("timestamp")
        date_str = (
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "N/A"
        )
        vid = r.get("video_id", "N/A")
        link = f"[link=https://youtu.be/{vid}]{vid}[/link]" if vid != "N/A" else "N/A"
        title = r.get("metadata", {}).get("title", "N/A")
        path = Path(r.get("file_path", "")).name

        table.add_row(date_str, title, link, path)

    console.print(table)


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

                except HttpError as e:
                    if "youtubeSignupRequired" in str(e):
                        progress.console.print(
                            f"[bold red]Error processing {file_path.name}: No YouTube channel found.[/]"
                        )
                        progress.console.print(
                            "Please create a channel associated with this account."
                        )
                    else:
                        progress.console.print(
                            f"[bold red]API Error processing {file_path.name}: {e}[/]"
                        )
                    logger.error(f"API Error processing {file_path.name}: {e}")
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
