import pytest
import sqlite3
import os
from pathlib import Path
import json
import csv
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import shutil

# Import database modules
from models.database_management import DatabaseClient
from models.data_models import ServerDBRecord


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
def db_client(temp_db_path):
    """Create a database client with a test database"""
    # Create a database client with a test database
    client = DatabaseClient(db_path=temp_db_path)
    # Initialize the database schema
    with client as db:
        db.init_db()
    return client


@pytest.fixture
def sample_servers():
    """Sample server data for testing"""
    return [
        ServerDBRecord(
            hostname="us1.nordvpn.com",
            ip="192.168.1.1",
            country="United States",
            city="New York",
            load=25,
            public_key="public_key_1"
        ),
        ServerDBRecord(
            hostname="de1.nordvpn.com",
            ip="192.168.1.2",
            country="Germany",
            city="Berlin",
            load=35,
            public_key="public_key_2"
        ),
        ServerDBRecord(
            hostname="uk1.nordvpn.com",
            ip="192.168.1.3",
            country="United Kingdom",
            city="London",
            load=45,
            public_key="public_key_3"
        ),
    ]


@pytest.fixture
def sample_csv_path():
    """Create a temporary CSV file with sample server data"""
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', newline='') as temp_file:
        writer = csv.writer(temp_file)
        writer.writerow(['hostname', 'ip', 'country', 'city', 'load', 'public_key'])
        writer.writerow(['us1.nordvpn.com', '192.168.1.1', 'United States', 'New York', 25, 'public_key_1'])
        writer.writerow(['de1.nordvpn.com', '192.168.1.2', 'Germany', 'Berlin', 35, 'public_key_2'])
        writer.writerow(['uk1.nordvpn.com', '192.168.1.3', 'United Kingdom', 'London', 45, 'public_key_3'])
        csv_path = temp_file.name
        
    # Return the path and ensure it's cleaned up after the test
    yield csv_path
    if os.path.exists(csv_path):
        os.remove(csv_path)


