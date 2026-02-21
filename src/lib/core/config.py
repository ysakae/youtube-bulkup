import os
from typing import List

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from pydantic import BaseModel, Field  # noqa: E402


class AuthConfig(BaseModel):
    client_secrets_file: str = "client_secrets.json"
    token_file: str = "token.pickle"
    scopes: List[str] = [
        "https://www.googleapis.com/auth/youtube",
    ]


class UploadConfig(BaseModel):
    chunk_size: int = 4194304  # 4MB
    retry_count: int = 5
    privacy_status: str = "private"
    daily_quota_limit: int = 10000  # YouTube API の1日あたりのクォータ上限


class MetadataConfig(BaseModel):
    # テンプレート変数: {folder}, {stem}, {filename}, {date}, {year}, {index}, {total}
    title_template: str = "【{folder}】{stem}"
    description_template: str = (
        "{folder}\n"
        "No. {index}/{total}\n\n"
        "File: {filename}\n"
        "Captured: {date}"
    )
    tags: List[str] = ["auto-upload"]


class AppConfig(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    history_db: str = "upload_history.db"

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
