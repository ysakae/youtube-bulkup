import os
import json
import logging
import google.genai as genai
from typing import Dict, Any, Optional
from pathlib import Path
from .config import config

logger = logging.getLogger("youtube_up")

class MetadataGenerator:
    def __init__(self):
        self.enabled = config.ai.enabled
        self.api_key = config.ai.api_key or os.getenv("GEMINI_API_KEY")
        if self.enabled and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = config.ai.model
        elif self.enabled:
            logger.warning("AI enabled but no API Key found. Metadata generation will be skipped.")

    async def generate_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Generate title, description, and tags using Gemini.
        Refuses to run if disabled.
        """
        default_metadata = {
            "title": file_path.stem.replace("_", " ").title(),
            "description": f"Uploaded via YouTube Bulk Uploader.\n\nFilename: {file_path.name}",
            "tags": ["auto-upload"]
        }

        if not self.enabled or not self.api_key:
            return default_metadata

        logger.info(f"Generating AI metadata for {file_path.name}...")

        language = config.ai.language
        lang_instruction = "in Japanese" if language == "ja" else f"in {language}"

        prompt = f"""
        You are a YouTube SEO expert.
        Generate metadata for a video file named "{file_path.name}".
        The content should be generated **{lang_instruction}**.
        
        Return ONLY a raw JSON object (no markdown formatting) with the following structure:
        {{
            "title": "Engaging Title (max 100 chars, {lang_instruction})",
            "description": "SEO optimized description (3-5 lines, {lang_instruction})",
            "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
        }}
        """

        try:
            # Use AsyncClient via aio
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            text = response.text.strip()
            
            # Clean up potential markdown code blocks
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            
            data = json.loads(text)
            
            # Merge with defaults to ensure keys exist
            return {**default_metadata, **data}

        except Exception as e:
            logger.error(f"AI Generation failed: {e}. using defaults.")
            return default_metadata
