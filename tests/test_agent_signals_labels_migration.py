"""Migration 0008 stores agent-signals' labels without losing a request (#93)."""

import json
from datetime import date, timedelta
from importlib import import_module
from pathlib import Path

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Sum
from django.db.models.query import QuerySet

from wagtail_markdown_agents.data.agents import AGENTS, RETIRED_AGENTS

pytestmark = pytest.mark.django_db(transaction=True)

MIGRATION = import_module("wagtail_markdown_agents.migrations.0008_agent_signals_labels")
DAY = date(2026, 11, 27)


def access_model():
    state = MigrationExecutor(connection).loader.project_state(
        [("wagtail_markdown_agents", "0007_refresh_and_listing_markers")]
    )
    return state.apps, state.apps.get_model("wagtail_markdown_agents", "AgentAccess")


def migrate(apps):
    with connection.schema_editor(atomic=False) as editor:
        MIGRATION.store_agent_signals_labels(apps, editor)


def by_label(access):
    return {
        row["agent"]: row["n"]
        for row in access.objects.values("agent").annotate(n=Sum("count")).order_by("agent")
    }


def test_frozen_labels_are_the_registry_at_this_migration():
    assert set(MIGRATION.KNOWN_LABELS) == {a.label for a in AGENTS + RETIRED_AGENTS}
    assert set(MIGRATION.RENAMES.values()) <= set(MIGRATION.KNOWN_LABELS)
    assert all(old == new + "/" for old, new in MIGRATION.RENAMES.items())


def test_staging_counts_become_the_expected_labels():
    # The owner's bakerydemo staging counts, one row per label, and their expected result.
    data = json.loads(
        (Path(__file__).with_name("fixtures") / "agent-labels-staging-2026-11-27.json").read_text()
    )
    apps, access = access_model()
    access.objects.bulk_create(
        access(page_id=1, agent=agent, access_method="ua", access_date=DAY, count=count)
        for agent, count in data["before"].items()
    )
    assert (len(by_label(access)), sum(by_label(access).values())) == (83, 1865)
    migrate(apps)
    after = by_label(access)
    assert after == data["expected"]
    assert (len(after), sum(after.values()), after[""]) == (80, 1865, 238)


@pytest.mark.parametrize("interrupt", [False, True])
def test_renames_merge_on_the_unique_key_in_batches_and_restart(monkeypatch, interrupt):
    apps, access = access_model()
    dims = {"page_id": 7, "access_method": "ua"}
    access.objects.bulk_create(
        # 503 slashed rows on different days, so the work spans two batches…
        [
            access(**dims, access_date=DAY - timedelta(days=i), agent="ShapBot/", count=2)
            for i in range(503)
        ]
        # …one of them on the same key as a row already stored without the slash…
        + [access(**dims, access_date=DAY, agent="ShapBot", count=5)]
        + [
            access(**dims, access_date=DAY, agent="meta-externalfetcher/", count=3),
            access(**dims, access_date=DAY, agent="OAI-AdsBot", count=4),
            access(**dims, access_date=DAY, agent="", count=1),
            access(**{**dims, "page_id": 8}, access_date=DAY, agent="FacebookBot", count=6),
            access(**dims, access_date=DAY, agent="GPTBot", count=9),
        ]
    )
    total = access.objects.aggregate(total=Sum("count"))["total"]
    if interrupt:
        original = QuerySet.delete
        deletions = 0

        def interrupted(queryset):
            nonlocal deletions
            deletions += 1
            if deletions == 2:
                raise RuntimeError("Interrupted in the second batch")
            return original(queryset)

        with monkeypatch.context() as patch:
            patch.setattr(QuerySet, "delete", interrupted)
            with pytest.raises(RuntimeError, match="Interrupted"):
                migrate(apps)
        # The first batch committed; the second rolled back whole.
        assert access.objects.aggregate(total=Sum("count"))["total"] == total
    for _ in range(2):
        migrate(apps)
        assert access.objects.aggregate(total=Sum("count"))["total"] == total
        assert access.objects.filter(agent__endswith="/").count() == 0
        assert access.objects.filter(agent="ShapBot").count() == 503
        assert access.objects.get(**dims, access_date=DAY, agent="ShapBot").count == 7
        assert access.objects.get(agent="meta-externalfetcher").count == 3
        assert access.objects.get(**dims, access_date=DAY, agent="").count == 5
        assert access.objects.get(page_id=8, agent="").count == 6
        assert access.objects.get(agent="GPTBot").count == 9
        assert set(access.objects.values_list("agent", flat=True)) == {
            "",
            "ShapBot",
            "meta-externalfetcher",
            "GPTBot",
        }
