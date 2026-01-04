import typer
from rich.console import Console
from rich.panel import Panel

from ..lib.auth.auth import authenticate_new_profile, get_authenticated_service, logout
from ..lib.auth.profiles import get_active_profile, list_profiles, set_active_profile
from ..lib.core.logger import setup_logging

app = typer.Typer(help="Manage authentication profiles.")
console = Console()

@app.callback(invoke_without_command=True)
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


@app.command("login")
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


@app.command("switch")
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


@app.command("list")
def list_cmd():
    """List all profiles."""
    profiles = list_profiles()
    active = get_active_profile()
    console.print("[bold]Available Profiles:[/]")
    for p in profiles:
        mark = "*" if p == active else " "
        console.print(f" {mark} {p}")


@app.command("logout")
def logout_cmd(
    profile: str = typer.Argument(
        None, help="Profile name to logout from (default: active profile)"
    )
):
    """Logout from a profile."""
    if logout(profile):
        console.print(f"[green]Successfully logged out from {profile or 'active profile'}.[/green]")
    else:
        console.print(f"[yellow]No active session found for {profile or 'active profile'}.[/yellow]")
