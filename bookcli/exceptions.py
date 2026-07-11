"""Custom exceptions for BookCLI."""


class BookCLIError(Exception):
    """Base exception for BookCLI."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderError(BookCLIError):
    """Raised when an API request to a provider fails or times out."""
    pass


class DownloadError(BookCLIError):
    """Raised when downloading a file fails, is interrupted, or checksum fails."""
    pass


class ConfigError(BookCLIError):
    """Raised when configuration is invalid or cannot be saved."""
    pass


class DatabaseError(BookCLIError):
    """Raised when a database query or migration fails."""
    pass


class BookNotFoundError(BookCLIError):
    """Raised when a specific book or file cannot be found in search results, database, or disk."""
    pass
