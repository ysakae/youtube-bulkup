import os
from typing import List

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from pydantic import BaseModel, Field, PrivateAttr  # noqa: E402


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


class QuotaConfig(BaseModel):
    daily_limit: int = 10000  # 実際の GCP 上限に合わせて調整する
    reserve: int = 1000  # 予備として残すユニット


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_hours: int = 24
    path: str = "youtube_cache.db"


class AppConfig(BaseModel):
    auth: AuthConfig = Field(default_factory=AuthConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    history_db: str = "upload_history.db"

    # quota セクションが設定ファイルに明示されていたかを保持する (後方互換の判定用)
    _has_explicit_quota: bool = PrivateAttr(default=False)

    @classmethod
    def load(cls, path: str = "settings.yaml") -> "AppConfig":
        """Load configuration from a YAML file, with env var overrides."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # Allow individual sections to be partial
            instance = cls(**data)
            instance._has_explicit_quota = "quota" in data
            return instance
        return cls()

    def effective_daily_quota(self) -> int:
        """実効的な日次クォータ上限を返す。

        quota.daily_limit を正とするが、quota セクションが無く
        upload.daily_quota_limit だけが既定値から変更されている
        既存の設定ファイルとの互換性のため、その場合は後者を使う。
        """
        if not self._has_explicit_quota and self.upload.daily_quota_limit != 10000:
            return self.upload.daily_quota_limit
        return self.quota.daily_limit


# Global config instance
config = AppConfig.load()
