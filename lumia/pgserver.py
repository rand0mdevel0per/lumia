"""
pgserver compatibility layer using testing.postgresql.

This module provides a simple interface for embedded PostgreSQL server
for testing and development purposes.
"""

import atexit
from pathlib import Path

import testing.postgresql

# Global server cache
_servers = {}


class PostgresServer:
    """Wrapper for testing.postgresql server."""

    def __init__(self, postgresql):
        self._postgresql = postgresql

    def get_uri(self) -> str:
        """Get PostgreSQL connection URI."""
        return self._postgresql.url()


def get_server(data_dir: str) -> PostgresServer:
    """
    Get or create PostgreSQL server for given data directory.

    Args:
        data_dir: Path to data directory

    Returns:
        PostgresServer instance
    """
    data_path = Path(data_dir)

    # Check if server already exists for this path
    if str(data_path) in _servers:
        return _servers[str(data_path)]

    # Create new server
    # Note: testing.postgresql creates temporary database
    # We ignore data_dir for now as testing.postgresql manages its own temp dir
    postgresql = testing.postgresql.Postgresql()

    # Register cleanup
    atexit.register(postgresql.stop)

    # Cache server
    server = PostgresServer(postgresql)
    _servers[str(data_path)] = server

    return server
