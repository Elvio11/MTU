import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def no_real_requests():
    """Fail if any test tries to make a real HTTP request."""
    # We patch requests.Session.request instead of requests.get/post directly
    # as many libraries use the session.
    with patch("requests.Session.request") as mock_req, \
         patch("aiohttp.ClientSession._request") as mock_aio:
        mock_req.side_effect = RuntimeError("Real HTTP request attempted in test!")
        mock_aio.side_effect = RuntimeError("Real aiohttp request attempted in test!")
        yield
