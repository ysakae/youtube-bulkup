from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from typer.testing import CliRunner
from src.main import app

runner = CliRunner()

def test_upload_simple_check_skips_hash(mocker, tmp_path):
    """Test that --simple-check skips hash calculation if path matches."""
    video_file = tmp_path / "video.mp4"
    video_file.touch()

    mocker.patch("src.lib.core.logger.setup_logging")
    mocker.patch("src.commands.upload.get_credentials")
    mocker.patch("src.services.upload_manager.scan_directory", return_value=[video_file])
    
    # Mock calc_hash to assert it's NOT called
    mock_calc_hash = mocker.patch("src.services.upload_manager.calculate_hash", return_value="hash123")

    mock_hist = MagicMock()
    # Path match is TRUE
    mock_hist.is_uploaded_by_path.return_value = True
    mocker.patch("src.commands.upload.HistoryManager", return_value=mock_hist)

    mocker.patch("src.commands.upload.FileMetadataGenerator")
    mocker.patch("src.commands.upload.VideoUploader")

    # Run with --simple-check
    result = runner.invoke(app, ["upload", str(tmp_path), "--simple-check", "--dry-run"])

    assert result.exit_code == 0
    # Verify we hit the "Skipping duplicate (by path)" logic
    assert "Skipping duplicate (by path)" in result.stdout
    
    # Assert hash calculation was skipped
    mock_calc_hash.assert_not_called()
    
    # Assert is_uploaded_by_path matched the path
    mock_hist.is_uploaded_by_path.assert_called_with(str(video_file))

def test_upload_no_simple_check_does_hash(mocker, tmp_path):
    """Test that without --simple-check, we DO hash even if path lines up (or logic normally)."""
    video_file = tmp_path / "video.mp4"
    video_file.touch()
    
    mocker.patch("src.lib.core.logger.setup_logging")
    mocker.patch("src.commands.upload.get_credentials")
    mocker.patch("src.services.upload_manager.scan_directory", return_value=[video_file])
    mock_calc_hash = mocker.patch("src.services.upload_manager.calculate_hash", return_value="hash123")
    
    mock_hist = MagicMock()
    mock_hist.is_uploaded.return_value = True # Pretend it's uploaded by hash
    mock_hist.is_uploaded_by_path.return_value = True # Even if path matches
    mocker.patch("src.commands.upload.HistoryManager", return_value=mock_hist)
    mocker.patch("src.commands.upload.FileMetadataGenerator")

    # Run WITHOUT --simple-check
    result = runner.invoke(app, ["upload", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    
    # Should hash
    mock_calc_hash.assert_called_once()
    
    # Should check duplicate by hash not path (explicitly anyway)
    mock_hist.is_uploaded.assert_called_once()
