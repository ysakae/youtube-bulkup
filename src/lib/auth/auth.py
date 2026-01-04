import logging
import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from ..core.config import config
from .profiles import (
    ensure_tokens_dir,
    get_active_profile,
    get_profile_path,
    migrate_legacy_token,
    set_active_profile,
    delete_profile_token,
)

logger = logging.getLogger("youtube_up")


def get_authenticated_service() -> Resource:
    """
    Authenticate and return a YouTube API service resource.
    Handles token storage and refreshing for the active profile.
    """
    # Migration check
    migrate_legacy_token()
    
    active_profile = get_active_profile()
    token_file = get_profile_path(active_profile)
    
    creds = None
    client_secrets_file = config.auth.client_secrets_file
    scopes = config.auth.scopes

    # Load existing credentials
    if os.path.exists(token_file):
        try:
            with open(token_file, "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.warning(f"Failed to load token file {token_file}: {e}")

    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired token...")
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                creds = None

        if not creds:
            if not os.path.exists(client_secrets_file):
                raise FileNotFoundError(
                    f"Client secrets file not found at: {client_secrets_file}. "
                    "Please download it from Google Cloud Console."
                )

            logger.info(f"Starting new OAuth flow for profile: {active_profile}...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, scopes
            )
            creds = flow.run_local_server(port=0)

        # Save credentials
        ensure_tokens_dir()
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)
            logger.info(f"Saved credentials to {token_file}")

    return build("youtube", "v3", credentials=creds)


def authenticate_new_profile(name: str) -> Resource:
    """
    Authenticate a new profile and set it as active.
    """
    # Set as active first so get_authenticated_service uses this name
    set_active_profile(name)
    
    # This will trigger the OAuth flow for the new profile name since token won't exist
    return get_authenticated_service()


def logout(name: str = None):
    """
    Logout from a profile (delete token).
    If name is None, logs out from the active profile.
    """
    if name is None:
        name = get_active_profile()
    
    if delete_profile_token(name):
        logger.info(f"Successfully logged out from profile: {name}")
        return True
    else:
        logger.warning(f"Profile {name} was not logged in (token not found).")
        return False
