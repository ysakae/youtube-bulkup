import os
import yaml
from dotenv import load_dotenv
from typing import List, Optional

# Load environment variables from .env file
load_dotenv()
from pydantic import BaseModel, Field

class AuthConfig(BaseModel):
    client_secrets_file: str = "client_secrets.json"
    token_file: str = "token.pickle"
    scopes: List[str] = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]

class UploadConfig(BaseModel):
    chunk_size: int = 4194304  # 4MB
    retry_count: int = 5
    privacy_status: str = "private"

class AIConfig(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = None
    api_key: Optional[str] = None
    model: str = "models/gemini-3-flash-preview"
    language: str = "ja"

class AppConfig(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    history_db: str = "upload_history.json"

    @classmethod
    def load(cls, path: str = "settings.yaml") -> "AppConfig":
        """Load configuration from a YAML file, with env var overrides."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # Allow individual sections to be partial
            return cls(**data)
        return cls()

# Global config instance
config = AppConfig.load()
