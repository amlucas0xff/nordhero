import pytest
import os
import sqlite3
import time
from unittest.mock import patch, MagicMock, mock_open
import tempfile
from pathlib import Path

# Import modules to test
from models.database_management import (
    DatabaseClient, init_database, get_last_update_time, check_database_status, get_best_servers
)
from models.connection_management import update_server_list
from models.config_management import ConfigManager
from api.nordvpn_client.wireguard import WireGuardClient
from models.data_models import ServerDBRecord

# Define a fixture for a mock WireGuardClient
@pytest.fixture
def mock_wireguard_client():
    """Create a mock WireGuardClient for testing"""
    mock_client = MagicMock(spec=WireGuardClient)
    
    # Set up mock server data
    mock_servers = [
        {
            'hostname': f'server{i}.nordvpn.com',
            'ip': f'10.0.0.{i}',
            'country': ['United States', 'Canada', 'Germany', 'Japan'][i % 4],
            'city': ['New York', 'Toronto', 'Berlin', 'Tokyo'][i % 4],
            'load': i * 5,  # Vary the load
            'public_key': f'public_key_{i}'
        } for i in range(1, 11)  # Create 10 mock servers
    ]
    
    # Set up the get_servers method to respect the limit parameter
    def get_servers_with_limit(limit=0):
        servers = [ServerDBRecord(**server) for server in mock_servers]
        if limit > 0:
            return servers[:limit]
        return servers
    
    mock_client.get_servers.side_effect = get_servers_with_limit
    
    # Set up the export_to_csv method to create a real temp file
    def create_temp_csv(servers):
        import tempfile
        import csv
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        writer = csv.writer(temp_file)
        writer.writerow(['hostname', 'ip', 'country', 'city', 'load', 'public_key'])
        for server in servers:
            writer.writerow([server.hostname, server.ip, server.country, server.city, server.load, server.public_key])
        temp_file.close()
        return temp_file.name
    
    mock_client.export_to_csv.side_effect = create_temp_csv
    
    return mock_client

