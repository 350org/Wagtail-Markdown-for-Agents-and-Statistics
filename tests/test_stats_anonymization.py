"""Upgrades remove legacy header fragments without losing historical totals."""

from datetime import date
from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Sum
from django.db.models.query import QuerySet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("interrupt", [False, True])
def test_anonymization_merges_batches_preserves_dimensions_and_is_restartable(
    monkeypatch, interrupt
):
    state = MigrationExecutor(connection).loader.project_state(
        [("wagtail_markdown_agents", "0005_agentaccess")]
    )
    access = state.apps.get_model("wagtail_markdown_agents", "AgentAccess")
    dimensions = {"page_id": 123, "access_method": "export-url", "access_date": date(2026, 9, 22)}
    access.objects.bulk_create(
        [access(**dimensions, agent=f"person-{i}@example.invalid", count=2) for i in range(503)]
        + [
            access(**dimensions, agent="", count=5),
            access(**dimensions, agent="GPTBot", count=7),
            access(**{**dimensions, "page_id": 456}, agent="custom-client", count=11),
            access(**{**dimensions, "access_method": "query-param"}, agent="curl", count=13),
            access(
                **{**dimensions, "access_date": date(2026, 9, 21)}, agent="custom-client", count=17
            ),
        ]
    )
    total = access.objects.aggregate(total=Sum("count"))["total"]
    migration = import_module("wagtail_markdown_agents.migrations.0006_anonymize_unknown_agents")
    if interrupt:
        original_delete = QuerySet.delete
        deletions = 0

        def interrupted_delete(queryset):
            nonlocal deletions
            deletions += 1
            if deletions == 2:
                raise RuntimeError("Interrupted before batch deletion")
            return original_delete(queryset)

        with monkeypatch.context() as patch:
            patch.setattr(QuerySet, "delete", interrupted_delete)
            with (
                connection.schema_editor(atomic=False) as editor,
                pytest.raises(RuntimeError, match="Interrupted"),
            ):
                migration.anonymize_unknown_agents(state.apps, editor)
        assert access.objects.aggregate(total=Sum("count"))["total"] == total
        assert access.objects.get(**dimensions, agent="").count == 1005
        assert access.objects.filter(agent__contains="@example.invalid").count() == 3
    for _ in range(2):
        with connection.schema_editor(atomic=False) as editor:
            migration.anonymize_unknown_agents(state.apps, editor)
        assert access.objects.count() == 5
        assert access.objects.aggregate(total=Sum("count"))["total"] == total
        assert access.objects.get(**dimensions, agent="").count == 1011
        assert access.objects.get(**dimensions, agent="GPTBot").count == 7
        assert access.objects.get(page_id=456).count == 11
        assert access.objects.get(access_method="query-param").count == 13
        assert access.objects.get(access_date=date(2026, 9, 21)).count == 17
        assert set(access.objects.values_list("agent", flat=True)) == {"", "GPTBot"}
