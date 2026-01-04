import shutil
from pathlib import Path
from typing import List

from ..core.config import config

TOKENS_DIR = Path("tokens")
ACTIVE_PROFILE_FILE = Path(".active_profile")
DEFAULT_PROFILE = "default"


def ensure_tokens_dir():
    """Ensure the tokens directory exists."""
    TOKENS_DIR.mkdir(exist_ok=True)


def get_profile_path(name: str) -> Path:
    """Get the path for a profile's token file."""
    return TOKENS_DIR / f"{name}.pickle"


def list_profiles() -> List[str]:
    """List all available profiles."""
    if not TOKENS_DIR.exists():
        return []
    return [p.stem for p in TOKENS_DIR.glob("*.pickle")]


def get_active_profile() -> str:
    """Get the name of the currently active profile."""
    if ACTIVE_PROFILE_FILE.exists():
        return ACTIVE_PROFILE_FILE.read_text().strip()
    return DEFAULT_PROFILE


def set_active_profile(name: str):
    """Set the active profile."""
    ensure_tokens_dir()
    ACTIVE_PROFILE_FILE.write_text(name)


def migrate_legacy_token():
    """Migrate legacy token.pickle to tokens/default.pickle if needed."""
    legacy_token = Path(config.auth.token_file)
    default_token = get_profile_path(DEFAULT_PROFILE)

    if legacy_token.exists() and not default_token.exists():
        ensure_tokens_dir()
        shutil.move(str(legacy_token), str(default_token))
        set_active_profile(DEFAULT_PROFILE)
        print(f"Migrated legacy token to {default_token}")


def delete_profile_token(name: str) -> bool:
    """
    Delete the token file for a profile.
    Returns True if file was deleted, False if it didn't exist.
    """
    token_path = get_profile_path(name)
    if token_path.exists():
        token_path.unlink()
        return True
    return False
