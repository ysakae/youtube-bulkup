from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_env(monkeypatch):
    """Fixture to mock environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_api_key")


@pytest.fixture
def mock_google_client(mocker):
    """Fixture to mock the Google GenAI Client."""
    mock_client = MagicMock()
    mocker.patch("google.genai.Client", return_value=mock_client)
    return mock_client
