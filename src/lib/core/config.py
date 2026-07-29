import os
from typing import List

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from pydantic import BaseModel, Field  # noqa: E402

# YouTube Data API の既定の日次クォータ上限 (ユニット)。
# GCP で引き上げ申請をしていないプロジェクトの初期値。
# upload.daily_quota_limit と quota.daily_limit の両方の既定値として使う
# (同じ数値を2箇所に直書きすると、片方だけ変更したときに不整合になる)。
DEFAULT_DAILY_QUOTA_LIMIT = 10000


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
    # YouTube API の1日あたりのクォータ上限
    daily_quota_limit: int = DEFAULT_DAILY_QUOTA_LIMIT


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
    # 実際の GCP 上限に合わせて調整する
    daily_limit: int = DEFAULT_DAILY_QUOTA_LIMIT
    # 予備として残すユニット。orphans / dedupe は1回の全走査で
    # 動画一覧 + プレイリスト走査に約1,000ユニットを消費するため、
    # その分を差し引いた残りを書き込み操作に充てる。
    reserve: int = 1000


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

    @classmethod
    def load(cls, path: str = "settings.yaml") -> "AppConfig":
        """Load configuration from a YAML file, with env var overrides."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # Allow individual sections to be partial
            return cls(**data)
        return cls()

    def effective_daily_quota(self) -> int:
        """実効的な日次クォータ上限を返す。

        quota.daily_limit と upload.daily_quota_limit のうち大きい方を採る。
        設定箇所が2つあるため、どちらを引き上げても効くようにして
        「上げたのに反映されない」という事故を防ぐ。

        以前は「quota セクションが明示されていなければ upload 側を使う」
        という後方互換フォールバックだったが、出荷 settings.yaml が
        quota ブロックを含むため出荷時点で死んでおり、
        upload.daily_quota_limit を引き上げても無視されていた。
        """
        return max(self.quota.daily_limit, self.upload.daily_quota_limit)


# Global config instance
config = AppConfig.load()
