"""Local filesystem storage with safe filenames and collision handling."""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.models.domain import SavedOutput, utc_now_iso
from app.storage.base import StorageError

_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def slugify(text: str, max_len: int = 48) -> str:
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    slug = slug[:max_len].strip("-")
    return slug or "newsletter"


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def _exclusive_write(self, path: Path, content: str) -> None:
        # 'x' mode fails if the file exists, so concurrent runs never overwrite each other.
        with open(path, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(content)

    def save(self, *, run_id: str, title: str, html: str, markdown: str) -> SavedOutput:
        if not _RUN_ID.match(run_id):
            raise StorageError("Invalid run id for storage.")
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not create output directory: {exc.strerror or exc}") from exc

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}-{slugify(title)}-{run_id[:8]}"
        for attempt in range(50):
            stem = base if attempt == 0 else f"{base}-{attempt}"
            html_path = self.root / f"{stem}.html"
            md_path = self.root / f"{stem}.md"
            if html_path.exists() or md_path.exists():
                continue
            try:
                self._exclusive_write(html_path, html)
            except FileExistsError:
                continue
            except OSError as exc:
                raise StorageError(f"Could not write HTML file: {exc.strerror or exc}") from exc
            try:
                self._exclusive_write(md_path, markdown)
            except FileExistsError:
                html_path.unlink(missing_ok=True)
                continue
            except OSError as exc:
                html_path.unlink(missing_ok=True)
                raise StorageError(f"Could not write Markdown file: {exc.strerror or exc}") from exc
            return SavedOutput(
                html_path=str(html_path),
                markdown_path=str(md_path),
                html_filename=html_path.name,
                markdown_filename=md_path.name,
                saved_at=utc_now_iso(),
            )
        raise StorageError("Could not find a free filename after 50 attempts.")

    def _safe_artifact_path(self, path: str) -> Path:
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("File is outside the output directory.") from exc
        if candidate.suffix not in (".html", ".md"):
            raise StorageError("Unsupported output file type.")
        return candidate

    def resolve(self, path: str) -> Path:
        candidate = self._safe_artifact_path(path)
        if not candidate.is_file():
            raise StorageError("File not found.")
        if not os.access(candidate, os.R_OK):
            raise StorageError("File is not readable.")
        return candidate

    def delete(self, path: str) -> bool:
        candidate = self._safe_artifact_path(path)
        if not candidate.exists():
            return False
        if not candidate.is_file():
            raise StorageError("Output path is not a file.")
        try:
            candidate.unlink()
        except OSError as exc:
            raise StorageError(f"Could not delete output file: {exc.strerror or exc}") from exc
        return True
