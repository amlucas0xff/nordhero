import os
import pytest
import requests
from unittest.mock import patch, Mock
from requests.exceptions import RequestException
from nordvpn_client.types import WireGuardServerInfo

from nordvpn_client.wireguard import WireGuardClient
from nordvpn_client.exceptions import APIError, DataValidationError

def test_successful_server_fetch(mock_response):
    """Test successful server fetch and processing"""
    with patch('requests.get', return_value=mock_response):
        client = WireGuardClient()
        servers = client.get_servers(limit=1)
        
        assert len(servers) == 1
        server = servers[0]
        assert server.hostname == "test1.nordvpn.com"
        assert server.ip == "192.168.1.1"
        assert server.country == "United States"
        assert server.city == "New York"
        assert server.load == 45
        assert server.public_key == "test_public_key"

def test_api_error():
    """Test handling of API errors"""
    with patch('requests.get', side_effect=RequestException("Connection error")):
        client = WireGuardClient()
        with pytest.raises(APIError) as exc_info:
            client.get_servers()
        assert "Connection error" in str(exc_info.value)

def test_invalid_data():
    """Test handling of invalid response data"""
    mock_resp = Mock()
    mock_resp.json.return_value = [{"invalid": "data"}]
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        with pytest.raises(DataValidationError):
            client.get_servers()

def test_empty_response():
    """Test handling of empty response"""
    mock_resp = Mock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        servers = client.get_servers()
        assert len(servers) == 0

def test_custom_timeout():
    """Test custom timeout setting"""
    with patch('requests.get') as mock_get:
        client = WireGuardClient(timeout=30)
        try:
            client.get_servers()
        except:
            pass
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['timeout'] == 30

def test_server_missing_required_fields():
    """Test handling of server data missing required fields"""
    mock_resp = Mock()
    mock_resp.json.return_value = [{"hostname": "test.com"}]  # Missing other required fields
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        with pytest.raises(DataValidationError):
            client.get_servers()

def test_api_response_status():
    """Test handling of non-200 HTTP status"""
    mock_resp = Mock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        with pytest.raises(APIError):
            client.get_servers()

def test_server_limit_parameter(mock_successful_response):
    """Test server limit parameter is respected"""
    mock_resp = Mock()
    mock_resp.json.return_value = [mock_successful_response] * 2  # Return only 2 servers as requested
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        servers = client.get_servers(limit=2)
        assert len(servers) == 2

def test_server_processing(mock_successful_response):
    """Test server data processing with missing optional fields"""
    server_data = mock_successful_response.copy()
    # Remove optional technology metadata
    server_data['technologies'][0]['metadata'] = []
    
    mock_resp = Mock()
    mock_resp.json.return_value = [server_data]
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        servers = client.get_servers()
        assert servers[0].public_key == ""  # Should default to empty string

def test_wireguard_server_info_validation():
    """Test WireGuardServerInfo model validation"""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        WireGuardServerInfo(
            hostname="test.com",
            ip="invalid_ip",
            country="Test",
            city="Test",
            load=-1,  # Invalid load value
            publicKey="test"
        )

def test_export_to_csv(tmp_path, mock_successful_response):
    """Test exporting server information to CSV"""
    mock_resp = Mock()
    mock_resp.json.return_value = [mock_successful_response]
    mock_resp.raise_for_status.return_value = None
    
    with patch('requests.get', return_value=mock_resp):
        client = WireGuardClient()
        servers = client.get_servers()
        
        # Use temporary directory for test file
        csv_path = tmp_path / "test_export.csv"
        filepath = client.export_to_csv(servers, str(csv_path))
        
        assert os.path.exists(filepath)
        
        # Verify CSV contents
        with open(filepath, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # Header + 1 server
            assert 'hostname,ip,country,city,load,public_key' in lines[0]
            assert 'test1.nordvpn.com' in lines[1]
