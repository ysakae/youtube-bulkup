import logging
import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from .config import config

logger = logging.getLogger("youtube_up")


def get_authenticated_service() -> Resource:
    """
    Authenticate and return a YouTube API service resource.
    Handles token storage and refreshing.
    """
    creds = None
    token_file = config.auth.token_file
    client_secrets_file = config.auth.client_secrets_file
    scopes = config.auth.scopes

    # Load existing credentials
    if os.path.exists(token_file):
        try:
            with open(token_file, "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.warning(f"Failed to load token file: {e}")

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

            logger.info("Starting new OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, scopes
            )
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)
            logger.info(f"Saved credentials to {token_file}")

    return build("youtube", "v3", credentials=creds)
