import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_successful_response():
    """Mock successful API response"""
    return {
        "hostname": "test1.nordvpn.com",
        "station": "192.168.1.1",
        "load": 45,
        "locations": [
            {
                "country": {
                    "name": "United States",
                    "city": {"name": "New York"}
                }
            }
        ],
        "technologies": [
            {
                "identifier": "wireguard_udp",
                "metadata": [
                    {"name": "public_key", "value": "test_public_key"}
                ]
            }
        ]
    }

@pytest.fixture
def mock_response(mock_successful_response):
    """Mock requests.Response object"""
    mock_resp = Mock()
    mock_resp.json.return_value = [mock_successful_response]
    mock_resp.raise_for_status.return_value = None
    return mock_resp
