import subprocess
import logging
import sys


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Helper functions
def check_file_exists_with_sudo(file_path: str) -> bool:
    """Check if a file exists using sudo
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        bool: True if the file exists, False otherwise
    """
    try:
        result = subprocess.run(['sudo', 'test', '-f', file_path], 
                            capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking if file exists: {e}")
        return False


def handle_keyboard_interrupt(signum, frame):
    """Handle keyboard interrupt (Ctrl+C)"""
    print("\n\nExiting gracefully...")
    sys.exit(0) 