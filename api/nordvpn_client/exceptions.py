class NordVPNError(Exception):
    """Base exception for NordVPN client errors"""
    pass

class APIError(NordVPNError):
    """Raised when API request fails"""
    pass

class DataValidationError(NordVPNError):
    """Raised when server response data is invalid"""
    pass
