from src.lib.core.logger import setup_logging


def test_setup_logging(mocker):
    """Test logger configuration."""
    mock_basicConfig = mocker.patch("logging.basicConfig")

    setup_logging(level="DEBUG")

    mock_basicConfig.assert_called_once()
    args, kwargs = mock_basicConfig.call_args
    assert kwargs["level"] == "DEBUG"
    assert kwargs["format"] is not None
