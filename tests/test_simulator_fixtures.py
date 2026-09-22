"""Run the explicit simulator corpus through real Wagtail serving and counters."""

import json
from io import StringIO
from urllib.parse import urlsplit

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from sandbox.testapp.models import ArticlePage
from sandbox.testapp.simulator_fixtures import PREVIEW_PATH, create_fixtures
from scripts import agent_simulator as sim
from scripts.traffic_simulator.planning import REQUIRED_FIXTURES
from wagtail.models import Locale, Page, PageViewRestriction, Site

from tests.test_agent_simulator import Clock, events
from wagtail_markdown_agents.models import AgentAccess, ExportArtifact, PageAgentSettings

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.export_lifecycle]
TARGET = "http://localhost"


def response_body(response):
    try:
        return b"".join(response.streaming_content) if response.streaming else response.content
    finally:
        response.close()


@pytest.fixture
def corpus(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    settings.SIMULATOR_FIXTURES_ENABLED = True
    settings.WAGTAIL_MARKDOWN_AGENTS = {"AUTO_GENERATE": False}
    settings.MIDDLEWARE = [
        "sandbox.testapp.simulator_fixtures.PublishedPreviewMiddleware",
        *settings.MIDDLEWARE,
    ]
    locale, _ = Locale.objects.get_or_create(language_code="en")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root", locale=locale)
    home = root.add_child(instance=Page(title="Fixture home", slug="fixture-home"))
    home.save_revision().publish()
    Site.objects.all().delete()
    site = Site.objects.create(hostname="localhost", port=80, root_page=home, is_default_site=True)
    Site.clear_site_root_paths_cache()
    checks = create_fixtures(site)["checks"]
    yield site, checks
    Site.clear_site_root_paths_cache()


def fetch(client, spec):
    response = client.generic(
        spec.method,
        spec.url,
        HTTP_HOST="localhost",
        HTTP_USER_AGENT=spec.ua,
        HTTP_ACCEPT=spec.accept,
    )
    return response.status_code, dict(response.items()), response_body(response)


def make_plan(client, checks):
    manifest = client.get("/markdown/manifest.json", HTTP_HOST="localhost")
    assert manifest.status_code == 200
    pages = sim.discover(
        json.loads(response_body(manifest)), TARGET, lambda spec: fetch(client, spec)[2]
    )
    return sim.build_plan(pages, TARGET, fixtures=checks, max_requests=250), pages


def test_six_fixtures_have_real_page_state_and_no_counter_increments(corpus, client):
    site, checks = corpus
    by_kind = {check["kind"]: check for check in checks}
    assert PageAgentSettings.objects.get(page_id=by_kind["excluded"]["page_id"]).excluded
    assert PageViewRestriction.objects.filter(page_id=by_kind["private-export"]["page_id"]).exists()
    for kind in ("fallback", "missing-export", "private-export", "excluded"):
        assert not ExportArtifact.objects.filter(page_id=by_kind[kind]["page_id"]).exists()
    navigation = ExportArtifact.objects.get(
        scope__site_id=site.pk, logical_path="localhost/simulator/navigation/index.md"
    )
    assert navigation.page_id is None
    plan, pages = make_plan(client, checks)
    assert {page["id"] for page in pages} == {
        by_kind["preview"]["page_id"],
        ArticlePage.objects.get(slug="public-child").pk,
    }
    assert plan["coverage"]["suite_complete"]
    assert plan["coverage"]["missing_fixtures"] == []
    before = list(AgentAccess.objects.order_by("pk").values())
    specs = [row for row in plan["requests"] if row["scenario"] in REQUIRED_FIXTURES]
    assert len(specs) == 12
    for row in specs:
        spec = sim.RequestSpec.from_dict(row)
        status, headers, body = fetch(client, spec)
        assert (
            sim.assess(spec, status, {k.lower(): v for k, v in headers.items()}, body)["outcome"]
            == "pass"
        ), row["scenario"]
        if spec.method == "HEAD":
            assert body == b""
        if spec.scenario == "navigation-index" and spec.method == "GET":
            assert b"public-child.md" in body
        assert list(AgentAccess.objects.order_by("pk").values()) == before


def test_preview_really_uses_wagtail_preview_and_never_reads_draft(corpus, client, monkeypatch):
    page = ArticlePage.objects.get(slug="preview")
    page.body = [("paragraph", "<p>UNPUBLISHED DRAFT CANARY</p>")]
    page.save_revision()
    seen = []
    original = ArticlePage.serve_preview

    def preview(self, request, mode_name):
        seen.append((self.pk, request.is_preview))
        return original(self, request, mode_name)

    monkeypatch.setattr(ArticlePage, "serve_preview", preview)
    response = client.get(
        PREVIEW_PATH + "?preview=1", HTTP_HOST="localhost", HTTP_USER_AGENT="GPTBot"
    )
    body = response_body(response)
    assert response.status_code == 200
    assert seen == [(page.pk, True)]
    assert b"Synthetic published preview content" in body
    assert b"UNPUBLISHED DRAFT CANARY" not in body
    assert "Link" not in response
    assert not AgentAccess.objects.exists()
    control = client.get(PREVIEW_PATH, HTTP_HOST="localhost", HTTP_USER_AGENT="GPTBot")
    assert control["Content-Type"].startswith("text/markdown")
    response_body(control)
    assert AgentAccess.objects.get().count == 1


@pytest.mark.parametrize("restriction", ["page", "ancestor"])
def test_preview_adapter_denies_restricted_content(corpus, client, restriction):
    page = ArticlePage.objects.get(slug="preview")
    PageViewRestriction.objects.create(
        page=page if restriction == "page" else page.get_parent(), restriction_type="login"
    )
    response = client.get(
        PREVIEW_PATH + "?preview=1", HTTP_HOST="localhost", HTTP_USER_AGENT="GPTBot"
    )
    assert response.status_code == 404
    assert b"Synthetic published preview content" not in response_body(response)
    assert not AgentAccess.objects.exists()


def test_truncated_plan_reports_unscheduled_fixture_methods(corpus, client):
    _, checks = corpus
    plan, pages = make_plan(client, checks)
    first_fixture = next(
        i for i, row in enumerate(plan["requests"]) if row["scenario"] == "fallback"
    )
    for budget in (first_fixture, first_fixture + 1):
        short = sim.build_plan(pages, TARGET, fixtures=checks, max_requests=budget)
        assert short["coverage"]["missing_fixtures"] == sorted(REQUIRED_FIXTURES)
        assert not short["coverage"]["suite_complete"]


def test_full_plan_reconciles_actual_counters_with_test_transport_evidence(
    corpus, client, tmp_path
):
    _, checks = corpus
    plan, _ = make_plan(client, checks)

    def snapshot():
        return {
            "captured_at": timezone.now().isoformat(),
            "rows": [
                {**row, "access_date": row["access_date"].isoformat()}
                for row in AgentAccess.objects.values(
                    "page_id", "agent", "access_method", "access_date", "count"
                )
            ],
        }

    before = snapshot()
    origins = []

    def transport(spec, headers, timeout, max_bytes):
        status, response_headers, body = fetch(client, spec)
        # Test adapter evidence only: these rows are not nginx/deployment logs.
        parts = urlsplit(spec.url)
        origins.append(
            {
                "run_id": headers["X-Sim-Run"],
                "request_id": headers["X-Sim-Request"],
                "timestamp": timezone.now().isoformat(),
                "method": spec.method,
                "uri": parts.path + ("?" + parts.query if parts.query else ""),
                "user_agent": spec.ua,
                "accept": spec.accept,
                "status": status,
                "content_type": response_headers["Content-Type"],
                "upstream_status": str(status),
                "upstream_cache_status": "",
                "request_time": "0",
            }
        )
        return status, response_headers, body

    path = tmp_path / "run.jsonl"
    with sim.Runner(
        path,
        TARGET,
        max_requests=250,
        transport=transport,
        clock=Clock(),
        metadata={"coverage": plan["coverage"]},
    ) as runner:
        for row in plan["requests"]:
            runner.fetch(sim.RequestSpec.from_dict(row))
        runner.emit("coverage", completed_plan_requests=250, planned_requests=250)
    assert runner.failures == 0
    report = sim.reconcile(events(path), origins, before, snapshot())
    assert report["status"] == "matched", report
    assert report["warnings"] == []
    assert report["counts"]["attempts"] == 250
    assert sum(bucket["expected"] for bucket in report["buckets"]) > 0
    assert all(bucket["residual"] == 0 for bucket in report["buckets"])
    assert len([row for row in events(path) if row.get("scenario") in REQUIRED_FIXTURES]) == 12


def test_seed_command_requires_opt_in_and_refuses_existing_branch(settings, corpus):
    settings.SIMULATOR_FIXTURES_ENABLED = False
    with pytest.raises(CommandError, match="simulator_settings"):
        call_command("agentmd_simulator_fixtures", stdout=StringIO())
    settings.SIMULATOR_FIXTURES_ENABLED = True
    count = Page.objects.count()
    with pytest.raises(CommandError, match="already exists"):
        call_command("agentmd_simulator_fixtures", stdout=StringIO())
    assert Page.objects.count() == count
