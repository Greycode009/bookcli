"""Downloader service for fetching files asynchronously with resume capability and Rich progress."""

import os
import hashlib
import time
import logging
from typing import Optional
import httpx
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn
)

from bookcli.exceptions import DownloadError

logger = logging.getLogger(__name__)


def calculate_sha256(file_path: str) -> str:
    """Calculates the SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


async def download_file(
    url: str,
    dest_path: str,
    timeout_seconds: int = 15
) -> str:
    """Downloads a file asynchronously from a URL with resume support, showing a Rich progress bar.

    Returns:
        The SHA256 checksum of the completed file.
    """
    part_path = dest_path + ".part"
    initial_bytes = 0

    if os.path.exists(part_path):
        initial_bytes = os.path.getsize(part_path)
        logger.info("Found partial download of size %d bytes. Attempting to resume...", initial_bytes)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if initial_bytes > 0:
        headers["Range"] = f"bytes={initial_bytes}-"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 416:
                    # Range not satisfiable, might mean the file was already fully downloaded
                    # Let's delete part file and restart or just raise
                    logger.warning("Range not satisfiable (416). Restarting download.")
                    if os.path.exists(part_path):
                        os.remove(part_path)
                    initial_bytes = 0
                    # Retry without Range
                    return await download_file(url, dest_path, timeout_seconds)

                if response.status_code not in (200, 206):
                    raise DownloadError(
                        f"Server returned HTTP status code {response.status_code} for download."
                    )

                is_resume = response.status_code == 206
                total_bytes = int(response.headers.get("content-length", 0))
                
                if is_resume:
                    total_bytes += initial_bytes
                    write_mode = "ab"
                else:
                    initial_bytes = 0
                    write_mode = "wb"

                # Ensure destination directory exists
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                filename = os.path.basename(dest_path)
                
                # Setup Rich Progress bar
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    transient=True  # Clear the progress bar after completion
                ) as progress:
                    
                    task_desc = f"Downloading {filename}"
                    task_id = progress.add_task(
                        task_desc,
                        total=total_bytes,
                        completed=initial_bytes
                    )

                    with open(part_path, write_mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            progress.update(task_id, advance=len(chunk))

        # Rename part file to final file
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(part_path, dest_path)

        # Calculate Checksum
        checksum = calculate_sha256(dest_path)
        logger.info("Download completed successfully. SHA256: %s", checksum)
        return checksum

    except httpx.RequestError as e:
        logger.error("Network error during download: %s", e)
        raise DownloadError(f"Network error while downloading: {e}")
    except (IOError, OSError) as e:
        logger.error("Disk I/O error during download: %s", e)
        raise DownloadError(f"Failed to write downloaded file: {e}")
    except Exception as e:
        logger.error("Unexpected error during download: %s", e)
        raise DownloadError(f"Download failed: {e}")
