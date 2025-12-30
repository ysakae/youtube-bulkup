import logging
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata

logger = logging.getLogger("youtube_up")

class FileMetadataGenerator:
    """
    Generates metadata from file attributes and internal video metadata
    using hachoir.
    """

    def generate(self, file_path: Path, index: int, total: int) -> Dict[str, Any]:
        """
        Generate title, description, tags, and recording details.
        
        Args:
            file_path: Path to the video file
            index: Current file index (1-based)
            total: Total files count
        """
        folder_name = file_path.parent.name
        file_name = file_path.name
        
        # 1. Extract internal metadata (Date, Duration, GPS if available)
        meta_info = self._extract_raw_metadata(file_path)
        
        # 2. Format Title
        # Format: 【Folder Name】Filename
        # Truncate if too long (YouTube max 100 chars)
        title = f"【{folder_name}】{file_path.stem}"
        if len(title) > 100:
            title = title[:97] + "..."

        # 3. Format Description
        # Folder Name
        # No. X/Y
        # 
        # File: Filename
        # Captured: Date
        creation_date = meta_info.get("creation_date")
        date_str = creation_date.strftime('%Y-%m-%d %H:%M:%S') if creation_date else "Unknown"
        
        description = (
            f"{folder_name}\n"
            f"No. {index}/{total}\n\n"
            f"File: {file_name}\n"
            f"Captured: {date_str}\n"
        )

        # 4. Tags
        tags = ["auto-upload", folder_name]
        if creation_date:
            tags.append(str(creation_date.year))
        
        # 5. Recording Details for YouTube API
        recording_details = {}
        if creation_date:
            # Format: YYYY-MM-DDThh:mm:ss.sZ
            recording_details["recordingDate"] = creation_date.isoformat() + "Z"

        # GPS Location
        if "latitude" in meta_info and "longitude" in meta_info:
            location = {
                "latitude": meta_info["latitude"],
                "longitude": meta_info["longitude"]
            }
            if "altitude" in meta_info:
                location["altitude"] = meta_info["altitude"]
            recording_details["location"] = location

        return {
            "title": title,
            "description": description,
            "tags": tags,
            "recordingDetails": recording_details
        }

    def _extract_raw_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Uses hachoir to extract creation date, duration, and GPS data.
        """
        info = {}
        parser = None
        try:
            parser = createParser(str(file_path))
            if not parser:
                logger.warning(f"Unable to parse file: {file_path}")
                return info

            metadata = extractMetadata(parser)
            if not metadata:
                logger.warning(f"No metadata found for: {file_path}")
                return info

            # Extract Creation Date
            if metadata.has("creation_date"):
                info["creation_date"] = metadata.get("creation_date")
            
            # Extract Duration
            if metadata.has("duration"):
                info["duration"] = metadata.get("duration")

            # Extract GPS Data
            # Note: The keys depend on hachoir's parser implementation for specific file types.
            # Common keys are 'latitude', 'longitude', 'altitude'.
            if metadata.has("latitude"):
                info["latitude"] = metadata.get("latitude")
            if metadata.has("longitude"):
                info["longitude"] = metadata.get("longitude")
            if metadata.has("altitude"):
                info["altitude"] = metadata.get("altitude")

        except Exception as e:
            logger.error(f"Error extracting metadata for {file_path}: {e}")
        finally:
            if parser:
                parser.close()
        
        return info
