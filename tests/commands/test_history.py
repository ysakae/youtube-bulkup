
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.main import app
from src.lib.data.history import HistoryManager

runner = CliRunner()

@pytest.fixture
def mock_history_manager():
    with patch("src.commands.history.HistoryManager") as mock_cls:
        instance = mock_cls.return_value
        yield instance

def test_delete_by_path(mock_history_manager):
    mock_history_manager.delete_record_by_path.return_value = True
    
    # history.app is added to root, so "delete" is a sibling of "history" command
    result = runner.invoke(app, ["delete", "--path", "/tmp/test.mp4"])
    
    assert result.exit_code == 0
    assert "Deleted history for path" in result.stdout
    mock_history_manager.delete_record_by_path.assert_called()

def test_delete_by_hash(mock_history_manager):
    mock_history_manager.delete_record.return_value = True
    
    result = runner.invoke(app, ["delete", "--hash", "abc123hash"])
    
    assert result.exit_code == 0
    assert "Deleted history for hash" in result.stdout
    mock_history_manager.delete_record.assert_called_with("abc123hash")

def test_delete_by_video_id(mock_history_manager):
    mock_history_manager.delete_record_by_video_id.return_value = True
    
    result = runner.invoke(app, ["delete", "--video-id", "vid_123"])
    
    assert result.exit_code == 0
    assert "Deleted history for Video ID" in result.stdout
    mock_history_manager.delete_record_by_video_id.assert_called_with("vid_123")

def test_delete_not_found(mock_history_manager):
    mock_history_manager.delete_record.return_value = False
    
    result = runner.invoke(app, ["delete", "--hash", "missing"])
    
    assert result.exit_code == 0
    assert "No record found" in result.stdout

def test_delete_no_args():
    result = runner.invoke(app, ["delete"])
    assert result.exit_code == 0
    assert "Please specify" in result.stdout
