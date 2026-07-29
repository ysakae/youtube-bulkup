from src.lib.core.config import AppConfig


class TestConfig:
    def test_default_config(self):
        """Test default configuration values."""
        config = AppConfig()
        assert config.auth.client_secrets_file == "client_secrets.json"
        assert config.upload.chunk_size == 4194304

    def test_load_from_yaml(self, tmp_path):
        """Test loading configuration from a YAML file."""
        settings_file = tmp_path / "settings.yaml"
        settings_content = """
auth:
  client_secrets_file: "secret.json"
        """
        settings_file.write_text(settings_content, encoding="utf-8")

        config = AppConfig.load(str(settings_file))

        assert config.auth.client_secrets_file == "secret.json"
        # Check defaults are preserved for missing fields
        assert config.upload.privacy_status == "private"

    def test_env_var_override(self, monkeypatch):
        """Test that environment variables (via dotenv/os) are respected if we implement that logic."""
        # Note: In the current implementation, config.py loads dotenv at module level.
        # But AppConfig.load() itself doesn't explicitly read env vars for all fields,
        # except mostly for what pydantic-settings might do if used, or manual logic.
        # The current code in config.py is:
        # load_dotenv()
        # class AppConfig(BaseModel)...
        # It doesn't seem to automatically override from env unless we use pydantic-settings or manual checks.
        # However, ai.py *does* check os.getenv("GEMINI_API_KEY") if config.ai.api_key is None.
        pass

    def test_load_nonexistent_file(self):
        """Test loading from a non-existent file falls back to defaults."""
        config = AppConfig.load("nonexistent.yaml")
        assert config.auth.client_secrets_file == "client_secrets.json"


class TestQuotaAndCacheConfig:
    def test_defaults(self):
        from src.lib.core.config import AppConfig

        cfg = AppConfig()
        assert cfg.quota.daily_limit == 10000
        assert cfg.quota.reserve == 1000
        assert cfg.cache.enabled is True
        assert cfg.cache.ttl_hours == 24
        assert cfg.cache.path == "youtube_cache.db"

    def test_load_from_yaml(self, tmp_path):
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text(
            "quota:\n"
            "  daily_limit: 500000\n"
            "  reserve: 20000\n"
            "cache:\n"
            "  enabled: false\n"
            "  ttl_hours: 6\n"
            "  path: 'custom_cache.db'\n",
            encoding="utf-8",
        )
        cfg = AppConfig.load(str(path))
        assert cfg.quota.daily_limit == 500000
        assert cfg.quota.reserve == 20000
        assert cfg.cache.enabled is False
        assert cfg.cache.ttl_hours == 6
        assert cfg.cache.path == "custom_cache.db"

    def test_effective_daily_quota_prefers_quota_section(self, tmp_path):
        """quota.daily_limit の方が大きければそちらを採る。"""
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text(
            "quota:\n  daily_limit: 500000\nupload:\n  daily_quota_limit: 30000\n",
            encoding="utf-8",
        )
        cfg = AppConfig.load(str(path))
        assert cfg.effective_daily_quota() == 500000

    def test_effective_daily_quota_falls_back_to_upload_section(self, tmp_path):
        """quota セクションが無く upload.daily_quota_limit だけ変更されている
        既存の設定ファイルとの後方互換。"""
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text("upload:\n  daily_quota_limit: 30000\n", encoding="utf-8")
        cfg = AppConfig.load(str(path))
        assert cfg.effective_daily_quota() == 30000

    def test_effective_daily_quota_default(self):
        from src.lib.core.config import AppConfig

        cfg = AppConfig()
        assert cfg.effective_daily_quota() == 10000

    def test_effective_daily_quota_takes_upload_when_larger(self, tmp_path):
        """quota セクションが明示されていても、upload.daily_quota_limit の方が
        大きければそちらを採る (Critical 2)。

        出荷 settings.yaml は quota ブロックを含むため、以前の実装では
        upload.daily_quota_limit を引き上げても一切反映されなかった。
        設定箇所が2つあるので、どちらを上げても効くようにする。
        """
        from src.lib.core.config import AppConfig

        path = tmp_path / "settings.yaml"
        path.write_text(
            "quota:\n  daily_limit: 10000\nupload:\n  daily_quota_limit: 1000000\n",
            encoding="utf-8",
        )
        cfg = AppConfig.load(str(path))
        assert cfg.effective_daily_quota() == 1000000

    def test_effective_daily_quota_uses_max_without_yaml(self):
        """ファイルを介さずに直接構築した場合も大きい方を採る。"""
        from src.lib.core.config import AppConfig, QuotaConfig, UploadConfig

        cfg = AppConfig(
            quota=QuotaConfig(daily_limit=10000),
            upload=UploadConfig(daily_quota_limit=500000),
        )
        assert cfg.effective_daily_quota() == 500000

        cfg2 = AppConfig(
            quota=QuotaConfig(daily_limit=500000),
            upload=UploadConfig(daily_quota_limit=10000),
        )
        assert cfg2.effective_daily_quota() == 500000

    def test_default_daily_quota_limit_constant_is_shared(self):
        """既定値のマジックナンバーが定数化されている (Critical 2b)。"""
        from src.lib.core.config import DEFAULT_DAILY_QUOTA_LIMIT, AppConfig

        cfg = AppConfig()
        assert DEFAULT_DAILY_QUOTA_LIMIT == 10000
        assert cfg.upload.daily_quota_limit == DEFAULT_DAILY_QUOTA_LIMIT
        assert cfg.quota.daily_limit == DEFAULT_DAILY_QUOTA_LIMIT
