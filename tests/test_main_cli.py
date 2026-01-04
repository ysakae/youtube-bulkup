import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.main import app

runner = CliRunner()


@pytest.fixture
def mock_dependencies():
    with patch("src.main.get_authenticated_service") as mock_auth, \
         patch("src.main.VideoUploader") as mock_uploader_cls, \
         patch("src.main.HistoryManager") as mock_history_cls, \
         patch("src.main.FileMetadataGenerator") as mock_meta_cls, \
         patch("src.main.calculate_hash", return_value="dummy_hash"), \
         patch("src.main.scan_directory") as mock_scan:
             
        mock_auth.return_value = MagicMock()
        mock_uploader = mock_uploader_cls.return_value
        
        # Correctly mock async method to return completed future
        def create_future(*args, **kwargs):
            f = asyncio.Future()
            f.set_result("vid_123")
            return f
            
        mock_uploader.upload_video = MagicMock(side_effect=create_future)
        
        mock_history = mock_history_cls.return_value
        # Default: not uploaded
        mock_history.is_uploaded.return_value = False
        mock_history.delete_record.return_value = True
        
        mock_meta = mock_meta_cls.return_value
        mock_meta.generate.return_value = {
            "title": "Test Title",
            "description": "Desc",
            "tags": []
        }
        
        yield {
            "auth": mock_auth,
            "uploader": mock_uploader,
            "history": mock_history,
            "scan": mock_scan,
        }


def test_upload_command_dry_run(mock_dependencies):
    # Setup mock paths for scan
    path1 = MagicMock()
    path1.__str__.return_value = "/tmp/videos/test.mp4"
    path1.resolve.return_value = Path("/tmp/videos/test.mp4") # For print output
    path1.name = "test.mp4"
    path1.stat.return_value.st_size = 1000
    
    mock_dependencies["scan"].return_value = [path1]
    
    with patch("src.main.process_video_files") as mock_process:
        result = runner.invoke(app, ["upload", "/tmp/videos", "--dry-run"])
        assert result.exit_code == 0
        # If mocked process_video_files, scan_directory might not be called if we mock it?
        # Wait, upload command calls scan_directory then process_video_files.
        # But here we mocked scan_directory.
        
    # Real dry run flow (verify scan message and dry run process call)
    result = runner.invoke(app, ["upload", "/tmp/videos", "--dry-run"])
    assert result.exit_code == 0
    assert "Scanning /tmp/videos..." in result.stdout
    assert "[Dry Run]" in result.stdout


def test_reupload_no_args():
    result = runner.invoke(app, ["reupload"])
    assert result.exit_code == 0
    assert "No files, hashes, or video IDs provided" in result.stdout


def test_reupload_by_path(mock_dependencies):
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve", return_value=Path("/abs/path/test.mp4")):
             
        result = runner.invoke(app, ["reupload", "test.mp4"])
        assert result.exit_code == 0
        
        # Verify delete_record called
        mock_dependencies["history"].delete_record.assert_called_with("dummy_hash")
        assert "Cleared history for: test.mp4" in result.stdout


def test_reupload_by_hash(mock_dependencies):
    mock_dependencies["history"].delete_record.return_value = True
    # Mock get_record
    mock_dependencies["history"].get_record.return_value = {
        "file_path": "/stored/path/vid.mp4"
    }
    
    with patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(app, ["reupload", "--hash", "hash123"])
        assert result.exit_code == 0
        
        mock_dependencies["history"].get_record.assert_called_with("hash123")
        assert "Cleared history for: vid.mp4" in result.stdout


def test_reupload_dry_run(mock_dependencies):
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve", return_value=Path("/abs/path/test.mp4")):
             
        result = runner.invoke(app, ["reupload", "test.mp4", "--dry-run"])
        assert result.exit_code == 0
        
        # Should NOT call delete_record
        mock_dependencies["history"].delete_record.assert_not_called()
        assert "[Dry Run] Would clear history" in result.stdout



def test_retry_command(mock_dependencies):
    mock_dependencies["history"].get_failed_records.return_value = [
        {"file_path": "/failed/vid.mp4"}
    ]
    
    with patch("pathlib.Path.exists", return_value=True):
        result = runner.invoke(app, ["retry"])
        assert result.exit_code == 0
        assert "Found 1 failed uploads" in result.stdout


def test_history_command():
    with patch("src.main.HistoryManager") as mock_hist_cls:
        mock_hist = mock_hist_cls.return_value
        mock_hist.get_all_records.return_value = [
            {"timestamp": 1234567890, "status": "success", "file_path": "test.mp4", "video_id": "vid1"},
            {"timestamp": 1234567899, "status": "failed", "file_path": "fail.mp4", "error": "err"}
        ]
        
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "Success: 1" in result.stdout
        assert "Failed: 1" in result.stdout


def test_auth_status_command():
    with patch("src.main.get_active_profile", return_value="default"), \
         patch("src.main.get_authenticated_service") as mock_service:
        
        mock_service.return_value.channels().list().execute.return_value = {
            "items": [{"snippet": {"title": "My Channel", "customUrl": "@mychan"}}]
        }
        
        result = runner.invoke(app, ["auth"])
        assert result.exit_code == 0
        assert "Active Profile: default" in result.stdout
        assert "Connected to channel: My Channel" in result.stdout