@pytest.fixture
def temp_db_path():
    """Create a temporary database path"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        db_path = temp_file.name
        
    # Return the path and ensure it's cleaned up after the test
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def config_manager(temp_db_path):
    """Create a ConfigManager with a temporary database path"""
    config_manager = MagicMock(spec=ConfigManager)
    config_manager.get.return_value = temp_db_path
    
    return config_manager

@pytest.fixture
def db_client(temp_db_path):
    """Create a DatabaseClient with a temporary database"""
    client = DatabaseClient(db_path=temp_db_path)
    client.connect()
    client.init_db()
    
    try:
        yield client
    finally:
        client.close()

# Tests for server update functionality
def test_init_database(mock_wireguard_client, config_manager):
    """Test initializing the database with server data"""
    with patch('models.database_management.WireGuardClient', return_value=mock_wireguard_client):
        with patch('time.sleep'):  # Skip sleep calls to speed up tests
            with patch('models.database_management.tqdm'):  # Skip progress bars
                # Initialize the database
                new_count, prev_count = init_database(limit=5, config_manager=config_manager)
                
                # Check the results
                assert prev_count == 0  # Should be 0 for a new database
                assert new_count == 5   # We requested 5 servers
                
                # Verify the API client was called correctly
                mock_wireguard_client.get_servers.assert_called_once_with(limit=5)
                mock_wireguard_client.export_to_csv.assert_called_once()
                
                # Check that the database has the correct data
                with DatabaseClient(db_path=config_manager.get()) as db:
                    db.cursor.execute('SELECT COUNT(*) FROM servers')
                    count = db.cursor.fetchone()[0]
                    assert count == 5
                    
                    # Check for metadata table with last_update
                    db.cursor.execute('SELECT value FROM metadata WHERE key = ?', ('last_update',))
                    assert db.cursor.fetchone() is not None

def test_update_server_list(mock_wireguard_client, config_manager):
    """Test updating the server list through the connection management function"""
    with patch('models.connection_management.init_database') as mock_init_db:
        with patch('builtins.input', return_value="5"):  # Mock user input for server limit
            with patch('builtins.print'):  # Suppress prints
                # Set up the mock to return some test data
                mock_init_db.return_value = (5, 0)
                
                # Call the update function
                update_server_list(config_manager)
                
                # Verify the init_database function was called with correct parameters
                mock_init_db.assert_called_once_with(5, config_manager)

def test_incremental_update(mock_wireguard_client, config_manager):
    """Test that subsequent updates correctly track the server count differences"""
    with patch('models.database_management.WireGuardClient', return_value=mock_wireguard_client):
        with patch('time.sleep'):  # Skip sleep calls
            with patch('models.database_management.tqdm'):  # Skip progress bars
                # Initial update with 3 servers
                mock_wireguard_client.get_servers.return_value = mock_wireguard_client.get_servers.return_value[:3]
                new_count1, prev_count1 = init_database(limit=3, config_manager=config_manager)
                assert prev_count1 == 0
                assert new_count1 == 3
                
                # Second update with 5 servers
                mock_wireguard_client.get_servers.return_value = mock_wireguard_client.get_servers.return_value[:5]
                new_count2, prev_count2 = init_database(limit=5, config_manager=config_manager)
                assert prev_count2 == 3  # Previous count should be 3
                assert new_count2 == 5   # New count should be 5
                
                # Verify the database has the updated data
                with DatabaseClient(db_path=config_manager.get()) as db:
                    db.cursor.execute('SELECT COUNT(*) FROM servers')
                    count = db.cursor.fetchone()[0]
                    assert count == 5

def test_get_last_update_time(config_manager):
    """Test retrieving the last update time"""
    with patch('models.database_management.DatabaseClient') as mock_db_class:
        # Mock instance of DatabaseClient
        mock_db = MagicMock()
        mock_db_class.return_value.__enter__.return_value = mock_db
        
        # Set up mock to return a specific update time
        mock_db.cursor.fetchone.return_value = ('2023-01-01 12:00:00',)
        
        # Test without time ago formatting
        result = get_last_update_time(config_manager, format_as_time_ago=False)
        assert result == '2023-01-01 12:00:00'
        
        # Test with time ago formatting
        with patch('models.database_management.get_time_ago', return_value='3 days ago'):
            result = get_last_update_time(config_manager, format_as_time_ago=True)
            assert result == '3 days ago'

def test_error_handling_api_failure(mock_wireguard_client, config_manager):
    """Test handling of API errors during server update"""
    # Make the API client raise an exception
    mock_wireguard_client.get_servers.side_effect = Exception("API Connection Error")
    
    with patch('models.database_management.WireGuardClient', return_value=mock_wireguard_client):
        with patch('time.sleep'):
            with patch('models.database_management.tqdm'):
                # The function should exit with system exit when the API fails
                with pytest.raises(SystemExit):
                    init_database(limit=5, config_manager=config_manager)

def test_database_error_handling(mock_wireguard_client, config_manager):
    """Test handling of database errors during server update"""
    # Simulate a database error by making the DatabaseClient raise an exception
    with patch('models.database_management.WireGuardClient', return_value=mock_wireguard_client):
        with patch('models.database_management.DatabaseClient') as mock_db_class:
            # Make the database client raise an exception when used
            mock_db_class.return_value.__enter__.side_effect = sqlite3.Error("Database Error")
            
            with patch('time.sleep'):
                with patch('models.database_management.tqdm'):
                    # The function should exit with system exit when the database fails
                    with pytest.raises(SystemExit):
                        init_database(limit=5, config_manager=config_manager)

def test_csv_processing_error(mock_wireguard_client, config_manager):
    """Test handling of CSV processing errors during server update"""
    # Make the export_to_csv method return a non-existent path
    mock_wireguard_client.export_to_csv.return_value = "/nonexistent/path/servers.csv"
    
    with patch('models.database_management.WireGuardClient', return_value=mock_wireguard_client):
        with patch('time.sleep'):
            with patch('models.database_management.tqdm'):
                # The function should raise an exception when the CSV file doesn't exist
                with pytest.raises(SystemExit):
                    init_database(limit=5, config_manager=config_manager)

def test_database_client_context_manager(db_client):
    """Test that the DatabaseClient context manager works correctly"""
    with DatabaseClient(db_path=db_client.db_path) as db:
        # Check that it's connected
        assert db.conn is not None
        assert db.cursor is not None
        
        # Execute a simple query
        db.cursor.execute('SELECT 1')
        assert db.cursor.fetchone()[0] == 1
    
    # Check that it's closed after the context manager exits
    assert db_client.conn is None

def test_get_best_servers(db_client):
    """Test getting the best servers from the database"""
    # Insert some test servers
    servers = [
        {'hostname': 'server1.nordvpn.com', 'ip': '10.0.0.1', 'country': 'United States', 'city': 'New York', 'load': 10, 'public_key': 'key1'},
        {'hostname': 'server2.nordvpn.com', 'ip': '10.0.0.2', 'country': 'United States', 'city': 'Los Angeles', 'load': 20, 'public_key': 'key2'},
        {'hostname': 'server3.nordvpn.com', 'ip': '10.0.0.3', 'country': 'Canada', 'city': 'Toronto', 'load': 5, 'public_key': 'key3'},
        {'hostname': 'server4.nordvpn.com', 'ip': '10.0.0.4', 'country': 'Germany', 'city': 'Berlin', 'load': 15, 'public_key': 'key4'},
    ]
    
    for server in servers:
        db_client.cursor.execute(
            'INSERT INTO servers (hostname, ip, country, city, load, public_key) VALUES (?, ?, ?, ?, ?, ?)',
            (server['hostname'], server['ip'], server['country'], server['city'], server['load'], server['public_key'])
        )
    db_client.conn.commit()
    
    # Test getting all servers
    all_servers = get_best_servers(db_path=db_client.db_path, limit=10)
    assert len(all_servers) == 4
    assert all_servers[0].hostname == 'server3.nordvpn.com'  # Should be first due to lowest load
    
    # Test filtering by country
    us_servers = get_best_servers(country='United States', db_path=db_client.db_path)
    assert len(us_servers) == 2
    assert all(s.country == 'United States' for s in us_servers)
    
    # Test limiting the result count
    limited_servers = get_best_servers(db_path=db_client.db_path, limit=2)
    assert len(limited_servers) == 2
    assert limited_servers[0].load == 5  # Lowest load first
    
    # Test max_load filter
    low_load_servers = get_best_servers(db_path=db_client.db_path, max_load=15)
    assert len(low_load_servers) == 2
    assert all(s.load < 15 for s in low_load_servers)

def test_check_database_status(config_manager):
    """Test checking if the database exists and has servers"""
    with patch('models.database_management.DatabaseClient') as mock_db_class:
        # Mock instance of DatabaseClient
        mock_db = MagicMock()
        mock_db_class.return_value.__enter__.return_value = mock_db
        
        # Test with a database that has servers
        mock_db.cursor.fetchone.return_value = (5,)
        with patch('pathlib.Path.exists', return_value=True):
            assert check_database_status(config_manager) is True
        
        # Test with an empty database
        mock_db.cursor.fetchone.return_value = (0,)
        with patch('pathlib.Path.exists', return_value=True):
            assert check_database_status(config_manager) is False
        
        # Test with a non-existent database
        with patch('pathlib.Path.exists', return_value=False):
            assert check_database_status(config_manager) is False
        
        # Test with a database error
        mock_db_class.return_value.__enter__.side_effect = Exception("Database Error")
        assert check_database_status(config_manager) is False

def test_retry_mechanism():
    """Test that the server update process includes retry mechanisms for temporary failures"""
    # This test will verify that the retry decorator is applied to update functions
    
    # Create a mock config manager
    config_manager = MagicMock(spec=ConfigManager)
    config_manager.get.return_value = "/tmp/test_db.db"
    
    # Create a mock API client that fails initially but succeeds on retry
    mock_client = MagicMock(spec=WireGuardClient)
    
    # Set up a side effect that fails twice, then succeeds
    fails_remaining = [2]  # Use a list so we can modify it in the inner function
    
    def side_effect(*args, **kwargs):
        if fails_remaining[0] > 0:
            fails_remaining[0] -= 1
            raise ConnectionError("Temporary network failure")
        # After failures, return some mock data
        return [ServerDBRecord(
            hostname=f'server{i}.nordvpn.com',
            ip=f'10.0.0.{i}',
            country='United States',
            city='New York',
            load=10,
            public_key=f'key{i}'
        ) for i in range(1, 4)]
    
    mock_client.get_servers.side_effect = side_effect
    mock_client.export_to_csv.return_value = "/tmp/mock_servers.csv"
    
    # Apply the mocks and run the test
    with patch('models.database_management.WireGuardClient', return_value=mock_client):
        with patch('time.sleep'):  # Skip sleep calls
            with patch('models.database_management.tqdm'):  # Skip progress bars
                with patch('pathlib.Path.unlink'):  # Skip file deletion
                    with patch('models.database_management.DatabaseClient'):
                        # Should succeed after retries
                        try:
                            init_database(limit=3, config_manager=config_manager)
                            # If we get here, retry worked - the test passes
                            assert fails_remaining[0] == 0
                            assert mock_client.get_servers.call_count == 3  # Initial + 2 retries
                        except SystemExit:
                            pytest.fail("Should not have exited - retry should have succeeded") 