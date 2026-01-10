import logging
import typer
from rich.console import Console

from .commands import auth, history, upload, reupload, retry, sync, quota

app = typer.Typer(help="YouTube Bulk Uploader CLI", add_completion=False)
console = Console()
logger = logging.getLogger("youtube_up")

# Register commands
app.add_typer(auth.app, name="auth")
app.add_typer(history.app)
app.add_typer(upload.app)
app.add_typer(reupload.app)
app.add_typer(retry.app)
app.add_typer(sync.app)
app.add_typer(quota.app)

if __name__ == "__main__":
    app()
