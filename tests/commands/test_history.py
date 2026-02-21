
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


def test_export_json(mock_history_manager):
    """JSON形式のexportコマンドテスト"""
    mock_history_manager.export_records.return_value = '[{"file_hash": "h1", "video_id": "v1"}]'

    result = runner.invoke(app, ["export", "--format", "json"])
    assert result.exit_code == 0
    mock_history_manager.export_records.assert_called_once_with(format="json", output_path=None)


def test_export_csv_to_file(mock_history_manager):
    """CSV形式でファイル出力するexportコマンドテスト"""
    mock_history_manager.export_records.return_value = "file_path,file_hash\n/tmp/a.mp4,h1"

    result = runner.invoke(app, ["export", "--format", "csv", "--output", "/tmp/test.csv"])
    assert result.exit_code == 0
    assert "Exported to" in result.stdout
    mock_history_manager.export_records.assert_called_once_with(format="csv", output_path="/tmp/test.csv")


def test_import_json(mock_history_manager, tmp_path):
    """JSONファイルをimportするテスト"""
    import json

    test_file = tmp_path / "import.json"
    data = [
        {"file_path": "/tmp/i1.mp4", "file_hash": "h1", "video_id": "v1", "status": "success"},
    ]
    test_file.write_text(json.dumps(data))

    mock_history_manager.import_records.return_value = (1, 0)

    result = runner.invoke(app, ["import", str(test_file)])
    assert result.exit_code == 0
    assert "Import complete" in result.stdout
    assert "1 imported" in result.stdout


def test_import_file_not_found():
    """存在しないファイルを指定した場合のテスト"""
    result = runner.invoke(app, ["import", "/nonexistent/file.json"])
    assert result.exit_code == 1
    assert "File not found" in result.stdout
