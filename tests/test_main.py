from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from src.main import app

runner = CliRunner()


class TestMain:
    @pytest.fixture
    def mock_deps(self, mocker):
        """Mock all external dependencies for main.py."""
        mocker.patch("src.lib.core.logger.setup_logging")
        
        # Mock service for auth check
        mock_service = MagicMock()
        mock_channels = MagicMock()
        mock_service.channels.return_value = mock_channels
        mock_channels.list.return_value.execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "title": "TestChannel",
                        "customUrl": "@testhandle",
                    }
                }
            ]
        }
        
        mock_auth = mocker.patch("src.commands.auth.get_authenticated_service")
        mock_auth.return_value = mock_service

        mocker.patch("src.commands.upload.VideoUploader")
        mocker.patch("src.commands.upload.HistoryManager")
        mocker.patch("src.commands.upload.FileMetadataGenerator")
        mocker.patch("src.services.upload_manager.scan_directory", return_value=[])

        return mock_auth

    def test_auth_status(self, mock_deps, mocker):
        """Test auth status (default)."""
        mocker.patch("src.commands.auth.get_active_profile", return_value="default")
        
        result = runner.invoke(app, ["auth"])
        
        assert result.exit_code == 0
        assert "Active Profile: default" in result.stdout
        assert "Connected to channel: TestChannel (@testhandle)" in result.stdout

    def test_auth_list(self, mock_deps, mocker):
        """Test auth list command."""
        mocker.patch("src.commands.auth.list_profiles", return_value=["default", "other"])
        mocker.patch("src.commands.auth.get_active_profile", return_value="default")
        
        result = runner.invoke(app, ["auth", "list"])
        
        assert result.exit_code == 0
        assert "Available Profiles:" in result.stdout
        assert "* default" in result.stdout
        assert "  other" in result.stdout

    def test_upload_dry_run(self, mocker, tmp_path):
        """Test upload command in dry-run mode."""
        # 実ファイルを作成することで stat() の FileNotFoundError を回避
        video_file = tmp_path / "video.mp4"
        video_file.touch()

        mocker.patch("src.lib.core.logger.setup_logging")
        mocker.patch("src.services.upload_manager.scan_directory", return_value=[video_file])
        mocker.patch("src.services.upload_manager.calculate_hash", return_value="hash123")

        # History モック
        mock_hist = MagicMock()
        mock_hist.is_uploaded.return_value = False
        mocker.patch("src.commands.upload.HistoryManager", return_value=mock_hist)

        # Metadata モック
        mock_meta = MagicMock()
        mock_meta.generate = MagicMock(
            return_value={
                "title": "File Title", 
                "description": "File Desc", 
                "tags": [],
                "recordingDetails": {}
            }
        )
        mocker.patch("src.commands.upload.FileMetadataGenerator", return_value=mock_meta)

        result = runner.invoke(app, ["upload", "./test_dir", "--dry-run"])

        assert result.exit_code == 0
        assert "Found 1 video files" in result.stdout
        # richフォーマットのため、キーフレーズのみチェック
        assert "File Title" in result.stdout

    def test_upload_real_run(self, mocker, tmp_path):
        """Test upload command with real upload (mocked)."""
        video_file = tmp_path / "video.mp4"
        video_file.touch()

        mocker.patch("src.lib.core.logger.setup_logging")
        mocker.patch("src.commands.upload.get_credentials")  # Mock auth
        mocker.patch("src.services.upload_manager.scan_directory", return_value=[video_file])
        mocker.patch("src.services.upload_manager.calculate_hash", return_value="hash123")

        mock_hist = MagicMock()
        mock_hist.is_uploaded.return_value = False
        mocker.patch("src.commands.upload.HistoryManager", return_value=mock_hist)

        mock_meta = MagicMock()
        mock_meta.generate = MagicMock(
            return_value={"title": "Title", "tags": [], "recordingDetails": {}}
        )
        mocker.patch("src.commands.upload.FileMetadataGenerator", return_value=mock_meta)

        mock_uploader = MagicMock()
        mock_uploader.upload_video = AsyncMock(return_value="new_vid_123")
        mocker.patch("src.commands.upload.VideoUploader", return_value=mock_uploader)

        result = runner.invoke(app, ["upload", "./test_dir"])

        assert result.exit_code == 0

        # Debug info
        if mock_hist.add_record.call_count == 0:
            print("History add_record NOT called.")
            print("STDOUT:", result.stdout)
            print("Upload Video Calls:", mock_uploader.upload_video.call_count)
            print("Upload Video Return:", mock_uploader.upload_video.return_value)

        # Check logic flow via mocks instead of fragile stdout capturing
        mock_hist.add_record.assert_called_once()
        mock_uploader.upload_video.assert_called_once()
