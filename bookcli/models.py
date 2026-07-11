"""Data models for BookCLI."""

from typing import List, Optional
from pydantic import BaseModel, Field


class BookMetadata(BaseModel):
    """Pydantic model representing normalized book metadata across all providers."""
    id: str = Field(description="Unique identifier, e.g., 'gutenberg:1234' or 'google:abcde'")
    title: str = Field(description="The primary title of the book")
    subtitle: Optional[str] = Field(default=None, description="Subtitle if available")
    authors: List[str] = Field(default_factory=list, description="List of author names")
    description: Optional[str] = Field(default=None, description="Synopsis or description of the book")
    language: Optional[str] = Field(default=None, description="Language code (e.g., 'en', 'fr')")
    publisher: Optional[str] = Field(default=None, description="Publisher name")
    published_year: Optional[int] = Field(default=None, description="Year of publication")
    pages: Optional[int] = Field(default=None, description="Number of pages")
    isbn: Optional[str] = Field(default=None, description="International Standard Book Number")
    cover_url: Optional[str] = Field(default=None, description="URL of the cover page image")
    download_url: Optional[str] = Field(default=None, description="Direct legal download link if available")
    source: str = Field(description="Source provider name (gutenberg, google_books, etc.)")
    download_availability: bool = Field(default=False, description="Flag indicating if a legal download file is available")
    file_format: Optional[str] = Field(default=None, description="Format of the downloadable file (epub, pdf, txt, etc.)")
