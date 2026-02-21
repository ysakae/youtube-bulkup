import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

from ..core.config import config

logger = logging.getLogger("youtube_up")

class FileMetadataGenerator:
    """
    Generates metadata from file attributes and internal video metadata
    using hachoir. テンプレート設定と .yt-meta.yaml によるカスタマイズに対応。
    """

    def _load_folder_override(self, folder: Path) -> Dict[str, Any]:
        """
        フォルダ内の .yt-meta.yaml を読み込む。
        存在しない場合は空辞書を返す。
        """
        meta_file = folder / ".yt-meta.yaml"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                logger.info(f"Loaded folder override: {meta_file}")
                return data
            except Exception as e:
                logger.warning(f"Failed to read {meta_file}: {e}")
        return {}

    def _resolve_template_config(self, folder: Path) -> Dict[str, Any]:
        """
        settings.yaml のメタデータ設定をベースに、
        フォルダ別 .yt-meta.yaml でオーバーライドして返す。
        """
        # ベース設定
        base = {
            "title_template": config.metadata.title_template,
            "description_template": config.metadata.description_template,
            "tags": list(config.metadata.tags),
        }
        # フォルダ別オーバーライド
        override = self._load_folder_override(folder)
        if override:
            if "title_template" in override:
                base["title_template"] = override["title_template"]
            if "description_template" in override:
                base["description_template"] = override["description_template"]
            if "tags" in override:
                base["tags"] = override["tags"]
            if "extra_tags" in override:
                base["tags"] = base["tags"] + override["extra_tags"]
        return base

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
        
        # テンプレート設定を解決
        tmpl = self._resolve_template_config(file_path.parent)
        
        # テンプレート変数を準備
        creation_date = meta_info.get("creation_date")
        date_str = creation_date.strftime('%Y-%m-%d %H:%M:%S') if creation_date else "Unknown"
        year_str = str(creation_date.year) if creation_date else ""
        
        # 安全なテンプレート展開用の変数マップ
        vars_map = {
            "folder": folder_name,
            "stem": file_path.stem,
            "filename": file_name,
            "date": date_str,
            "year": year_str,
            "index": str(index),
            "total": str(total),
        }

        # 2. Format Title (テンプレート展開)
        try:
            title = tmpl["title_template"].format_map(vars_map)
        except (KeyError, ValueError) as e:
            logger.warning(f"Title template error: {e}, falling back to default")
            title = f"【{folder_name}】{file_path.stem}"
        if len(title) > 100:
            title = title[:97] + "..."

        # 3. Format Description (テンプレート展開)
        try:
            description = tmpl["description_template"].format_map(vars_map)
        except (KeyError, ValueError) as e:
            logger.warning(f"Description template error: {e}, falling back to default")
            description = (
                f"{folder_name}\n"
                f"No. {index}/{total}\n\n"
                f"File: {file_name}\n"
                f"Captured: {date_str}\n"
            )

        # 4. Tags (テンプレート設定 + 動的タグ)
        tags = list(tmpl["tags"])
        if folder_name not in tags:
            tags.append(folder_name)
        if year_str and year_str not in tags:
            tags.append(year_str)
        
        # 5. Recording Details for YouTube API
        recording_details = {}
        if creation_date:
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

    def _extract_hachoir_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extra metadata using hachoir."""
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

    def _extract_raw_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Uses hachoir to extract creation date, duration, and GPS data.
        """
        info = self._extract_hachoir_metadata(file_path)
        
        # Fallback: If no GPS data from hachoir, try binary scan
        if "latitude" not in info:
            gps_from_binary = self._scan_gps_from_bytes(file_path)
            if gps_from_binary:
                info.update(gps_from_binary)

        return info

    def _scan_gps_from_bytes(self, file_path: Path) -> Dict[str, Any]:
        """
        Fallback method to scan binary for ISO 6709 GPS string.
        Pattern: ±DD.DDDD±DDD.DDDD(±AAA.AAA/)
        Example: +35.4524+139.6431/
        """
        import re
        # Regex for ISO 6709: (lat)(long)(alt optional)
        # Lat: +35.4524
        # Long: +139.6431
        # Alt: +10.0/ (Optional, trailing slash)
        pattern = re.compile(rb'([+-]\d+\.\d+)([+-]\d+\.\d+)(?:([+-]\d+\.?\d*)/)?')
        
        try:
            with open(file_path, 'rb') as f:
                # Scan first 50MB (usually sufficient for metadata atoms)
                data = f.read(50 * 1024 * 1024)
                
                match = pattern.search(data)
                
                if match:
                    lat_b, long_b, alt_b = match.groups()
                    result = {
                        "latitude": float(lat_b),
                        "longitude": float(long_b)
                    }
                    if alt_b:
                        result["altitude"] = float(alt_b)
                    
                    logger.info(f"GPS extracted via binary scan: {result}")
                    return result
                
                # Try scanning tail (last 5MB)
                f.seek(0, 2)
                total_size = f.tell()
                if total_size > 50 * 1024 * 1024:
                    f.seek(max(0, total_size - 5 * 1024 * 1024))
                    data = f.read()
                    
                    match = pattern.search(data)
                    if match:
                        lat_b, long_b, alt_b = match.groups()
                        result = {
                            "latitude": float(lat_b),
                            "longitude": float(long_b)
                        }
                        if alt_b:
                            result["altitude"] = float(alt_b)
                        
                        logger.info(f"GPS extracted via binary scan (tail): {result}")
                        return result
                    
        except Exception as e:
            logger.warning(f"Binary GPS scan failed for {file_path}: {e}")
        
        return {}
