import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.core.logger import setup_logging
from ..lib.video.manager import VideoManager
from ..lib.video.playlist import PlaylistManager

app = typer.Typer(help="Manage videos.")
console = Console()

def _get_manager():
    try:
        credentials = get_credentials()
        return VideoManager(credentials)
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

def _get_playlist_manager():
    try:
        credentials = get_credentials()
        return PlaylistManager(credentials)
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

@app.command("update-privacy")
def update_privacy(
    target: str = typer.Argument(..., help="YouTube Video ID or 'all' if using --playlist"),
    status: str = typer.Argument(..., help="Privacy status (private, public, unlisted)"),
    playlist: str = typer.Option(None, "--playlist", help="Target playlist for bulk update"),
):
    """
    Update the privacy status of a video or a playlist.
    
    Single Video:
      yt-up video update-privacy <VIDEO_ID> <STATUS>
      
    Playlist (Bulk):
      yt-up video update-privacy all <STATUS> --playlist <PLAYLIST_NAME>
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if playlist:
        if target != "all":
            console.print("[yellow]Warning: 'target' argument is ignored when --playlist is used, but normally set to 'all' for clarity.[/]")
        
        console.print(f"[bold]Fetching videos from playlist: {playlist}...[/]")
        pl_manager = _get_playlist_manager()
        video_ids = pl_manager.get_video_ids_from_playlist(playlist)
        
        if not video_ids:
            console.print(f"[red]No videos found in playlist {playlist} (or failed to retrieve).[/]")
            raise typer.Exit(code=1)
            
        success_count = 0
        fail_count = 0
        
        with console.status(f"[bold green]Updating privacy to {status} for {len(video_ids)} videos..."):
            for vid in video_ids:
                if manager.update_privacy_status(vid, status):
                    console.print(f"[green]✔ Updated {vid}[/]")
                    success_count += 1
                else:
                    console.print(f"[red]✖ Failed {vid}[/]")
                    fail_count += 1
        
        console.print(f"\n[bold]Bulk Update Complete:[/] {success_count} success, {fail_count} failed.")
        if fail_count > 0:
            raise typer.Exit(code=1)
            
    else:
        # Single video mode
        if manager.update_privacy_status(target, status):
            console.print(f"[green]Successfully updated {target} to {status}[/]")
        else:
            console.print("[red]Failed to update privacy status.[/]")
            raise typer.Exit(code=1)

@app.command("update-meta")
def update_meta(
    target: str = typer.Argument(..., help="YouTube Video ID or 'all' if using --playlist"),
    title: str = typer.Option(None, "--title", help="New title"),
    description: str = typer.Option(None, "--desc", help="New description"),
    tags: str = typer.Option(None, "--tags", help="Comma separated tags"),
    category: str = typer.Option(None, "--category", help="New category ID"),
    playlist: str = typer.Option(None, "--playlist", help="Target playlist for bulk update"),
):
    """
    Update metadata (title, description, tags, category) for a video or a playlist.
    
    Example:
      yt-up video update-meta <VIDEO_ID> --title "New Title" --tags "tag1,tag2"
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    # helper to parse tags
    tag_list = tags.split(",") if tags else None
    
    if playlist:
        if target != "all":
            console.print("[yellow]Warning: 'target' argument is ignored when --playlist is used, but normally set to 'all' for clarity.[/]")
        
        console.print(f"[bold]Fetching videos from playlist: {playlist}...[/]")
        pl_manager = _get_playlist_manager()
        video_ids = pl_manager.get_video_ids_from_playlist(playlist)
        
        if not video_ids:
            console.print(f"[red]No videos found in playlist {playlist} (or failed to retrieve).[/]")
            raise typer.Exit(code=1)
            
        success_count = 0
        fail_count = 0
        
        with console.status(f"[bold green]Updating metadata for {len(video_ids)} videos..."):
            for vid in video_ids:
                if manager.update_metadata(vid, title=title, description=description, tags=tag_list, category_id=category):
                    console.print(f"[green]✔ Updated {vid}[/]")
                    success_count += 1
                else:
                    console.print(f"[red]✖ Failed {vid}[/]")
                    fail_count += 1
        
        console.print(f"\n[bold]Bulk Update Complete:[/] {success_count} success, {fail_count} failed.")
        if fail_count > 0:
            raise typer.Exit(code=1)
    
    else:
        # Single video mode
        if manager.update_metadata(target, title=title, description=description, tags=tag_list, category_id=category):
             console.print(f"[green]Successfully updated metadata for {target}[/]")
        else:
             console.print("[red]Failed to update metadata.[/]")
             raise typer.Exit(code=1)

@app.command("update-thumbnail")
def update_thumbnail(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    image_path: str = typer.Argument(..., help="Path to the thumbnail image file"),
):
    """
    Update the thumbnail of a video.
    
    Example:
      yt-up video update-thumbnail <VIDEO_ID> ./new_thumb.jpg
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if manager.update_thumbnail(video_id, image_path):
        console.print(f"[green]Successfully updated thumbnail for {video_id}[/]")
    else:
        console.print("[red]Failed to update thumbnail.[/]")
        raise typer.Exit(code=1)

@app.command("delete-video")
def delete_video(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """
    Delete a video from YouTube.
    
    WARNING: This action is irreversible.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if not force:
        if not typer.confirm(f"Are you sure you want to delete video {video_id}?"):
            console.print("[yellow]Aborted.[/]")
            raise typer.Abort()

    if manager.delete_video(video_id):
        console.print(f"[green]Successfully deleted video {video_id}[/]")
    else:
        console.print("[red]Failed to delete video.[/]")
        raise typer.Exit(code=1)
