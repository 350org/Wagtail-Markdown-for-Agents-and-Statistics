"""A rebound backend must permit recovery without reading/deleting its old keys."""

import pytest
from django.core.files.storage import storages
from django.core.management import call_command

from tests import test_writer
from tests.test_writer import read
from wagtail_markdown_agents.models import ExportArtifact, ExportFile

pytestmark = pytest.mark.django_db(transaction=True)
setup = test_writer.setup


@pytest.mark.parametrize("force", [False, True])
def test_reconfigured_storage_falls_back_and_regenerates(setup, settings, client, force):
    writer, storage, site, page = setup
    old = writer.generate(page)
    settings.STORAGES = {
        **settings.STORAGES,
        "exports": {
            "BACKEND": "tests.storage_backend.RemoteStorage",
            "OPTIONS": {"region": "new-region"},
        },
    }
    rebound = storages["exports"]
    rebound.files[old.file.storage_key] = b"Unrelated object"
    response = client.get("/article/?output_format=md", HTTP_HOST="example.org")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert client.get("/markdown/article.md", HTTP_HOST="example.org").status_code == 404
    assert not writer.exists(old.logical_path)
    call_command("agentmd_generate", site=site.hostname, force=force)
    current = ExportArtifact.objects.get(page_id=page.pk)
    assert current.file_id != old.file_id
    assert "Published" in read(writer, current.logical_path)
    assert writer.exists("example.org/manifest.json")
    assert rebound.files[old.file.storage_key] == b"Unrelated object"
    assert old.file.storage_key in storage.files
    assert ExportFile.objects.get(pk=old.file_id).cleanup_pending
