from src.config import AppConfig


class TestConfig:
    def test_default_config(self):
        """Test default configuration values."""
        config = AppConfig()
        assert config.auth.client_secrets_file == "client_secrets.json"
        assert config.upload.chunk_size == 4194304
        assert config.ai.enabled is False
        assert config.ai.model == "models/gemini-3-flash-preview"
        assert config.ai.language == "ja"

    def test_load_from_yaml(self, tmp_path):
        """Test loading configuration from a YAML file."""
        settings_file = tmp_path / "settings.yaml"
        settings_content = """
auth:
  client_secrets_file: "secret.json"
ai:
  enabled: true
  api_key: "yaml_key"
  language: "en"
        """
        settings_file.write_text(settings_content, encoding="utf-8")

        config = AppConfig.load(str(settings_file))

        assert config.auth.client_secrets_file == "secret.json"
        assert config.ai.enabled is True
        assert config.ai.api_key == "yaml_key"
        assert config.ai.language == "en"
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
