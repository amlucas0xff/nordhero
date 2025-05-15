import sys
import logging
import sqlite3
import csv
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from time import sleep
from tqdm import tqdm

from models.config_management import ConfigManager
from models.data_models import ServerDBRecord
from api.nordvpn_client.wireguard import WireGuardClient

# Logger
logger = logging.getLogger(__name__)

# --- Added DatabaseClient class definition ---
class DatabaseClient:
    """Client for managing SQLite database operations"""

    def __init__(self, db_path: str = "./db/servers.db"):
        """Initialize database connection"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def connect(self):
        """Create database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    def init_db(self):
        """Initialize database schema"""
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    hostname TEXT PRIMARY KEY,
                    ip TEXT NOT NULL,
                    country TEXT NOT NULL,
                    city TEXT NOT NULL,
                    load INTEGER NOT NULL,
                    public_key TEXT NOT NULL,
                    UNIQUE(hostname)
                )
            ''')

            # Create indexes for common queries
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_country ON servers(country)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_city ON servers(city)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_load ON servers(load)')

            self.conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Schema initialization failed: {e}")
            raise

    def _row_to_server_record(self, row: tuple, columns: List[str]) -> ServerDBRecord:
        """Convert a database row to a ServerDBRecord Pydantic model

        Args:
            row: Database row as tuple
            columns: Column names corresponding to the values in the row

        Returns:
            ServerDBRecord instance with data from the row
        """
        return ServerDBRecord(**{key: value for key, value in zip(columns, row)})

    def import_csv(self, csv_path: str, progress_callback=None):
        """Import server data from CSV file"""
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        try:
            # Clear existing data
            self.cursor.execute('DELETE FROM servers')

            with open(csv_path, 'r') as f:
                csv_reader = csv.DictReader(f)

                # Prepare bulk insert
                records = []
                for row in csv_reader:
                    # Create a ServerDBRecord to validate the data
                    server_record = ServerDBRecord(
                        hostname=row['hostname'],
                        ip=row['ip'],
                        country=row['country'],
                        city=row['city'],
                        load=int(row['load']),
                        public_key=row['public_key']
                    )
                    
                    # Convert to tuple for SQLite insert
                    records.append((
                        server_record.hostname,
                        server_record.ip,
                        server_record.country,
                        server_record.city,
                        server_record.load,
                        server_record.public_key
                    ))
                    
                    if progress_callback:
                        progress_callback(1)

                # If no progress callback was provided, do bulk insert
                if not progress_callback:
                    self.cursor.executemany(
                        'INSERT INTO servers (hostname, ip, country, city, load, public_key) VALUES (?, ?, ?, ?, ?, ?)',
                        records
                    )
                else:
                    # If progress callback exists, insert one by one to show progress
                    for record in records:
                        self.cursor.execute(
                            'INSERT INTO servers (hostname, ip, country, city, load, public_key) VALUES (?, ?, ?, ?, ?, ?)',
                            record
                        )

            self.conn.commit()
            logger.info(f"Imported {len(records)} records from {csv_path}")

        except (sqlite3.Error, csv.Error) as e:
            logger.error(f"CSV import failed: {e}")
            raise

    def get_servers(self, country: Optional[str] = None, city: Optional[str] = None, ip: Optional[str] = None, public_key: Optional[str] = None,
                   limit: Optional[int] = None) -> List[ServerDBRecord]:
        """Fetch servers with optional filters

        Args:
            country: Optional country name to filter by
            city: Optional city name to filter by
            limit: Optional maximum number of servers to return

        Returns:
            List of ServerDBRecord objects
        """
        query = 'SELECT * FROM servers'
        params = []

        # Build WHERE clause
        where_clauses = []
        if country:
            where_clauses.append('country = ?')
            params.append(country)
        if city:
            where_clauses.append('city = ?')
            params.append(city)
        if ip:
            where_clauses.append('ip = ?')
            params.append(ip)
        if public_key:
            where_clauses.append('public_key = ?')
            params.append(public_key)

        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)

        # Add limit
        if limit:
            query += ' LIMIT ?'
            params.append(limit)

        try:
            self.cursor.execute(query, params)
            columns = [col[0] for col in self.cursor.description]
            rows = self.cursor.fetchall()
            
            # Convert each row to a ServerDBRecord
            return [self._row_to_server_record(row, columns) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Query failed: {e}")
            raise
# --- End of DatabaseClient class definition ---


def get_time_ago(timestamp_str: str) -> str:
    """Convert timestamp to human readable time ago format"""
    try:
        last_update = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        diff = now - last_update

        # Convert to total seconds
        seconds = int(diff.total_seconds())

        # Define time intervals
        intervals = [
            (60 * 60 * 24 * 30, 'month'),
            (60 * 60 * 24 * 7, 'week'),
            (60 * 60 * 24, 'day'),
            (60 * 60, 'hour'),
            (60, 'minute'),
            (1, 'second')
        ]

        # Find the appropriate interval
        for seconds_in_interval, interval_name in intervals:
            if seconds >= seconds_in_interval:
                count = seconds // seconds_in_interval
                if count == 1:
                    return f"{count} {interval_name} ago"
                return f"{count} {interval_name}s ago"

        return "just now"

    except Exception:
        return "unknown"

def get_last_update_time(config_manager: ConfigManager, format_as_time_ago: bool = False) -> str:
    """Get the last database update time"""
    try:
        db_path = config_manager.get('database', 'path', 'servers.db')
        with DatabaseClient(db_path=db_path) as db:
            db.cursor.execute('SELECT value FROM metadata WHERE key = ?', ('last_update',))
            result = db.cursor.fetchone()
            if not result:
                return "Never"

            if format_as_time_ago:
                return get_time_ago(result[0])
            return result[0]
    except:
        return "Never"

def init_database(limit: int = 0, config_manager: ConfigManager = None) -> Tuple[int, int]:
    """Initialize database with server data from API"""
    try:
        print("\nRetrieving server data from NordVPN API...")
        client = WireGuardClient()

        # Create a progress bar for API retrieval
        with tqdm(total=100, desc="Fetching servers", bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt}') as pbar:
            servers = client.get_servers(limit=limit)
            # Simulate progress for API call
            for i in range(100):
                sleep(0.02)  # Small delay to show progress
                pbar.update(1)

        # Generate temporary CSV file
        csv_path = client.export_to_csv(servers)
        total_servers = len(servers)

        try:
            db_path = config_manager.get('database', 'path', 'servers.db')
            with DatabaseClient(db_path=db_path) as db:
                # Get previous count if database exists
                prev_count = 0
                try:
                    db.cursor.execute('SELECT COUNT(*) FROM servers')
                    prev_count = db.cursor.fetchone()[0]
                except:
                    pass

                db.init_db()

                # Create a progress bar for database operations
                print("\nUpdating database...")
                with tqdm(total=total_servers, desc="Importing servers",
                         bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} servers') as pbar:
                    db.import_csv(csv_path, progress_callback=lambda x: pbar.update(1))

                # Get new count
                db.cursor.execute('SELECT COUNT(*) FROM servers')
                new_count = db.cursor.fetchone()[0]

                # Store last update time in database
                db.cursor.execute('''CREATE TABLE IF NOT EXISTS metadata
                                   (key TEXT PRIMARY KEY, value TEXT)''')
                db.cursor.execute('INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)',
                                ('last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                db.conn.commit()

            logger.info(f"Database initialized at: {db_path} with {len(servers)} servers")
            return new_count, prev_count

        finally:
            # Clean up the temporary CSV file
            try:
                Path(csv_path).unlink()
                logger.debug(f"Removed temporary CSV file: {csv_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary CSV file: {e}")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)


def check_database_status(config_manager: ConfigManager) -> bool:
    """Check if database exists and has servers"""
    try:
        db_path = Path(config_manager.get('database', 'path', 'servers.db'))
        if not db_path.exists():
            return False

        with DatabaseClient(db_path=db_path) as db:
            db.cursor.execute('SELECT COUNT(*) FROM servers')
            count = db.cursor.fetchone()[0]
            return count > 0
    except:
        return False

def get_best_servers(country: str = None, limit: int = 5, max_load: int = 50, show_all: bool = False, db_path: str = None) -> List[ServerDBRecord]:
    """Get best servers based on criteria
    
    Args:
        country: Optional country filter
        limit: Maximum number of servers to return
        max_load: Maximum server load to consider
        show_all: If True, ignore load filter
        db_path: Optional database path
        
    Returns:
        List of ServerDBRecord objects, sorted by load
    """
    try:
        with DatabaseClient(db_path=db_path) as db:
            # Define sorting order for results (ORDER BY load ASC)
            query = 'SELECT * FROM servers'
            params = []
            
            # Build WHERE clause if country is specified
            where_clauses = []
            if country:
                where_clauses.append('country = ?')
                params.append(country)
                
            # Add load filter if needed
            if not show_all and max_load > 0:
                where_clauses.append('load < ?')
                params.append(max_load)
                
            if where_clauses:
                query += ' WHERE ' + ' AND '.join(where_clauses)
                
            # Add sorting and limit
            query += ' ORDER BY load ASC'
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
                
            # Execute query
            db.cursor.execute(query, params)
            columns = [col[0] for col in db.cursor.description]
            rows = db.cursor.fetchall()
            
            # Convert each row to a ServerDBRecord
            return [db._row_to_server_record(row, columns) for row in rows]
            
    except Exception as e:
        logger.error(f"Failed to get best servers: {e}")
        return []