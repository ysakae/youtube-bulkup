import typer
from rich.console import Console

from ..lib.auth.auth import get_credentials
from ..lib.video.manager import VideoManager
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

@app.command("update-privacy")
def update_privacy(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    status: str = typer.Argument(..., help="Privacy status (private, public, unlisted)"),
):
    """
    Update the privacy status of a video.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if manager.update_privacy_status(video_id, status):
        console.print(f"[green]Successfully updated {video_id} to {status}[/]")
    else:
        console.print(f"[red]Failed to update privacy status.[/]")
        raise typer.Exit(code=1)
