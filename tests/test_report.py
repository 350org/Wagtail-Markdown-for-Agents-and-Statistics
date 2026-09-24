"""The admin report presents one consistently filtered set of daily counters."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from wagtail import hooks
from wagtail.models import Page

from wagtail_markdown_agents.models import AgentAccess
from wagtail_markdown_agents.reports import bucket_dates, correlation, top_pages

pytestmark = pytest.mark.django_db
TODAY = date(2026, 9, 15)


@pytest.fixture
def report(client, admin_user, monkeypatch):
    from wagtail_markdown_agents import reports

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 9, 15, 0, 15, tzinfo=UTC)

    monkeypatch.setattr(reports, "datetime", Clock)
    client.force_login(admin_user)
    return lambda **params: client.get(reverse("agentmd_report"), params)


def counter(**kwargs):
    return AgentAccess.objects.create(
        **{
            "page_id": 12345,
            "agent": "GPTBot",
            "access_method": "export-url",
            "access_date": TODAY,
            "count": 3,
            **kwargs,
        }
    )


@pytest.mark.parametrize(
    "span,grain",
    [(1, "daily"), (92, "daily"), (93, "monthly"), (1827, "monthly"), (1828, "yearly")],
)
def test_grain_boundaries(span, grain):
    start = TODAY - timedelta(days=span - 1)
    actual, buckets = bucket_dates(start, TODAY)
    assert actual == grain
    assert buckets == sorted(set(buckets))
    assert buckets[0] <= start and buckets[-1] <= TODAY
    if grain == "daily":
        assert len(buckets) == span


def test_calendar_buckets_cover_leap_day_and_year_transition():
    grain, buckets = bucket_dates(date(2023, 12, 31), date(2024, 4, 1))
    assert grain == "monthly"
    assert buckets == [
        date(2023, 12, 1),
        date(2024, 1, 1),
        date(2024, 2, 1),
        date(2024, 3, 1),
        date(2024, 4, 1),
    ]
    assert bucket_dates(date.min, date.max)[1][-1] == date(9999, 1, 1)


@pytest.mark.parametrize(
    "values,expected",
    [
        ([], None),
        ([4], None),
        ([4, 4], None),
        ([0, 0, 0], None),
        ([1, 2, 3], 1),
        ([3, 2, 1], -1),
        ([1, 0, 1], 0),
    ],
)
def test_trends_are_correlation(values, expected):
    actual = correlation(values)
    assert actual is None if expected is None else actual == pytest.approx(expected)


def test_top_pages_ranks_ties_and_uses_report_total():
    rows = [
        {"page_id": 4, "total": 5},
        {"page_id": 3, "total": 5},
        {"page_id": 2, "total": 10},
        {"page_id": 1, "total": 0},
    ]
    assert top_pages(rows, 20) == [
        {"page_id": 2, "total": 10, "rank": 1, "share": "50%"},
        {"page_id": 3, "total": 5, "rank": 2, "share": "25%"},
        {"page_id": 4, "total": 5, "rank": 2, "share": "25%"},
    ]
    assert top_pages([], 0) == []
    assert top_pages([{"page_id": 1, "total": 0}], 0) == []


def test_top_pages_stops_at_ten_and_marks_tiny_shares():
    rows = [{"page_id": pk, "total": 1} for pk in range(12, 0, -1)]
    assert [row["page_id"] for row in top_pages(rows, 400)] == list(range(1, 11))
    assert all(row["rank"] == 1 and row["share"] == "<1%" for row in top_pages(rows, 400))


@pytest.mark.parametrize("use_tz", [True, False])
def test_default_is_7_inclusive_utc_days(report, settings, use_tz):
    settings.USE_TZ = use_tz
    with timezone.override("America/Los_Angeles"):
        counter(access_date=TODAY - timedelta(days=6), count=5)
        counter(access_date=TODAY - timedelta(days=7), count=100)
        counter(access_date=TODAY + timedelta(days=1), count=100)
        counter(count=7)
        response = report()
    assert response.status_code == 200
    summary = response.context["summary"]
    assert summary["start"] == date(2026, 9, 9)
    assert summary["end"] == TODAY
    assert summary["tiles"][0]["count"] == 12
    assert len(summary["buckets"]) == 7
    assert response.context["report_form"]["preset"].value() == "7"


@pytest.mark.parametrize("preset,days", [("7", 7), ("30", 30), ("90", 90), ("365", 365)])
def test_presets(report, preset, days):
    response = report(preset=preset)
    assert response.context["summary"]["start"] == TODAY - timedelta(days=days - 1)


def test_combined_filters_and_reporting_consistency(report):
    row = counter(count=17)
    counter(page_id=999, count=100)
    counter(agent="ClaudeBot", count=200)
    counter(access_method="ua", count=300)
    counter(access_date=TODAY - timedelta(days=1), count=400)
    response = report(
        page_id=row.page_id,
        agent="label:GPTBot",
        method="export-url",
        start=TODAY,
        end=TODAY,
        intent="training",
    )
    assert response.status_code == 200
    assert [r.pk for r in response.context["object_list"]] == [row.pk]
    summary = response.context["summary"]
    assert [t["count"] for t in summary["tiles"]] == [17, 0, 0, 17, 0, 0]
    assert sum(sum(b["counts"]) for b in summary["buckets"]) == 17
    assert sum(bar["count"] for bar in summary["bars"]) == 17
    assert {bar["key"] for bar in summary["bars"]} == {"training"}
    assert all(t["trend"] == "Neutral" for t in summary["tiles"])
    assert response.context["object_list"][0].intent == "training"
    assert (
        report(agent="label:GPTBot", intent="search").context["summary"]["tiles"][0]["count"] == 0
    )


def test_hook_snapshot_shared_by_filters_chart_tiles_and_rows(report):
    counter(agent="ProjectClient", count=23)
    counter(agent="OddClient", count=9)
    calls = []

    def override(categories):
        calls.append(1)
        categories.clear()
        categories.update({"on-demand": ["project"], "invalid": ["odd"]})

    with hooks.register_temporarily("construct_markdown_agent_categories", override):
        response = report(intent="on-demand")
        assert calls == [1]
        assert [t["count"] for t in response.context["summary"]["tiles"]] == [23, 23, 0, 0, 0, 0]
        assert sum(b["counts"][0] for b in response.context["summary"]["buckets"]) == 23
        assert sum(b["count"] for b in response.context["summary"]["bars"]) == 23
        assert response.context["object_list"][0].intent == "on-demand"
        unknown = report(intent="unknown")
        assert unknown.context["summary"]["tiles"][0]["count"] == 9
    assert report(intent="on-demand").context["summary"]["tiles"][0]["count"] == 0


def test_deleted_pages_unknown_agents_and_counting_limits(report):
    page = Page.get_first_root_node().add_child(instance=Page(title="Temporary", slug="temporary"))
    pk = page.pk
    counter(page_id=pk, agent="")
    page.delete()
    response = report(page_id=pk, agent="label:")
    html = response.content.decode()
    for text in [
        f"Deleted page #{pk}",
        "unknown",
        "export-url",
        "estimate",
        "CDN",
        "static",
        "aggregate downloads",
        "correlation",
    ]:
        assert text in html
    assert response.context["summary"]["tiles"][0]["count"] == 3


def test_page_filter_is_a_searchable_datalist(report):
    root = Page.get_first_root_node()
    about = root.add_child(instance=Page(title="About us", slug="about-us"))
    news = root.add_child(instance=Page(title="News", slug="news"))
    counter(page_id=about.pk, count=5)
    counter(page_id=news.pk, count=7)
    counter(page_id=999, count=11)
    html = report().content.decode()
    assert 'list="id_page_id-options"' in html and '<datalist id="id_page_id-options">' in html
    for label in [f"About us (#{about.pk})", f"News (#{news.pk})", "Deleted page #999"]:
        assert f'<option value="{label}">' in html
    assert '<select name="page_id"' not in html

    for value in [str(about.pk), f"#{about.pk}", f"About us (#{about.pk})", "about US"]:
        response = report(page_id=value)
        assert response.context["summary"]["tiles"][0]["count"] == 5, value
        # Bare IDs from leader links show the readable label in the box.
        assert f'value="About us (#{about.pk})"' in response.content.decode()
    assert report(page_id="Deleted page #999").context["summary"]["tiles"][0]["count"] == 11
    assert report(page_id="").context["summary"]["tiles"][0]["count"] == 23

    for value in ["Missing", "12345678", "About", "(#999) About"]:
        response = report(page_id=value)
        assert response.context["report_form"].errors["page_id"], value
        assert response.context["summary"] is None


def test_pagination_preserves_filters_and_whole_report_totals(report):
    AgentAccess.objects.bulk_create(
        [
            AgentAccess(
                page_id=5000 + i, agent="GPTBot", access_method="ua", access_date=TODAY, count=2
            )
            for i in range(55)
        ]
    )
    response = report(p=2, method="ua", intent="training")
    assert response.context["page_obj"].number == 2
    assert len(response.context["object_list"]) == 5
    assert response.context["summary"]["tiles"][0]["count"] == 110
    assert response.context["summary"]["page_leader"]["truncated"]
    assert "50+" in response.content.decode()
    assert (
        "method=ua" in response.content.decode() and "intent=training" in response.content.decode()
    )
    assert report(p="invalid").status_code == 200
    assert report(p=999).context["page_obj"].number == 2


@pytest.mark.parametrize(
    "params",
    [
        {"start": "bad", "end": str(TODAY)},
        {"start": "2026-09-16", "end": "2026-09-15"},
        {"preset": "custom"},
        {"preset": "invalid"},
        {"intent": "invalid"},
        {"method": "invalid"},
        {"page_id": "-1"},
        {"agent": "missing"},
        {"operator": "missing"},
    ],
)
def test_invalid_filters_show_errors_not_unfiltered_data(report, params):
    counter()
    response = report(**params)
    assert response.status_code == 200
    assert response.context["report_form"].errors
    assert response.context["summary"] is None
    assert not response.context["object_list"]


def test_empty_states(report):
    assert "No recorded page requests yet" in report().content.decode()
    counter(access_date=date(2020, 1, 1))
    response = report()
    assert "No page requests match these filters" in response.content.decode()
    assert "No pages requested in this range." in response.content.decode()
    assert response.context["summary"]["top_pages"] == []
    assert all(
        t["count"] == 0 and t["trend"] == "Neutral" for t in response.context["summary"]["tiles"]
    )


@pytest.mark.parametrize(
    "role,status",
    [
        ("anonymous", 302),
        ("staff", 302),
        ("editor", 302),
        ("viewer", 200),
        ("superuser", 200),
        ("inactive", 302),
    ],
)
def test_report_and_menu_permissions(client, django_user_model, role, status):
    from wagtail_markdown_agents.wagtail_hooks import (
        register_permissions,
        register_report_menu_item,
    )

    user = django_user_model.objects.create_user(
        username=role, is_staff=True, is_superuser=role == "superuser", is_active=role != "inactive"
    )
    if role in {"editor", "viewer", "inactive"}:
        user.user_permissions.add(Permission.objects.get(codename="access_admin"))
    if role in {"viewer", "inactive"}:
        user.user_permissions.add(Permission.objects.get(codename="view_agentaccess"))
    if role != "anonymous":
        client.force_login(user)
    response = client.get(reverse("agentmd_report"))
    assert response.status_code == status
    if status == 302:
        assert response.url == (
            "/admin/" if role == "editor" else "/admin/login/?next=/admin/reports/agent-access/"
        )
    assert register_report_menu_item().is_shown(response.wsgi_request) == (status == 200)
    assert list(register_permissions().values_list("codename", flat=True)) == ["view_agentaccess"]


@pytest.mark.parametrize(
    "start,end,grain,expected",
    [
        ("2023-12-31", "2024-04-01", "monthly", [3, 5, 7, 0, 11]),
        ("2020-01-01", "2026-09-15", "yearly", [0, 0, 0, 3, 23, 0, 0]),
    ],
)
def test_calendar_sql_aggregation_and_partial_buckets(report, start, end, grain, expected):
    for day, count in [("2023-12-31", 3), ("2024-01-01", 5), ("2024-02-29", 7), ("2024-04-01", 11)]:
        counter(access_date=day, count=count)
    counter(access_date="2019-12-31", count=1000)
    response = report(start=start, end=end)
    summary = response.context["summary"]
    assert summary["grain"] == grain
    assert [sum(b["counts"]) for b in summary["buckets"]] == expected
    assert summary["tiles"][0]["count"] == sum(expected) == 26
    assert sum(bar["count"] for bar in summary["bars"]) == 26


def test_untrusted_labels_are_escaped(report):
    counter(agent='<script>alert("x")</script>')
    response = report()
    assert '<script>alert("x")</script>' not in response.content.decode()
    assert "&lt;script&gt;" in response.content.decode()


def test_non_staff_group_permission_and_no_export_bypass(client, django_user_model):
    from django.contrib.auth.models import Group

    user = django_user_model.objects.create_user(username="report-viewer", is_staff=False)
    group = Group.objects.create(name="Statistics viewers")
    group.permissions.add(
        *Permission.objects.filter(codename__in=["access_admin", "view_agentaccess"])
    )
    user.groups.add(group)
    client.force_login(user)
    assert client.get(reverse("agentmd_report"), {"export": "csv"}).status_code == 200
    group.permissions.remove(Permission.objects.get(codename="view_agentaccess"))
    response = client.get(reverse("agentmd_report"), {"export": "csv"})
    assert response.status_code == 302 and response.url == "/admin/"


def test_new_agent_during_report_uses_same_hook_snapshot(report, monkeypatch):
    from wagtail_markdown_agents.reports import AgentAccessReportView

    counter()
    original = AgentAccessReportView.get_context_data

    def insert_during_read(self, **kwargs):
        # Filter choices have already been fetched; simulate a concurrent new label.
        counter(agent="new-project-client", count=20)
        return original(self, **kwargs)

    monkeypatch.setattr(AgentAccessReportView, "get_context_data", insert_during_read)
    with hooks.register_temporarily(
        "construct_markdown_agent_categories",
        lambda categories: categories["search"].append("new-project"),
    ):
        response = report()
    assert response.context["summary"]["tiles"][2]["count"] == 20
    assert response.context["object_list"][1].intent == "search"


def test_mixed_purposes_filter_chart_and_totals_agree(report):
    counter(agent="Applebot", count=7)
    counter(agent="bingbot", count=11)
    counter(agent="GPTBot", count=20)
    response = report(intent="mixed")
    summary = response.context["summary"]
    assert [tile["count"] for tile in summary["tiles"]] == [18, 0, 0, 0, 18, 0]
    assert sum(bar["count"] for bar in summary["bars"]) == 18
    assert {bar["key"] for bar in summary["bars"]} == {"mixed"}
    assert {row.intent for row in response.context["object_list"]} == {"mixed"}
    assert "Mixed purposes" in response.content.decode()


def test_operator_cards_leaders_and_unattributed_reconcile(report):
    for agent, count in [
        ("GPTBot", 40),
        ("ChatGPT-User", 7),
        ("ClaudeBot", 12),
        ("Mozilla", 5),
        ("", 3),
    ]:
        counter(agent=agent, count=count)
    summary = report().context["summary"]
    assert summary["tiles"][0]["count"] == 67
    assert [(card["key"], card["count"]) for card in summary["operator_cards"]] == [
        ("openai", 47),
        ("anthropic", 12),
        ("unattributed", 8),
    ]
    assert summary["agent_leader"]["names"] == [("GPTBot", "GPTBot")]
    assert summary["operator_leader"]["names"] == [("OpenAI", "openai")]
    assert sum(bar["count"] for bar in summary["bars"]) == 67
    html = report().content.decode()
    assert "Recorded Markdown requests" in html
    assert "Requests by purpose" in html
    assert 'aria-label="Filter by OpenAI: 47 requests"' in html


def test_top_pages_table_links_shares_filters_and_section_order(report):
    root = Page.get_first_root_node()
    pages = [
        root.add_child(instance=Page(title=title, slug=slug))
        for title, slug in [("First", "first"), ("Second", "second"), ("Third", "third")]
    ]
    for page, count in zip(pages, [300, 99, 1], strict=True):
        counter(page_id=page.pk, count=count)
    response = report(operator="openai", method="export-url", page_search="old", p=2)
    summary = response.context["summary"]
    assert summary["tiles"][0]["count"] == 400
    assert sum(card["count"] for card in summary["operator_cards"]) == 400
    assert sum(row["total"] for row in summary["top_pages"]) == 400
    assert [(row["rank"], row["total"], row["share"]) for row in summary["top_pages"]] == [
        (1, 300, "75%"),
        (2, 99, "25%"),
        (3, 1, "<1%"),
    ]
    html = response.content.decode()
    headings = [
        "<h2>Summary",
        "<h2>Purposes</h2>",
        "<h2>Operators</h2>",
        "<h2>Top pages</h2>",
        "<h2>Agents by access method</h2>",
        "<h2>Daily records</h2>",
    ]
    positions = [html.index(heading) for heading in headings]
    assert positions == sorted(positions)
    for page, count, rank, share in zip(
        pages, [300, 99, 1], [1, 2, 3], ["75%", "25%", "<1%"], strict=True
    ):
        row = next(row for row in summary["top_pages"] if row["page_id"] == page.pk)
        if page == pages[0]:
            assert row["url"] == summary["page_links"][0][1]
        assert f"page_id={page.pk}" in row["url"]
        assert "operator=openai" in row["url"] and "method=export-url" in row["url"]
        assert "page_search=" not in row["url"] and "p=" not in row["url"]
        rendered_row = (
            f'<tr><td>{rank}</td><th scope="row"><a href="{escape(row["url"])}">'
            f"{page.title}</a></th><td>{count}</td><td>{escape(share)}</td></tr>"
        )
        assert rendered_row in html
    filtered = report(page_id=pages[0].pk, operator="openai", page_search="old", p=2)
    filtered_html = filtered.content.decode()
    assert f"Showing {pages[0].title} only." in filtered_html
    assert '<table class="listing agentmd-top-pages">' not in filtered_html
    assert "Clear page filter" in filtered_html
    clear_url = filtered.context["summary"]["clear_page_url"]
    assert "page_id=" not in clear_url and "page_search=" not in clear_url
    assert "operator=openai" in clear_url and "p=" not in clear_url


def test_access_method_rows_count_distinct_pages_for_current_filters(report):
    counter(page_id=111, agent="GPTBot", access_method="ua", count=3)
    counter(
        page_id=111,
        agent="GPTBot",
        access_method="ua",
        access_date=TODAY - timedelta(days=1),
        count=2,
    )
    counter(page_id=222, agent="GPTBot", access_method="ua", count=4)
    counter(page_id=333, agent="GPTBot", access_method="export-url", count=5)
    counter(page_id=444, agent="ClaudeBot", access_method="ua", count=6)
    summary = report(operator="openai").context["summary"]
    assert [
        (row["agent"], row["access_method"], row["requests"], row["unique_pages"])
        for row in summary["method_rows"]
    ] == [
        ("GPTBot", "ua", 9, 2),
        ("GPTBot", "export-url", 5, 1),
    ]


def test_operator_filter_drops_conflicting_agent_and_preserves_other_filters(report):
    row = counter(agent="GPTBot", count=9)
    counter(agent="ClaudeBot", count=3)
    response = report(
        operator="openai", agent="label:ClaudeBot", method="export-url", page_id=row.page_id, p=2
    )
    assert response.context["report_form"].cleaned_data["agent"] == ""
    assert response.context["summary"]["tiles"][0]["count"] == 9
    assert {r.agent for r in response.context["object_list"]} == {"GPTBot"}
    assert [value for value, _ in response.context["report_form"].fields["agent"].choices] == [
        "",
        "label:GPTBot",
    ]
    card = response.context["summary"]["operator_cards"][0]
    assert card["active"] and "operator=" not in card["url"]
    assert 'aria-current="true"' in response.content.decode()
    assert "Clear operator filter" in response.content.decode()
    assert "method=export-url" in card["url"] and "page_id=" in card["url"]
    assert "p=" not in card["url"]
    assert (
        report(operator="openai", agent="label:GPTBot").context["report_form"].cleaned_data["agent"]
        == "label:GPTBot"
    )


def test_operator_ties_and_unattributed_only(report):
    for agent in ("PerplexityBot", "GPTBot", "ClaudeBot", "Bytespider"):
        counter(agent=agent, count=5)
    counter(agent="CCBot", count=1)
    summary = report().context["summary"]
    assert summary["agent_leader"]["winner_count"] == 4
    assert [name for name, _ in summary["agent_leader"]["names"]] == [
        "Bytespider",
        "ClaudeBot",
        "GPTBot",
    ]
    assert summary["agent_leader"]["more"] == 1
    AgentAccess.objects.all().delete()
    counter(agent="curl", count=9)
    summary = report().context["summary"]
    assert summary["agent_leader"]["names"] == [("curl", "curl")]
    assert summary["operator_leader"]["empty"] == "No attributed operators in this range"
    assert [(card["key"], card["count"]) for card in summary["operator_cards"]] == [
        ("unattributed", 9)
    ]


def test_historical_operator_labels_do_not_change_serving_or_purpose(report):
    counter(agent="Bytespider", count=4)
    counter(agent="GoogleOther", count=6)
    summary = report().context["summary"]
    assert [(card["key"], card["count"]) for card in summary["operator_cards"]] == [
        ("google", 6),
        ("bytedance", 4),
    ]
    # The independently reviewed Wagtail registry currently marks GoogleOther unknown.
    assert summary["tiles"][-1]["count"] == 6
