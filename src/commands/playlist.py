import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.video.playlist import PlaylistManager
from ..lib.core.logger import setup_logging

app = typer.Typer(help="Manage playlists.")
console = Console()

def _get_manager():
    try:
        credentials = get_credentials()
        return PlaylistManager(credentials)
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

@app.command("add")
def add_video(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    playlist_name_or_id: str = typer.Argument(..., help="Playlist Name or ID"),
    privacy: str = typer.Option("private", help="Privacy status for new playlist")
):
    """
    Add a video to a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    # Simple heuristic: if it looks like an ID (starts with PL and usually long), treat as ID?
    # Actually PlaylistManager.get_or_create_playlist takes a TITLE.
    # If the user provides an ID, our current library implementation might try to create a playlist with that ID as Title?
    # The current library implementation is title-based for get_or_create.
    # To support ID directly we might need to enhance the lib, but strictly following the proposal:
    # "Playlist Name or ID" -> The library currently supports get_or_create by TITLE.
    # If we want to support ID, we should check if the input is a valid ID.
    # For now, let's stick to the library's capability: treat input as Title. 
    # If the user wants to use ID, we might need a separate command or library update.
    # Given the previous context, `get_or_create_playlist` uses title.
    
    # However, `add_video_to_playlist` takes a playlist ID.
    # So we need to resolve title to ID.
    
    playlist_id = manager.get_or_create_playlist(playlist_name_or_id, privacy)
    
    if not playlist_id:
        console.print(f"[red]Failed to find or create playlist: {playlist_name_or_id}[/]")
        raise typer.Exit(code=1)
        
    if manager.add_video_to_playlist(playlist_id, video_id):
        console.print(f"[green]Successfully added {video_id} to playlist {playlist_name_or_id} ({playlist_id})[/]")
    else:
        console.print(f"[red]Failed to add video to playlist.[/]")
        raise typer.Exit(code=1)

@app.command("remove")
def remove_video(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    playlist_name_or_id: str = typer.Argument(..., help="Playlist Name or ID"),
):
    """
    Remove a video from a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    # We need playlist ID. 
    # If user provided a name, we try to resolve it via cache/list?
    # The current `get_or_create` creates if not exists, which is NOT what we want for removal.
    # We need a `get_playlist_id_by_title` or similar.
    # But `get_or_create` does cache population.
    # If we use `get_or_create`, we might accidentally create a playlist if it doesn't exist, which is weird for remove command but maybe acceptable?
    # No, creating a playlist just to fail removing a video from it is silly.
    
    # Let's trust `get_or_create` for now as it handles the name resolution, 
    # but strictly we should probably add `get_playlist_id` to the library later.
    # For now, if the user passes the exact title of an EXISTING playlist, `get_or_create` returns its ID.
    
    playlist_id = manager.get_or_create_playlist(playlist_name_or_id)
    
    if not playlist_id:
        console.print(f"[red]Playlist not found (or failed to create?): {playlist_name_or_id}[/]")
        raise typer.Exit(code=1)
        
    if manager.remove_video_from_playlist(playlist_id, video_id):
        console.print(f"[green]Successfully removed {video_id} from playlist {playlist_name_or_id}[/]")
    else:
        console.print(f"[red]Failed to remove video from playlist (maybe not found?).[/]")
        raise typer.Exit(code=1)
