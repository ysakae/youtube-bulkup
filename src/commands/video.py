import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.video.manager import VideoManager
from ..lib.video.playlist import PlaylistManager
from ..lib.core.logger import setup_logging

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
            console.print(f"[red]Failed to update privacy status.[/]")
            raise typer.Exit(code=1)
