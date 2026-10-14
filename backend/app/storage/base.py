"""Storage interface for generated newsletters.

`LocalFileStorage` is used in development; another backend (S3, GCS, a
database) can be added by implementing the same protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.models.domain import SavedOutput


class StorageError(Exception):
    pass


class NewsletterStorage(Protocol):
    def save(self, *, run_id: str, title: str, html: str, markdown: str) -> SavedOutput: ...

    def resolve(self, path: str) -> Path:
        """Return a readable path for a previously saved file, enforcing that it
        lives inside the storage root. Raises StorageError otherwise."""

    def delete(self, path: str) -> bool:
        """Delete one stored newsletter artifact. Return False when it no longer exists."""
