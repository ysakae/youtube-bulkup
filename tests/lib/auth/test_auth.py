import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch, mock_open

import pytest
from pathlib import Path

# Import the functions directly
from src.lib.auth.auth import authenticate_new_profile, get_authenticated_service, logout
from src.lib.auth.profiles import get_active_profile, list_profiles, set_active_profile


@pytest.fixture
def temp_tokens_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)
        # Patch paths in profiles.py with Path objects
        with patch("src.lib.auth.profiles.TOKENS_DIR", dir_path), \
             patch("src.lib.auth.profiles.ACTIVE_PROFILE_FILE", dir_path / ".active_profile"):
            yield dir_path


def test_profiles_management(temp_tokens_dir):
    # Initial state
    assert get_active_profile() == "default"
    assert list_profiles() == []

    # Create dummy token files
    (temp_tokens_dir / "default.pickle").touch()
    (temp_tokens_dir / "user2.pickle").touch()

    assert "default" in list_profiles()
    assert "user2" in list_profiles()

    set_active_profile("user2")
    assert get_active_profile() == "user2"

    set_active_profile("default")
    assert get_active_profile() == "default"


@patch("src.lib.auth.auth.InstalledAppFlow")
def test_authenticate_new_profile(mock_flow, temp_tokens_dir):
    mock_flow_instance = mock_flow.from_client_secrets_file.return_value
    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.refresh_token = "refresh_token"
    mock_flow_instance.run_local_server.return_value = mock_creds

    # Also mock config to avoid needing client_secrets.json file
    # Mock pickle.dump to avoid pickling the mock
    with patch("src.lib.auth.auth.config.auth.client_secrets_file", "dummy_secrets.json"), \
         patch("src.lib.auth.auth.os.path.exists", return_value=True), \
         patch("src.lib.auth.auth.build"), \
         patch("src.lib.auth.auth.pickle.dump"):
        
        authenticate_new_profile("test_user")

    # Verify file "exists" (we mocked pickle dump but file creation is done via open() in real code? 
    # Wait, if we mock open? No, we didn't mock open. 
    # But authenticate_new_profile calls get_authenticated_service which calls pickle.dump.
    # The real open() will create the file.
    
    assert (temp_tokens_dir / "test_user.pickle").exists()
    assert get_active_profile() == "test_user"


def test_logout(temp_tokens_dir):
    # Setup
    token_path = temp_tokens_dir / "logout_user.pickle"
    token_path.touch()
    
    set_active_profile("logout_user")
    
    assert logout("logout_user") is True
    assert not token_path.exists()
    
    assert logout("non_existent") is False


@patch("src.lib.auth.auth.build")
def test_get_authenticated_service(mock_build, temp_tokens_dir):
    # Create a dummy token for current profile
    token_path = temp_tokens_dir / "default.pickle"
    
    mock_creds = MagicMock()
    mock_creds.valid = True
    
    # Mock pickle.load to return our mock creds
    with patch("src.lib.auth.auth.pickle.load", return_value=mock_creds): 
        # Create empty file so os.path.exists returns true
        token_path.touch()
        
        with patch("src.lib.auth.auth.migrate_legacy_token"):
             service = get_authenticated_service()

    assert service is not None
    mock_build.assert_called_once()


def test_logout_active_profile(temp_tokens_dir):
    token_path = temp_tokens_dir / "default.pickle"
    token_path.touch()
    
    # name=None should use active profile (default)
    assert logout(None) is True
    assert not token_path.exists()


@patch("src.lib.auth.auth.build")
def test_get_authenticated_service_refresh_error(mock_build, temp_tokens_dir):
    token_path = temp_tokens_dir / "default.pickle"
    
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "rt"
    # refresh() raises Exception
    mock_creds.refresh.side_effect = Exception("Refresh Failed")
    
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "rt"
    # refresh() raises Exception
    mock_creds.refresh.side_effect = Exception("Refresh Failed")
    
    # Don't try to pickle mock, just create file
    with open(token_path, "wb") as f:
        f.write(b"dummy")
        
    # Should try to refresh, fail, then try new flow -> fail because no secrets file
    # We must patch os.path.exists to return False to trigger FileNotFoundError
    with patch("src.lib.auth.auth.pickle.load", return_value=mock_creds), \
         patch("src.lib.auth.auth.migrate_legacy_token"), \
         patch("src.lib.auth.auth.os.path.exists", return_value=False), \
         pytest.raises(FileNotFoundError):
             
        get_authenticated_service()


@patch("src.lib.auth.auth.build")
def test_get_authenticated_service_missing_secrets(mock_build, temp_tokens_dir):
    # No token file
    # Missing secrets file
    with patch("src.lib.auth.auth.os.path.exists", side_effect=lambda p: False), \
         pytest.raises(FileNotFoundError):
             
        get_authenticated_service()
