"""13. Successful simulated output saving  14. File-write failure handling"""

from pathlib import Path

import pytest

from app.agent.runner import RunOptions, run_newsletter_agent
from app.models.domain import RunStatus
from app.storage.base import StorageError
from app.storage.local import LocalFileStorage, slugify
from app.tools.newsletter_renderer import render_newsletter, save_newsletter
from tests.conftest import GOAL
from tests.test_writing import _draft


def test_save_creates_unique_files_and_handles_collisions(tmp_path, fixture_articles):
    storage = LocalFileStorage(tmp_path / "nested" / "out")  # missing directory is created
    rendered = render_newsletter(_draft(fixture_articles[:3]))
    a = save_newsletter(rendered, run_id="abc123", title="AI Weekly: ../../etc/passwd", storage=storage)
    b = save_newsletter(rendered, run_id="abc123", title="AI Weekly: ../../etc/passwd", storage=storage)
    assert a.html_filename != b.html_filename  # collision → suffix
    for out in (a, b):
        p = Path(out.html_path)
        assert p.parent == storage.root and p.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
        assert Path(out.markdown_path).exists()
    assert ".." not in a.html_filename and "/" not in a.html_filename


def test_slugify_and_resolve_prevent_traversal(tmp_path):
    assert slugify("../../Évil <name>") == "evil-name"
    assert slugify("") == "newsletter"
    storage = LocalFileStorage(tmp_path / "out")
    outside = tmp_path / "secret.html"
    outside.write_text("x")
    with pytest.raises(StorageError):
        storage.resolve(str(outside))
    with pytest.raises(StorageError):
        storage.resolve(str(storage.root / ".." / "secret.html"))
    with pytest.raises(StorageError):
        storage.save(run_id="../x", title="t", html="h", markdown="m")


def test_invalid_html_is_never_saved(tmp_path, fixture_articles):
    rendered = render_newsletter(_draft(fixture_articles[:1]))
    rendered.validation.valid = False
    rendered.validation.errors = ["broken"]
    with pytest.raises(ValueError):
        save_newsletter(rendered, run_id="r1", title="t", storage=LocalFileStorage(tmp_path))


class FailingStorage(LocalFileStorage):
    def _exclusive_write(self, path, content):
        raise PermissionError(13, "Permission denied")


def test_write_failure_cleans_up_and_raises(tmp_path, fixture_articles):
    storage = FailingStorage(tmp_path)
    with pytest.raises(StorageError, match="Permission denied"):
        storage.save(run_id="r1", title="t", html="<html></html>", markdown="m")
    assert list(tmp_path.iterdir()) == []


def test_workflow_reports_write_failure_honestly(make_services, tmp_path):
    result = run_newsletter_agent(
        GOAL, RunOptions(deterministic=True,
                         services_factory=lambda r: make_services(r, storage=FailingStorage(tmp_path / "o")))
    )
    assert result.status == RunStatus.FAILED
    assert "Could not write" in (result.error or "")
    assert result.html_path is None
    assert any(t.tool.startswith("newsletter_storage") and t.status == "error" for t in result.tool_calls)


def test_successful_run_saves_and_labels_simulated_delivery(make_services, settings):
    result = run_newsletter_agent(GOAL, RunOptions(deterministic=True, services_factory=make_services))
    assert result.status == RunStatus.COMPLETED
    assert Path(result.html_path).is_file() and Path(result.markdown_path).is_file()
    assert Path(result.html_path).parent == Path(settings.output_dir).resolve()
    assert result.delivery_mode == "simulated" and "NOT sent" in result.delivery_note
    assert any("No email was sent" in e.message for e in result.execution_log)


def test_storage_delete_is_bounded_and_idempotent(tmp_path):
    storage = LocalFileStorage(tmp_path / "out")
    storage.root.mkdir(parents=True)
    inside = storage.root / "issue.html"
    inside.write_text("newsletter", encoding="utf-8")
    assert storage.delete(str(inside)) is True
    assert storage.delete(str(inside)) is False
    outside = tmp_path / "outside.html"
    outside.write_text("keep", encoding="utf-8")
    with pytest.raises(StorageError):
        storage.delete(str(outside))
    assert outside.exists()