def test_auth_login_command():
    with patch("src.main.authenticate_new_profile") as mock_auth, \
         patch("src.main.show_status"): 
        
        result = runner.invoke(app, ["auth", "login", "new_user"])
        assert result.exit_code == 0
        mock_auth.assert_called_with("new_user")
        assert "Successfully authenticated profile: new_user" in result.stdout


def test_auth_switch_command():
    with patch("src.main.list_profiles", return_value=["default", "user2"]), \
         patch("src.main.set_active_profile") as mock_set, \
         patch("src.main.show_status"):
             
        result = runner.invoke(app, ["auth", "switch", "user2"])
        assert result.exit_code == 0
        mock_set.assert_called_with("user2")
        assert "Switched to profile: user2" in result.stdout

        # Fail case
        result = runner.invoke(app, ["auth", "switch", "non_existent"])
        assert result.exit_code == 1
        assert "Profile 'non_existent' not found" in result.stdout


def test_auth_list_command():
    with patch("src.main.list_profiles", return_value=["default", "user2"]), \
         patch("src.main.get_active_profile", return_value="default"):
             
        result = runner.invoke(app, ["auth", "list"])
        assert result.exit_code == 0
        assert "* default" in result.stdout
        assert "  user2" in result.stdout


def test_auth_logout_command():
    with patch("src.main.logout", return_value=True) as mock_logout:
        result = runner.invoke(app, ["auth", "logout", "user2"])
        assert result.exit_code == 0
        mock_logout.assert_called_with("user2")
        assert "Successfully logged out" in result.stdout


def test_upload_command_full_flow(mock_dependencies):
    # Setup scan result
    path1 = MagicMock()
    path1.__str__.return_value = "/tmp/videos/v1.mp4"
    path1.name = "v1.mp4"
    path1.parent = Path("/tmp/videos")
    path1.stat.return_value.st_size = 1000
    
    mock_dependencies["scan"].return_value = [path1]
    
    # Run
    result = runner.invoke(app, ["upload", "/tmp/videos"])
    assert result.exit_code == 0
    
    # Verify processing calls
    mock_dependencies["history"].is_uploaded.assert_called_with("dummy_hash")
    mock_dependencies["uploader"].upload_video.assert_called()
    mock_dependencies["history"].add_record.assert_called()
    assert "Uploaded v1.mp4" in result.stdout


def test_upload_duplicate_skip(mock_dependencies):
    path1 = MagicMock()
    path1.__str__.return_value = "/tmp/videos/v1.mp4"
    path1.name = "v1.mp4"
    path1.parent = Path("/tmp/videos")
    path1.stat.return_value.st_size = 1000
    mock_dependencies["scan"].return_value = [path1]
    
    # Mark as uploaded
    mock_dependencies["history"].is_uploaded.return_value = True
    
    result = runner.invoke(app, ["upload", "/tmp/videos"])
    assert result.exit_code == 0
    
    assert "Skipping duplicate" in result.stdout
    mock_dependencies["uploader"].upload_video.assert_not_called()


def test_upload_quota_exceeded(mock_dependencies):
    path1 = MagicMock()
    path1.__str__.return_value = "/tmp/videos/v1.mp4"
    path1.name = "v1.mp4"
    path1.parent = Path("/tmp/videos")
    path1.stat.return_value.st_size = 1000
    mock_dependencies["scan"].return_value = [path1]
    
    # Simulate Quota Error
    from googleapiclient.errors import HttpError
    resp = MagicMock()
    resp.status = 403
    mock_dependencies["uploader"].upload_video.side_effect = HttpError(resp, b"quotaExceeded")
    
    result = runner.invoke(app, ["upload", "/tmp/videos"])
    assert result.exit_code == 0
    
    assert "CRITICAL: YouTube Upload Quota Exceeded" in result.stdout
    mock_dependencies["history"].add_failure.assert_called()


def test_upload_general_error(mock_dependencies):
    path1 = MagicMock()
    path1.__str__.return_value = "/tmp/videos/v1.mp4"
    path1.name = "v1.mp4"
    path1.parent = Path("/tmp/videos")
    path1.stat.return_value.st_size = 1000
    mock_dependencies["scan"].return_value = [path1]
    
    mock_dependencies["uploader"].upload_video.side_effect = Exception("General Error")
    
    result = runner.invoke(app, ["upload", "/tmp/videos"])
    assert result.exit_code == 0
    
    
    assert "Error processing v1.mp4" in result.stdout
    mock_dependencies["history"].add_failure.assert_called()


def test_reupload_auth_error(mock_dependencies):
    # Setup files so it proceeds to auth
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve", return_value=Path("/abs/path/test.mp4")):
             
        # Simulate Auth Error
        mock_dependencies["auth"].side_effect = Exception("Auth Failed")
        
        result = runner.invoke(app, ["reupload", "test.mp4"])
        assert result.exit_code == 1
        assert "Auth Error" in result.stdout


def test_upload_auth_error(mock_dependencies):
    # Simulate Auth Error during upload command start
    mock_dependencies["auth"].side_effect = Exception("Auth Failed")
    
    result = runner.invoke(app, ["upload", "/tmp/videos"])
    assert result.exit_code == 1
    assert "Auth Failed" in result.stdout


