"""Retention pruning deletes only counters older than an explicit UTC cutoff (#36)."""

from datetime import UTC, date, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from wagtail_markdown_agents.management.commands import agentmd_prune_stats
from wagtail_markdown_agents.models import AgentAccess

pytestmark = pytest.mark.django_db
TODAY = date(2026, 9, 15)  # UTC; the fixed clock is still 14 September in the Americas.


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 9, 15, 0, 15, tzinfo=UTC)

    monkeypatch.setattr(agentmd_prune_stats, "datetime", Clock)
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Unexpected prompt"))


def run(*args, **kwargs):
    output = StringIO()
    call_command("agentmd_prune_stats", *args, stdout=output, stderr=output, **kwargs)
    return output.getvalue()


def counters(*offsets):
    """One counter per day offset before TODAY; returns their dates."""
    AgentAccess.objects.bulk_create(
        AgentAccess(page_id=1, agent="GPTBot", access_method="ua", access_date=day, count=2)
        for day in (TODAY - timedelta(days=offset) for offset in offsets)
    )
    return {offset: TODAY - timedelta(days=offset) for offset in offsets}


def dates():
    return sorted(AgentAccess.objects.values_list("access_date", flat=True))


def test_default_retention_deletes_only_dates_older_than_the_utc_cutoff(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {}
    days = counters(-1, 0, 89, 90, 91, 400)
    with timezone.override("America/Los_Angeles"):
        output = run("--yes")
    assert "before 2026-06-17 (older than 90 days, from STATS_RETENTION_DAYS)" in output
    assert "deleted=2 retained=4" in output
    assert dates() == sorted(days[offset] for offset in (-1, 0, 89, 90))


def test_days_option_overrides_the_configured_retention(settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STATS_RETENTION_DAYS": 10}
    days = counters(0, 9, 10, 11, 30)
    assert "Selected 3" in run("--days", "9", "--dry-run")
    assert "Selected 2" in run("--dry-run")
    assert AgentAccess.objects.count() == 5
    run("--days", "30", "--yes")
    assert dates() == sorted(days.values())
    run("--yes")
    assert dates() == sorted(days[offset] for offset in (0, 9, 10))


@pytest.mark.parametrize("args", [["--days", "0"], ["--days", "-1"], ["--days", "x"]])
def test_invalid_days_fail_before_deleting(args):
    counters(400)
    with pytest.raises(CommandError):
        run(*args, "--yes")
    assert AgentAccess.objects.count() == 1


@pytest.mark.parametrize("value", [0, True, "90"])
def test_invalid_configured_retention_fails_before_deleting(settings, value):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"STATS_RETENTION_DAYS": value}
    counters(400)
    with pytest.raises(CommandError, match="STATS_RETENTION_DAYS"):
        run("--yes")
    assert AgentAccess.objects.count() == 1


def test_confirmation_is_required_unless_yes_and_never_implied(monkeypatch):
    counters(0, 400)
    monkeypatch.setattr("builtins.input", lambda *args: "no")
    with pytest.raises(CommandError, match="cancelled"):
        run()
    monkeypatch.setattr("builtins.input", lambda *args: "y")
    with pytest.raises(CommandError, match="cancelled"):
        run()

    def eof(*args):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(CommandError, match="--yes"):
        run()
    assert AgentAccess.objects.count() == 2
    monkeypatch.setattr("builtins.input", lambda prompt: " YES ")
    assert "deleted=1 retained=1" in run()


def test_dry_run_and_empty_selection_never_prompt_or_delete():
    counters(0, 400)
    assert "Dry run: deleted=1" in run("--dry-run")
    assert AgentAccess.objects.count() == 2
    assert "Selected 0" in run("--days", "500")
    assert AgentAccess.objects.count() == 2


def test_pruning_is_one_bounded_delete_regardless_of_volume():
    AgentAccess.objects.bulk_create(
        AgentAccess(page_id=page, agent=agent, access_method="ua", access_date=day, count=1)
        for page in range(1, 41)
        for agent in ("GPTBot", "ClaudeBot", "")
        for day in (TODAY - timedelta(days=offset) for offset in (0, 89, 90, 91, 200))
    )
    with CaptureQueriesContext(connection) as queries:
        output = run("--yes")
    assert "deleted=240 retained=360" in output
    deletes = [query["sql"] for query in queries if query["sql"].startswith("DELETE")]
    assert len(deletes) == 1
    assert "SELECT" not in deletes[0]
    assert len(queries) == 3  # count, delete, retained count
