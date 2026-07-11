"""Unit tests for the async downloader service."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from bookcli.downloader import download_file, calculate_sha256
from bookcli.exceptions import DownloadError


@pytest.fixture
def temp_dir():
    """Provides a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_calculate_sha256(temp_dir):
    """Test SHA256 calculation for a file."""
    test_file = os.path.join(temp_dir, "test.txt")
    # Open in binary mode to write exact bytes (avoid newline translation on Windows)
    with open(test_file, "wb") as f:
        f.write(b"Hello, BookCLI!")
    
    checksum = calculate_sha256(test_file)
    assert len(checksum) == 64
    assert checksum == "b3a042dd74cd01d169e6350c34f110b59f8b5ea011d90c683f973d1435e18097"


@pytest.mark.asyncio
async def test_download_file_success(temp_dir):
    """Test successful download from scratch."""
    dest_path = os.path.join(temp_dir, "downloaded.txt")
    
    # Mock Response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": "15"}
    
    async def mock_aiter_bytes(chunk_size=1024):
        yield b"Hello, BookCLI!"
    mock_response.aiter_bytes = mock_aiter_bytes

    # Configure client mock context manager
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    # stream is a synchronous method returning an async context manager
    mock_client.stream = MagicMock()
    
    mock_stream = AsyncMock()
    mock_stream.__aenter__.return_value = mock_response
    mock_client.stream.return_value = mock_stream

    with patch("httpx.AsyncClient", return_value=mock_client):
        checksum = await download_file("http://example.com/file", dest_path)
        
        assert os.path.exists(dest_path)
        with open(dest_path, "rb") as f:
            assert f.read() == b"Hello, BookCLI!"
        assert checksum == "b3a042dd74cd01d169e6350c34f110b59f8b5ea011d90c683f973d1435e18097"


@pytest.mark.asyncio
async def test_download_file_resume(temp_dir):
    """Test resuming a download using Range headers."""
    dest_path = os.path.join(temp_dir, "resume.txt")
    part_path = dest_path + ".part"
    
    # Write initial bytes
    with open(part_path, "wb") as f:
        f.write(b"Hello")

    # Mock Response
    mock_response = MagicMock()
    mock_response.status_code = 206
    mock_response.headers = {"content-length": "10"}
    
    async def mock_aiter_bytes(chunk_size=1024):
        yield b", BookCLI!"
    mock_response.aiter_bytes = mock_aiter_bytes

    # Configure client mock
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    # stream is a synchronous method returning an async context manager
    mock_client.stream = MagicMock()
    
    mock_stream = AsyncMock()
    mock_stream.__aenter__.return_value = mock_response
    mock_client.stream.return_value = mock_stream

    with patch("httpx.AsyncClient", return_value=mock_client):
        checksum = await download_file("http://example.com/file", dest_path)
        
        # Verify range headers were sent
        call_args = mock_client.stream.call_args
        headers = call_args[1]["headers"]
        assert headers["Range"] == "bytes=5-"
        
        assert os.path.exists(dest_path)
        with open(dest_path, "rb") as f:
            assert f.read() == b"Hello, BookCLI!"


@pytest.mark.asyncio
async def test_download_file_failed_http_status(temp_dir):
    """Test exception raised on server error response."""
    dest_path = os.path.join(temp_dir, "failed.txt")
    
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    # stream is a synchronous method returning an async context manager
    mock_client.stream = MagicMock()
    
    mock_stream = AsyncMock()
    mock_stream.__aenter__.return_value = mock_response
    mock_client.stream.return_value = mock_stream

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(DownloadError) as exc_info:
            await download_file("http://example.com/404", dest_path)
        assert "status code 404" in str(exc_info.value)
