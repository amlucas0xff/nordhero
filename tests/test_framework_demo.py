"""
Demo test for the NordVPN WireGuard Manager test framework.

This file demonstrates the use of the test framework with direct API access
and the auto-retry functionality.
"""

import os
import sys
import pytest
import logging
from pathlib import Path
from unittest.mock import Mock, patch

from tests.test_base import DirectAPITestBase
from tests.test_retry import retry
from tests.test_assertions import assert_valid_server, assert_database_integrity


@retry(max_retries=3)
def test_framework_demo_retry(config_manager, mock_db_client):
    """Test that demonstrates the retry functionality with auto-fixes."""
    # Create a DirectAPITestBase instance to directly access API functions
    api_test = DirectAPITestBase(config_manager)
    
    # Patch the db_client with our mock
    api_test.db_client = mock_db_client
    
    # Setup mock to fail on first call, then succeed
    mock_servers = [
        {'id': 1, 'name': 'test-server', 'hostname': 'test.example.com', 
         'ip_address': '192.168.1.1', 'country': 'Test Country', 
         'country_code': 'TC', 'load': 10, 'public_key': 'a' * 43 + '='}
    ]
    
    # First call will return None (failure), second call will return servers (success)
    mock_db_client.get_top_servers.side_effect = [None, mock_servers]
    
    # This will fail on first attempt but pass on retry
    servers = api_test.get_top_servers(limit=1)
    
    # Verify result after retries
    assert len(servers) == 1
    assert servers[0]['name'] == 'test-server'
    assert mock_db_client.get_top_servers.call_count == 2  # Called twice due to retry


@pytest.mark.parametrize('server_data,should_fail', [
    # Valid server data
    ({
        'id': 1, 
        'name': 'valid-server', 
        'hostname': 'valid.example.com',
        'ip_address': '192.168.1.1', 
        'country': 'Valid Country', 
        'country_code': 'VC', 
        'load': 10, 
        'public_key': 'a' * 43 + '='
    }, False),
    
    # Invalid server - missing field
    ({
        'id': 2, 
        'hostname': 'invalid.example.com',
        'ip_address': '192.168.1.2', 
        'country': 'Invalid Country', 
        'country_code': 'IC', 
        'load': 20, 
        'public_key': 'b' * 43 + '='
        # 'name' field is missing
    }, True),
    
    # Invalid server - bad IP address
    ({
        'id': 3, 
        'name': 'bad-ip-server', 
        'hostname': 'bad-ip.example.com',
        'ip_address': 'not-an-ip-address', 
        'country': 'Bad IP Country', 
        'country_code': 'BI', 
        'load': 30, 
        'public_key': 'c' * 43 + '='
    }, True),
    
    # Invalid server - bad public key
    ({
        'id': 4, 
        'name': 'bad-key-server', 
        'hostname': 'bad-key.example.com',
        'ip_address': '192.168.1.4', 
        'country': 'Bad Key Country', 
        'country_code': 'BK', 
        'load': 40, 
        'public_key': 'too-short'
    }, True),
])
def test_assertion_utilities(server_data, should_fail):
    """Test the assertion utilities with various data."""
    if should_fail:
        with pytest.raises(Exception):
            assert_valid_server(server_data)
    else:
        assert_valid_server(server_data)  # Should not raise an exception


@retry(max_retries=2)
def test_database_integrity_with_retry(temp_dir):
    """Test the database integrity check with retry functionality."""
    # Create a test database path
    db_path = temp_dir / 'test_database.db'
    
    # First call - database doesn't exist yet, should fail
    # but retry mechanism should create it
    assert_database_integrity(db_path)
    
    # Verify the database file exists now
    assert db_path.exists()


@pytest.mark.parametrize('test_params', [
    {'max_retries': 1, 'should_succeed': False},  # Will fail (only 1 retry)
    {'max_retries': 3, 'should_succeed': True},   # Should succeed on 3rd retry
])
def test_retry_mechanism(test_params):
    """Test the retry mechanism with different retry counts."""
    counter = {'attempts': 0}
    
    @retry(max_retries=test_params['max_retries'])
    def flaky_function():
        counter['attempts'] += 1
        # This function will succeed only on the 3rd attempt
        if counter['attempts'] < 3:
            raise ValueError(f"Attempt {counter['attempts']} failed")
        return True
    
    if test_params['should_succeed']:
        assert flaky_function() is True
        assert counter['attempts'] == 3
    else:
        with pytest.raises(Exception):
            flaky_function()
        assert counter['attempts'] == test_params['max_retries'] 