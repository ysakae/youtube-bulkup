import logging
from typing import Dict, Optional, Any, List

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from ..core.config import config

logger = logging.getLogger("youtube_up")

class PlaylistManager:
    """
    Manages YouTube Playlist interactions.
    """
    def __init__(self, credentials):
        self.credentials = credentials
        # Cache playlist IDs to avoid redundant API calls: {title: playlist_id}
        self._playlist_cache: Dict[str, str] = {}
        self._initialized = False

    def _ensure_cache(self):
        """
        Populates the cache with existing playlists from the channel.
        This is done lazily to avoid startup latency if not needed.
        """
        if self._initialized:
            return

        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            request = service.playlists().list(
                part="snippet,id",
                mine=True,
                maxResults=50  # Adjust pagination if user has many playlists
            )
            response = request.execute()
            
            # Todo: Handle pagination for >50 playlists
            for item in response.get("items", []):
                title = item["snippet"]["title"]
                self._playlist_cache[title] = item["id"]
            
            self._initialized = True
            logger.debug(f"Initialized playlist cache with {len(self._playlist_cache)} items.")
            
        except HttpError as e:
            logger.error(f"Failed to list playlists: {e}")
            # Don't mark as initialized so we retry next time? 
            # Or just proceed with empty cache and potentially fail duplicates?
            # Safe to assume empty for now.

    def get_or_create_playlist(self, title: str, privacy_status: str = "private") -> Optional[str]:
        """
        Retrieves a playlist ID by title, or creates one if it doesn't exist.
        """
        self._ensure_cache()
        
        if title in self._playlist_cache:
            return self._playlist_cache[title]
        
        # Create new playlist
        logger.info(f"Creating new playlist: '{title}' ({privacy_status})")
        
        body = {
            "snippet": {
                "title": title,
                "description": f"Created into playlist '{title}' by youtube-bulkup"
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }
        
        try:
            # Build fresh service for write operation
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            request = service.playlists().insert(
                part="snippet,status",
                body=body
            )
            response = request.execute()
            
            playlist_id = response["id"]
            self._playlist_cache[title] = playlist_id
            logger.info(f"Created playlist '{title}' -> {playlist_id}")
            return playlist_id
            
        except HttpError as e:
            logger.error(f"Failed to create playlist '{title}': {e}")
            return None

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Adds a video to a specific playlist.
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
        
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)

            request = service.playlistItems().insert(
                part="snippet",
                body=body
            )
            request.execute()
            logger.info(f"Added video {video_id} to playlist {playlist_id}")
            return True
            
        except HttpError as e:
            if "videoAlreadyInPlaylist" in str(e): # Check specific error message if possible
                logger.info(f"Video {video_id} already in playlist {playlist_id}")
                return True
            
            logger.error(f"Failed to add video {video_id} to playlist {playlist_id}: {e}")
            return False

    def remove_video_from_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Removes a video from a specific playlist.
        Requires finding the playlistItemId first.
        """
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            # 1. Find the playlistItem ID for this video in this playlist
            # API doesn't let us delete by videoId directly, we need the item ID.
            request = service.playlistItems().list(
                part="id",
                playlistId=playlist_id,
                videoId=video_id
            )
            response = request.execute()
            items = response.get("items", [])
            
            if not items:
                logger.warning(f"Video {video_id} not found in playlist {playlist_id}")
                return False
                
            # There could theoretically be duplicates, we remove the first one found
            playlist_item_id = items[0]["id"]
            
            # 2. Delete the playlist item
            delete_request = service.playlistItems().delete(id=playlist_item_id)
            delete_request.execute()
            
            logger.info(f"Removed video {video_id} from playlist {playlist_id}")
            return True

        except HttpError as e:
            logger.error(f"Failed to remove video {video_id} from playlist {playlist_id}: {e}")
            return False

    def get_video_ids_from_playlist(self, playlist_name_or_id: str) -> List[str]:
        """
        Retrieves all video IDs from a playlist.
        """
        playlist_id = self.get_or_create_playlist(playlist_name_or_id)
        if not playlist_id:
             # It might be an ID directly, check if we can list items using it as ID
             # But get_or_create logic currently treats input as title if not found in cache.
             # If user passes ID, get_or_create creates a new playlist with that ID as title.
             # This is a limitation acknowledged in previous steps.
             # For now, we rely on get_or_create resolving title to ID.
             # If it fails (e.g. error), we return empty.
             return []

        video_ids = []
        try:
            service = build("youtube", "v3", credentials=self.credentials, cache_discovery=False)
            
            request = service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50
            )
            
            while request:
                response = request.execute()
                for item in response.get("items", []):
                    video_ids.append(item["contentDetails"]["videoId"])
                
                request = service.playlistItems().list_next(request, response)
                
            logger.info(f"Found {len(video_ids)} videos in playlist {playlist_name_or_id}")
            return video_ids

        except HttpError as e:
            logger.error(f"Failed to get videos from playlist {playlist_name_or_id}: {e}")
            return []
