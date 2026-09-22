"""Regression tests from the storage review: failures, query budgets and IO locks."""

import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch

import pytest
from django.db import OperationalError, close_old_connections, connection
from django.test.utils import CaptureQueriesContext
from sandbox.testapp.models import ArticlePage
from wagtail.models import Page, PageViewRestriction

from tests import test_writer
from tests.test_writer import read
from wagtail_markdown_agents.export.writer import FileWriter, StaleBuild
from wagtail_markdown_agents.models import ExportArtifact

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup


def test_post_commit_lookup_failure_preserves_success_and_runs_cleanup(setup, monkeypatch, caplog):
    writer, storage, site, page = setup
    old = writer.generate(page)
    original = writer._published

    def fail_lookup(record):
        with patch.object(
            Page.objects, "filter", side_effect=OperationalError("lookup unavailable")
        ):
            original(record)

    monkeypatch.setattr(writer, "_published", fail_lookup)
    record = writer.publish(writer.begin(page), "Replacement")
    assert ExportArtifact.objects.get(pk=record.pk).file_id != old.file_id
    assert storage.files[record.file.storage_key] == b"Replacement"
    assert old.file.storage_key not in storage.files
    assert "lookup unavailable" in caplog.text


def test_builtin_state_queries_do_not_grow_per_page(setup):
    writer, storage, site, page = setup
    # Warm Wagtail's content-type and site caches before comparing query budgets.
    writer.generate(page, depends_on_site=True)
    counts = []
    for size in (1, 15):
        if size > 1:
            for number in range(14):
                sibling = site.root_page.add_child(
                    instance=ArticlePage(
                        title=f"Page {number}",
                        slug=f"page-{number}",
                        body=[("paragraph", "<p>Public</p>")],
                    )
                )
                sibling.save_revision().publish()
        record = writer.generate(page, depends_on_site=True)
        with CaptureQueriesContext(connection) as queries:
            read(writer, record.logical_path)
        counts.append(len(queries))
    assert counts[1] <= counts[0] + 2, counts
    assert counts[1] <= 45, counts


def test_leaf_publication_does_not_scan_site_without_dependents(setup, monkeypatch):
    writer, storage, site, page = setup
    from wagtail_markdown_agents.export import writer as module

    def unexpected(*args):
        pytest.fail("A leaf publication without dependents should not scan the site")

    monkeypatch.setattr(module, "site_state", unexpected)
    writer.generate(page)


def run_in_worker(fn):
    close_old_connections()
    try:
        return fn()
    finally:
        close_old_connections()


@pytest.mark.parametrize("operation", ["aggregate", "cleanup"])
def test_slow_storage_io_does_not_block_unrelated_readers(setup, operation):
    writer, storage, site, page = setup
    record = writer.generate(page)
    started, release = threading.Event(), threading.Event()

    def pause():
        started.set()
        assert release.wait(10)

    if operation == "aggregate":
        storage.after_save = pause

        def work():
            return FileWriter().update_aggregate(
                site.pk, "example.org/manifest.json", lambda previous: "{}"
            )
    else:
        old_delete = storage.delete

        def slow_delete(key):
            pause()
            return old_delete(key)

        storage.delete = slow_delete
        # Replacing an aggregate retires its old object, then runs cleanup.
        writer.update_aggregate(site.pk, "example.org/manifest.json", lambda previous: "old")

        def work():
            return FileWriter().update_aggregate(
                site.pk, "example.org/manifest.json", lambda previous: "new"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        upload = pool.submit(run_in_worker, work)
        try:
            assert started.wait(10)
            reader = pool.submit(run_in_worker, lambda: read(FileWriter(), record.logical_path))
            assert "Published" in reader.result(timeout=3)
        finally:
            release.set()
        upload.result(timeout=10)


def test_aggregate_retry_never_retries_a_revocation(setup):
    writer, storage, site, page = setup
    calls = []

    def update(previous):
        calls.append(previous)
        return "Must not be retried after withdrawal"

    storage.after_save = lambda: writer.delete_page(page.pk, site_id=site.pk)
    with pytest.raises(StaleBuild):
        writer.update_aggregate(site.pk, "example.org/manifest.json", update)
    assert calls == [None]
    assert not writer.exists("example.org/manifest.json")


def test_reader_rechecks_revocation_after_storage_open(setup, monkeypatch):
    writer, storage, site, page = setup
    record = writer.generate(page)
    original = writer._open_file
    streams = []

    def revoke_while_opening(file):
        with original(file) as source:
            stream = BytesIO(source.read())
        streams.append(stream)
        PageViewRestriction.objects.create(page=page, restriction_type="login")
        return stream

    monkeypatch.setattr(writer, "_open_file", revoke_while_opening)
    with pytest.raises(FileNotFoundError):
        writer.open(record.logical_path)
    assert streams and all(stream.closed for stream in streams)


def test_aggregate_contention_retries_are_bounded(setup):
    writer, storage, site, page = setup
    calls = []

    def competing_update():
        storage.after_save = None
        try:
            writer.update_aggregate(site.pk, "example.org/other.json", lambda previous: "{}")
        finally:
            storage.after_save = competing_update

    storage.after_save = competing_update

    def update(previous):
        calls.append(previous)
        return "candidate"

    with pytest.raises(StaleBuild):
        writer.update_aggregate(site.pk, "example.org/manifest.json", update)
    assert len(calls) == 3
    assert not writer.exists("example.org/manifest.json")
    assert not any(value == b"candidate" for value in storage.files.values())
