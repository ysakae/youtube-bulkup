import pytest
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from src.main import app

runner = CliRunner()

@pytest.fixture
def mock_dependencies():
    with patch("src.commands.sync.get_authenticated_service") as m_auth, \
         patch("src.commands.sync.HistoryManager") as m_hist_cls, \
         patch("src.services.sync_manager.HistoryManager") as m_sm_hist_cls:
        
        mock_service = MagicMock()
        m_auth.return_value = mock_service
        
        mock_history = MagicMock()
        m_hist_cls.return_value = mock_history
        m_sm_hist_cls.return_value = mock_history # SyncManager instantiates or uses it? No, passed in.
        
        yield {
            "service": mock_service,
            "history": mock_history
        }

def test_sync_dry_run_no_auth():
    with patch("src.commands.sync.get_authenticated_service", side_effect=Exception("No Auth")):
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 1
        assert "Auth Error" in result.stdout

def test_sync_perfect_match(mock_dependencies):
    # Mock Remote: 1 video, ID "vid1"
    mock_service = mock_dependencies["service"]
    
    # channels.list response
    mock_service.channels().list().execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "PL_UPLOADS"}}}]
    }
    
    # playlistItems.list response
    mock_service.playlistItems().list().execute.return_value = {
        "items": [
            {
                "snippet": {"title": "Video 1"},
                "contentDetails": {"videoId": "vid1"}
            }
        ],
        # No nextPageToken
    }
    
    # Mock Local: 1 record, ID "vid1"
    mock_dependencies["history"].get_all_records.return_value = [
        {"video_id": "vid1", "status": "success", "file_path": "/path/to/vid1.mp4"}
    ]
    
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "Remote Videos: 1" in result.stdout
    assert "In Sync: 1" in result.stdout
    assert "Local history is perfectly in sync" in result.stdout

    assert result.exit_code == 0

def test_sync_missing_local(mock_dependencies):
    # Remote has vid1, Local has empty
    mock_service = mock_dependencies["service"]
    mock_service.channels().list().execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "PL_UPLOADS"}}}]
    }
    mock_service.playlistItems().list().execute.return_value = {
        "items": [
            {
                "snippet": {"title": "Video 1"},
                "contentDetails": {"videoId": "vid1"}
            }
        ]
    }
    
    mock_dependencies["history"].get_all_records.return_value = []
    
    with patch("src.commands.sync.Table") as MockTable:
        mock_table_instance = MockTable.return_value
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        
        # Verify add_row called with link markup
        # args[0] should be the Video ID column content
        calls = mock_table_instance.add_row.call_args_list
        # We expect at least one call. The one for vid1 should contain the link.
        found_link = False
        for call in calls:
            if "[link=https://youtu.be/vid1]vid1[/link]" in call[0][0]:
                found_link = True
                break
        assert found_link, "Link markup not found in Table.add_row calls"

def test_sync_missing_remote(mock_dependencies):
    # Remote has empty, Local has vid1
    mock_service = mock_dependencies["service"]
    mock_service.channels().list().execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "PL_UPLOADS"}}}]
    }
    mock_service.playlistItems().list().execute.return_value = {
        "items": []
    }
    
    mock_dependencies["history"].get_all_records.return_value = [
        {"video_id": "vid1", "status": "success", "file_path": "/path/to/vid1.mp4"}
    ]
    
    with patch("src.commands.sync.Table") as MockTable:
        mock_table_instance = MockTable.return_value
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        
        calls = mock_table_instance.add_row.call_args_list
        found_link = False
        for call in calls:
            if "[link=https://youtu.be/vid1]vid1[/link]" in call[0][0]:
                found_link = True
                break
        assert found_link, "Link markup not found in Table.add_row calls"