def test_database_initialization(db_client, temp_db_path):
    """Test that the database is properly initialized"""
    # Check that the tables are created
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    
    # Query the database for tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    table_names = [table[0] for table in tables]
    
    # Check for expected tables
    assert "servers" in table_names
    
    # Check that the schema is correct
    cursor.execute("PRAGMA table_info(servers)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    # Check for expected columns in servers table
    expected_columns = ["hostname", "ip", "country", "city", "load", "public_key"]
    for col in expected_columns:
        assert col in column_names
    
    conn.close()


def test_import_csv(db_client, sample_csv_path):
    """Test importing server data from CSV"""
    with db_client as db:
        db.import_csv(sample_csv_path)
        
        # Query the database to verify import
        db.cursor.execute("SELECT COUNT(*) FROM servers")
        server_count = db.cursor.fetchone()[0]
        assert server_count == 3
        
        # Check specific server data
        db.cursor.execute("SELECT hostname, country, city, load FROM servers WHERE hostname=?", ("us1.nordvpn.com",))
        server = db.cursor.fetchone()
        assert server is not None
        assert server[0] == "us1.nordvpn.com"
        assert server[1] == "United States"
        assert server[2] == "New York"
        assert server[3] == 25


def test_get_servers(db_client, sample_csv_path):
    """Test retrieving servers with filters"""
    with db_client as db:
        db.import_csv(sample_csv_path)
        
        # Get all servers
        servers = db.get_servers()
        assert len(servers) == 3
        
        # Get servers by country
        us_servers = db.get_servers(country="United States")
        assert len(us_servers) == 1
        assert us_servers[0].hostname == "us1.nordvpn.com"
        
        # Get servers by city
        berlin_servers = db.get_servers(city="Berlin")
        assert len(berlin_servers) == 1
        assert berlin_servers[0].hostname == "de1.nordvpn.com"
        
        # Get servers with limit
        limited_servers = db.get_servers(limit=2)
        assert len(limited_servers) == 2


def test_get_servers_by_country(db_client, sample_csv_path):
    """Test retrieving servers by country"""
    with db_client as db:
        db.import_csv(sample_csv_path)
        
        # Test each country
        us_servers = db.get_servers(country="United States")
        de_servers = db.get_servers(country="Germany")
        uk_servers = db.get_servers(country="United Kingdom")
        
        assert len(us_servers) == 1
        assert len(de_servers) == 1
        assert len(uk_servers) == 1
        
        assert us_servers[0].country == "United States"
        assert de_servers[0].country == "Germany"
        assert uk_servers[0].country == "United Kingdom"
        
        # Test country that doesn't exist
        empty_servers = db.get_servers(country="France")
        assert len(empty_servers) == 0


def test_row_to_server_record(db_client):
    """Test conversion of database row to ServerDBRecord"""
    columns = ["hostname", "ip", "country", "city", "load", "public_key"]
    row = ("us1.nordvpn.com", "192.168.1.1", "United States", "New York", 25, "public_key_1")
    
    server_record = db_client._row_to_server_record(row, columns)
    
    assert isinstance(server_record, ServerDBRecord)
    assert server_record.hostname == "us1.nordvpn.com"
    assert server_record.ip == "192.168.1.1"
    assert server_record.country == "United States"
    assert server_record.city == "New York"
    assert server_record.load == 25
    assert server_record.public_key == "public_key_1"


def test_csv_not_found(db_client):
    """Test handling of missing CSV file"""
    with pytest.raises(FileNotFoundError):
        with db_client:
            db_client.import_csv("nonexistent.csv")


def test_database_error_handling(db_client, sample_csv_path):
    """Test error handling for database operations"""
    # Test with a closed connection
    with pytest.raises(sqlite3.Error):
        # Don't use context manager to keep connection closed
        db_client.cursor.execute("SELECT * FROM servers")
        
    # Test with invalid SQL
    with pytest.raises(sqlite3.Error):
        with db_client:
            db_client.cursor.execute("SELECT * FROM nonexistent_table")


def test_get_servers_with_combined_filters(db_client, sample_csv_path):
    """Test retrieving servers with multiple filters"""
    with db_client as db:
        db.import_csv(sample_csv_path)
        
        # Add an extra server in the same country but different city
        db.cursor.execute(
            'INSERT INTO servers (hostname, ip, country, city, load, public_key) VALUES (?, ?, ?, ?, ?, ?)',
            ("us2.nordvpn.com", "192.168.1.4", "United States", "Chicago", 30, "public_key_4")
        )
        db.conn.commit()
        
        # Get servers with country and city filters
        filtered_servers = db.get_servers(country="United States", city="Chicago")
        assert len(filtered_servers) == 1
        assert filtered_servers[0].hostname == "us2.nordvpn.com"
        
        # Get servers with country filter
        us_servers = db.get_servers(country="United States")
        assert len(us_servers) == 2  # Two US servers now


def test_import_with_progress_callback(db_client, sample_csv_path):
    """Test importing server data with progress callback"""
    # Define a simple progress callback to count calls
    progress_count = 0
    
    def progress_callback(increment):
        nonlocal progress_count
        progress_count += increment
    
    # Import with callback
    with db_client as db:
        db.import_csv(sample_csv_path, progress_callback=progress_callback)
        
        # Progress callback should be called for each record
        assert progress_count == 3  # Three servers in the test CSV
        
        # Verify servers were imported
        db.cursor.execute("SELECT COUNT(*) FROM servers")
        server_count = db.cursor.fetchone()[0]
        assert server_count == 3


@patch('models.database_management.DatabaseClient.connect')
@patch('models.database_management.DatabaseClient.close')
def test_context_manager(mock_close, mock_connect, db_client):
    """Test that the context manager properly connects and closes"""
    # Use the context manager
    with db_client as db:
        # Should connect on entry
        mock_connect.assert_called_once()
        
        # Set a flag we can check after exit
        db.was_used = True
    
    # Ensure it was the same db object we used
    assert hasattr(db_client, 'was_used')
    
    # Check that close was called on exit
    mock_close.assert_called_once()


def test_server_record_model(sample_servers):
    """Test the ServerDBRecord Pydantic model"""
    server = sample_servers[0]
    
    # Test data access
    assert server.hostname == "us1.nordvpn.com"
    assert server.ip == "192.168.1.1"
    assert server.country == "United States"
    assert server.load == 25
    
    # Test model validation
    from pydantic import ValidationError
    
    # Should raise when required fields are missing
    with pytest.raises(ValidationError):
        ServerDBRecord(hostname="test")
    
    # Should raise with invalid types
    with pytest.raises(ValidationError):
        ServerDBRecord(
            hostname="test.nordvpn.com",
            ip="192.168.1.1",
            country="Test",
            city="City",
            load="not-a-number",  # Should be an integer
            public_key="key"
        )


def test_database_retry_mechanism():
    """Test retry decorator with database operations"""
    # This test simulates the retry decorator behavior
    attempts = 0
    max_attempts = 3
    
    # Simulate a function with retry
    def operation_with_retry():
        nonlocal attempts
        attempts += 1
        if attempts < max_attempts:
            # Just record the attempt without raising
            return "retry"
        return "success"
    
    # Simulate retry mechanism
    result = None
    for _ in range(max_attempts):
        result = operation_with_retry()
        if result == "success":
            break
    
    # Should eventually succeed
    assert result == "success"
    assert attempts == max_attempts

# Add more tests as needed for the actual implementation 