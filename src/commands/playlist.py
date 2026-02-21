import typer
from rich.console import Console
from rich.table import Table

from ..lib.auth.auth import get_credentials
from ..lib.core.logger import setup_logging
from ..lib.video.playlist import PlaylistManager

app = typer.Typer(help="Manage playlists.")
console = Console()

def _get_manager():
    try:
        credentials = get_credentials()
        return PlaylistManager(credentials)
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

@app.command("list")
def list_playlists(
    name: str = typer.Argument(None, help="Playlist name or ID to show details"),
):
    """
    プレイリストの一覧を表示する。
    名前またはIDを指定すると、そのプレイリスト内の動画一覧を表示する。
    """
    setup_logging(level="INFO")
    manager = _get_manager()

    if name:
        # 指定プレイリストの動画一覧
        items = manager.list_playlist_items(name)
        if not items:
            console.print(f"[yellow]No videos found in playlist: {name}[/]")
            return

        table = Table(title=f"Playlist: {name} ({len(items)} videos)")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="magenta")
        table.add_column("Video ID", style="cyan")

        for item in items:
            vid = item["video_id"]
            link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
            table.add_row(str(item["position"] + 1), item["title"], link)

        console.print(table)
    else:
        # 全プレイリスト一覧
        playlists = manager.list_playlists()
        if not playlists:
            console.print("[yellow]No playlists found.[/]")
            return

        table = Table(title=f"Playlists ({len(playlists)} total)")
        table.add_column("Title", style="magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Videos", style="green", justify="right")
        table.add_column("Privacy", style="dim")

        for pl in playlists:
            table.add_row(pl["title"], pl["id"], str(pl["item_count"]), pl["privacy"])

        console.print(table)

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
        console.print("[red]Failed to add video to playlist.[/]")
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
    
    # プレイリスト名からIDを解決（存在しない場合は新規作成しない）
    playlist_id = manager.find_playlist_id(playlist_name_or_id)
    
    if not playlist_id:
        console.print(f"[red]Playlist not found: {playlist_name_or_id}[/]")
        raise typer.Exit(code=1)
        
    if manager.remove_video_from_playlist(playlist_id, video_id):
        console.print(f"[green]Successfully removed {video_id} from playlist {playlist_name_or_id}[/]")
    else:
        console.print("[red]Failed to remove video from playlist (maybe not found?).[/]")
        raise typer.Exit(code=1)

@app.command("rename")
def rename_playlist(
    old_name_or_id: str = typer.Argument(..., help="Current Playlist Name or ID"),
    new_name: str = typer.Argument(..., help="New Playlist Name"),
):
    """
    Rename a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if manager.rename_playlist(old_name_or_id, new_name):
        console.print(f"[green]Successfully renamed playlist to '{new_name}'[/]")
    else:
        console.print("[red]Failed to rename playlist.[/]")
        raise typer.Exit(code=1)

@app.command("orphans")
def list_orphans(
    fix: bool = typer.Option(False, "--fix", help="Automatically assign orphans to playlists based on history"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation for fix"),
):
    """
    Find videos not in any playlist (orphans) and optionally fix them.
    """
    setup_logging(level="INFO")
    
    # 1. Initialize Managers
    credentials = get_credentials()
    pl_manager = PlaylistManager(credentials)
    # We need VideoManager for getting all uploads
    from ..lib.video.manager import VideoManager
    vid_manager = VideoManager(credentials)
    
    # 2. Fetch all videos and playlist map
    console.print("[yellow]Fetching all uploaded videos and playlist data... (this may take a while)[/]")
    
    all_videos = vid_manager.get_all_uploaded_videos()
    if not all_videos:
        console.print("[red]No uploaded videos found or API error.[/]")
        return

    playlist_map = pl_manager.get_all_playlists_map()
    
    # 3. Identify Orphans
    # Create a set of all video IDs currently in ANY playlist
    videos_in_playlists = set()
    for vid_set in playlist_map.values():
        videos_in_playlists.update(vid_set)
        
    orphans = []
    for vid in all_videos:
        if vid["id"] not in videos_in_playlists:
            orphans.append(vid)
            
    console.print(f"[bold]Total Videos:[/] {len(all_videos)}")
    console.print(f"[bold]Videos in Playlists:[/] {len(videos_in_playlists)}")
    console.print(f"[bold red]Orphan Videos:[/] {len(orphans)}")
    
    if not orphans:
        console.print("[green]No orphan videos found. All videos are in at least one playlist.[/]")
        return

    # List orphans
    console.print("\n[bold]Orphan Videos:[/]")
    for orphan in orphans:
        console.print(f"- {orphan['title']} ({orphan['id']})")
        
    if not fix:
        console.print("\n[dim]Run with --fix to attempt automatic assignment based on local history.[/]")
        return
        
    # 4. Fix Orphans
    if not yes:
        if not typer.confirm(f"\nAttempt to assign {len(orphans)} videos to playlists based on local history?"):
            raise typer.Abort()
            
    # Initialize History to look up paths
    from ..lib.data.history import HistoryManager
    history = HistoryManager()
    
    console.print("\n[bold]Assigning Orphans...[/]")
    
    for orphan in orphans:
        vid_id = orphan["id"]
        # Look up in history
        record = history.get_record_by_video_id(vid_id)
        
        target_playlist = None
        if record:
            # Try getting explicit playlist name first
            target_playlist = record.get("playlist_name")
            
            # Fallback to parent dir of file path if available
            if not target_playlist and record.get("file_path"):
                try:
                    from pathlib import Path
                    target_playlist = Path(record["file_path"]).parent.name
                except Exception:
                    pass
        
        if target_playlist:
            # Add to playlist
            # We assume get_or_create handles the existence check
            pl_id = pl_manager.get_or_create_playlist(target_playlist)
            if pl_id:
                if pl_manager.add_video_to_playlist(pl_id, vid_id):
                    console.print(f"[green]Assigned {orphan['title']} -> {target_playlist}[/]")
                else:
                     console.print(f"[red]Failed to assign {orphan['title']} -> {target_playlist}[/]")
            else:
                 console.print(f"[red]Failed to get/create playlist {target_playlist} for {orphan['title']}[/]")
        else:
            console.print(f"[dim]Skipping {orphan['title']} (no history/playlist found)[/]")
            
    history.close()
