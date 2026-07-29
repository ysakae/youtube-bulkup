"""`yt-up quota` の表示が実際のクォータのモデルに沿っていることを検証する。

動画のアップロードは「Video Uploads per day」(本数ベースの別枠) で
カウントされ、Queries per day (ユニット) は消費しない。
"""

import time
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.main import app

runner = CliRunner()


@pytest.fixture
def mock_history_manager():
    with patch("src.commands.quota.HistoryManager") as mock_cls:
        instance = mock_cls.return_value
        yield instance


def _records(count: int):
    now = time.time()
    return [
        {"status": "success", "timestamp": now, "file_size": 1024}
        for _ in range(count)
    ]


def test_shows_upload_count_against_video_uploads_per_day(mock_history_manager):
    """本日のアップロード本数は Video Uploads per day の枠で示す。"""
    mock_history_manager.get_all_records.return_value = _records(30)

    result = runner.invoke(app, ["quota"])

    assert result.exit_code == 0
    assert "30" in result.stdout
    assert "100" in result.stdout, "Video Uploads per day の上限が示されていない"
    assert "Video Uploads per day" in result.stdout


def test_does_not_report_upload_units_as_queries_usage(mock_history_manager):
    """アップロード本数 x 1,600 units を Queries per day の使用量として
    報告しない (回帰防止)。100 本なら旧実装は 160,000 units と表示していた。"""
    mock_history_manager.get_all_records.return_value = _records(100)

    result = runner.invoke(app, ["quota"])

    assert result.exit_code == 0
    assert "160,000" not in result.stdout
    # プレイリスト追加分 100 x 50 = 5,000 units が Queries per day の使用量
    assert "5,000" in result.stdout


def test_ignores_yesterday_uploads(mock_history_manager):
    yesterday = time.time() - 86400 * 2
    mock_history_manager.get_all_records.return_value = [
        {"status": "success", "timestamp": yesterday, "file_size": 1024}
    ]

    result = runner.invoke(app, ["quota"])

    assert result.exit_code == 0
    assert "Uploads Today: 0" in result.stdout or "0/100" in result.stdout


def test_limit_option_overrides_queries_per_day(mock_history_manager):
    mock_history_manager.get_all_records.return_value = _records(2)

    result = runner.invoke(app, ["quota", "--limit", "50000"])

    assert result.exit_code == 0
    assert "50,000" in result.stdout
