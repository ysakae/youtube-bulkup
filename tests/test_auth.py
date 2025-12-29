from unittest.mock import MagicMock

import pytest

from src.auth import get_authenticated_service
from src.config import config


class TestAuth:
    def test_get_authenticated_service_success(self, mocker):
        """Test successful authentication."""
        # Mock installedAppFlow
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        mock_from_client_secrets_file = mocker.patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=mock_flow,
        )

        # Mock build at point of use
        mock_build = mocker.patch("src.auth.build")

        # Mock pickle to avoid writing mock to file
        mocker.patch("src.auth.pickle")
        mocker.patch("builtins.open", mocker.mock_open())  # Mock open as well

        # Mock config
        mocker.patch.object(config.auth, "client_secrets_file", "secrets.json")
        mocker.patch.object(config.auth, "scopes", ["scope1"])

        # Mock checking paths
        def exists_side_effect(path):
            if "secrets.json" in str(path):
                return True
            return False

        mocker.patch("os.path.exists", side_effect=exists_side_effect)

        service = get_authenticated_service()

        assert service is not None
        # Debugging call mismatch
        try:
            mock_from_client_secrets_file.assert_called_with("secrets.json", ["scope1"])
        except AssertionError as e:
            raise AssertionError(
                f"Call mismatch. Actual: {mock_from_client_secrets_file.call_args}"
            ) from e

        mock_build.assert_called_with("youtube", "v3", credentials=mock_creds)

    def test_get_authenticated_service_no_secrets(self, mocker):
        """Test failure when secrets file missing."""
        mocker.patch("os.path.exists", return_value=False)
        mocker.patch.object(config.auth, "client_secrets_file", "missing.json")

        with pytest.raises(FileNotFoundError):
            get_authenticated_service()
