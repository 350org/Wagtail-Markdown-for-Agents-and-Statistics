"""Read-only Wagtail reporting over the daily access counters."""

import math
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from django import forms
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from wagtail.admin.views.reports import ReportView
from wagtail.models import Page
from wagtail.permission_policies import ModelPermissionPolicy

from .data.operators import OPERATOR_NAMES, operator_for_agent
from .models import AgentAccess
from .stats import ACCESS_METHODS, INTENT_CATEGORIES, categorise_agent, get_agent_categories

REPORT_PERMISSION = ModelPermissionPolicy(AgentAccess)
INTENT_LABELS = {
    "on-demand": _("On-demand (estimate)"),
    "search": _("Search"),
    "training": _("Training"),
    "mixed": _("Mixed purposes"),
    "unknown": _("Unknown"),
}


def page_label(page_id, titles):
    if page_id in titles:
        return f"{titles[page_id]} (#{page_id})"
    return _("Deleted page #%(id)s") % {"id": page_id}


class PageInput(forms.TextInput):
    """A free-text page box with suggestions from every page that has history."""

    template_name = "wagtail_markdown_agents/widgets/page_input.html"
    options = ()

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["list_id"] = f"{widget['attrs'].get('id', name)}-options"
        widget["attrs"]["list"] = widget["list_id"]
        widget["options"] = self.options
        return context


class PageField(forms.CharField):
    """Accept a page ID, a suggested "Title (#ID)" label or one exact title."""

    widget = PageInput(attrs={"autocomplete": "off", "spellcheck": "false"})
    reference = re.compile(r"^#?(\d+)$|\(#(\d+)\)$")

    def __init__(self, **kwargs):
        super().__init__(required=False, **kwargs)
        self.pages = {}

    def set_pages(self, pages):
        self.pages = dict(pages)
        self.widget.options = [str(label) for label in self.pages.values()]

    def lookup(self, value):
        match = self.reference.search(value)
        if match and (pk := match.group(1) or match.group(2)) in self.pages:
            return pk
        titles = [
            pk
            for pk, label in self.pages.items()
            if str(label).rsplit(" (#", 1)[0].casefold() == value.casefold()
        ]
        return titles[0] if len(titles) == 1 else None

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return ""
        pk = self.lookup(value)
        if pk is None:
            raise forms.ValidationError(_("Choose a page from the suggestions or enter its ID."))
        return pk


class ReportFilterForm(forms.Form):
    preset = forms.ChoiceField(
        label=_("Date range"),
        choices=[
            ("7", _("Last 7 days")),
            ("30", _("Last 30 days")),
            ("90", _("Last 90 days")),
            ("365", _("Last 365 days")),
            ("custom", _("Custom dates")),
        ],
    )
    start = forms.DateField(label=_("From (UTC)"), widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label=_("To (UTC)"), widget=forms.DateInput(attrs={"type": "date"}))
    page_id = PageField(
        label=_("Page"),
    )
    agent = forms.ChoiceField(label=_("Agent"), required=False)
    operator = forms.ChoiceField(label=_("Operator"), required=False)
    method = forms.ChoiceField(
        label=_("Access method"),
        required=False,
        choices=[("", _("All methods"))] + [(m, m) for m in sorted(ACCESS_METHODS)],
    )
    intent = forms.ChoiceField(
        label=_("Intent"), required=False, choices=[("", _("All intents")), *INTENT_LABELS.items()]
    )

    def __init__(self, data, *, today, pages, agents):
        data = data.copy()
        preset = data.get("preset") or ("custom" if data.get("start") or data.get("end") else "7")
        data["preset"] = preset
        if preset in {"7", "30", "90", "365"}:
            data["start"] = (today - timedelta(days=int(preset) - 1)).isoformat()
            data["end"] = today.isoformat()
        operator = data.get("operator")
        if operator in {*OPERATOR_NAMES, "unattributed"}:
            agents = [agent for agent in agents if operator_for_agent(agent) == operator]
            selected_agent = data.get("agent", "")
            if selected_agent.startswith("label:") and selected_agent[6:] not in agents:
                data["agent"] = ""
        super().__init__(data)
        self.fields["page_id"].set_pages(pages)
        # Links filter by bare ID; show the readable label in the box instead.
        page = self.fields["page_id"].lookup(data.get("page_id", "").strip())
        if page is not None:
            self.data["page_id"] = self.fields["page_id"].pages[page]
        self.fields["operator"].choices = [
            ("", _("All operators")),
            *((key, name) for key, name in OPERATOR_NAMES.items()),
            ("unattributed", _("Unattributed")),
        ]
        # Prefix every value so the stored empty label has its own selectable value.
        self.fields["agent"].choices = [("", _("All agents"))] + [
            (f"label:{agent}", agent or _("unknown")) for agent in agents
        ]

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            self.add_error("end", _("The end date must be on or after the start date."))
        return data


def bucket_dates(start, end):
    """Inclusive UTC dates, with calendar-aligned monthly and yearly buckets."""
    span = (end - start).days + 1
    if span <= 92:
        return "daily", [start + timedelta(days=i) for i in range(span)]
    if span <= 1827:
        first = start.year * 12 + start.month - 1
        last = end.year * 12 + end.month - 1
        return "monthly", [date(i // 12, i % 12 + 1, 1) for i in range(first, last + 1)]
    return "yearly", [date(year, 1, 1) for year in range(start.year, end.year + 1)]


def correlation(values):
    """Pearson r against equally spaced time buckets; flat/short is undefined."""
    if len(values) < 2 or len(set(values)) == 1:
        return None
    centre_x = (len(values) - 1) / 2
    centre_y = sum(values) / len(values)
    numerator = sum((i - centre_x) * (value - centre_y) for i, value in enumerate(values))
    denominator = math.sqrt(
        sum((i - centre_x) ** 2 for i in range(len(values)))
        * sum((value - centre_y) ** 2 for value in values)
    )
    return max(-1.0, min(1.0, numerator / denominator))


def summarise(queryset, start, end, intent_for_agent):
    grain, dates = bucket_dates(start, end)
    counts = {day: dict.fromkeys(INTENT_CATEGORIES, 0) for day in dates}
    bucket = {
        "daily": F("access_date"),
        "monthly": TruncMonth("access_date"),
        "yearly": TruncYear("access_date"),
    }[grain]
    # Group in SQL before reading; no per-hit rows or per-page lookups for charts.
    aggregates = (
        queryset.order_by()
        .annotate(bucket=bucket)
        .values("bucket", "agent")
        .annotate(total=Sum("count"))
    )
    agents = Counter()
    for row in aggregates:
        counts[row["bucket"]][intent_for_agent(row["agent"])] += row["total"]
        agents[row["agent"]] += row["total"]
    series = [[counts[day][intent] for day in dates] for intent in INTENT_CATEGORIES]
    total = [sum(counts[day].values()) for day in dates]
    maximum = max(2, math.ceil(max(total) / 2) * 2)
    bars = []
    step = 900 / len(dates)
    for i, day in enumerate(dates):
        stacked = 0
        for key in INTENT_CATEGORIES:
            value = counts[day][key]
            if value:
                bars.append(
                    {
                        "key": key,
                        "label": INTENT_LABELS[key],
                        "date": day,
                        "count": value,
                        "x": f"{(i + 0.14) * step:.3f}",
                        "width": f"{step * 0.72:.3f}",
                        "y": f"{220 - (stacked + value) * 220 / maximum:.3f}",
                        "height": f"{value * 220 / maximum:.3f}",
                    }
                )
            stacked += value
    tiles = []
    for key, label, values in [("total", _("Total requests"), total)] + [
        (key, INTENT_LABELS[key], values)
        for key, values in zip(INTENT_CATEGORIES, series, strict=True)
    ]:
        r = correlation(values)
        trend = (
            _("Neutral")
            if r is None or abs(r) < 0.005
            else (_("Rising") if r > 0 else _("Falling"))
        )
        tiles.append(
            {
                "key": key,
                "label": label,
                "count": sum(values),
                "trend": trend,
                "correlation": None if r is None else f"{r:.2f}",
            }
        )
    return {
        "start": start,
        "end": end,
        "grain": grain,
        "tiles": tiles,
        "maximum": maximum,
        "midpoint": maximum // 2,
        "bars": bars,
        "series": [{"key": key, "label": INTENT_LABELS[key]} for key in INTENT_CATEGORIES],
        "buckets": [{"date": day, "counts": list(counts[day].values())} for day in dates],
        "agents": agents,
    }


def leader(counts, *, empty, label_for=None, eligible=lambda key: True):
    """Describe a leader and its ties without discarding tied counts."""
    candidates = {key: value for key, value in counts.items() if eligible(key) and value}
    if not candidates:
        return {"empty": empty}
    maximum = max(candidates.values())
    winners = [key for key, value in candidates.items() if value == maximum]
    # Labels, rather than database IDs, determine display order for page ties.
    winners.sort(key=lambda key: str(label_for(key) if label_for else key).casefold())
    return {
        "count": maximum,
        "tied": len(winners) > 1,
        "winner_count": len(winners),
        "names": [(label_for(key) if label_for else key, key) for key in winners[:3]],
        "more": max(0, len(winners) - 3),
    }


def top_pages(page_rows, report_total):
    """Rank filtered page totals with competition ties and whole-percent shares."""
    if report_total <= 0:
        return []
    rows = sorted(
        (row for row in page_rows if row["total"] > 0),
        key=lambda row: (-row["total"], row["page_id"]),
    )[:10]
    ranked = []
    previous_total = None
    rank = 0
    for position, row in enumerate(rows, 1):
        if row["total"] != previous_total:
            rank = position
        previous_total = row["total"]
        percent = (200 * row["total"] + report_total) // (2 * report_total)
        ranked.append(
            {
                "page_id": row["page_id"],
                "total": row["total"],
                "rank": rank,
                "share": f"{percent}%" if percent else "<1%",
            }
        )
    return ranked


class AccessPaginator(ReportView.paginator_class):
    verbose_name = _("daily record")
    verbose_name_plural = _("daily records")


class AgentAccessReportView(ReportView):
    page_title = _("Agent access")
    header_icon = "globe"
    index_url_name = "agentmd_report"
    template_name = "wagtail_markdown_agents/report.html"
    results_template_name = "wagtail_markdown_agents/report_results.html"
    permission_policy = REPORT_PERMISSION
    permission_required = "view"
    paginate_by = 50
    paginator_class = AccessPaginator
    # This report has no spreadsheet export UI. Ignore the inherited export parameter.
    FORMATS = {}

    @cached_property
    def dimensions(self):
        queryset = AgentAccess.objects.all()
        ids = list(queryset.order_by("page_id").values_list("page_id", flat=True).distinct())
        titles = dict(Page.objects.filter(pk__in=ids).values_list("pk", "title"))
        agents = list(queryset.order_by("agent").values_list("agent", flat=True).distinct())
        return ids, titles, agents

    @cached_property
    def report_form(self):
        ids, titles, agents = self.dimensions
        return ReportFilterForm(
            self.request.GET,
            today=datetime.now(UTC).date(),
            agents=agents,
            pages=[(str(pk), page_label(pk, titles)) for pk in ids],
        )

    @cached_property
    def category_map(self):
        return get_agent_categories()

    @cached_property
    def agent_intents(self):
        # One hook snapshot per request, including all historical labels. Reuse it
        # for the SQL intent filter, chart aggregation, tiles and displayed rows.
        return {
            agent: categorise_agent(agent, categories=self.category_map)
            for agent in self.dimensions[2]
        }

    def intent_for_agent(self, agent):
        # A new label can arrive while the report is loading. Use the same map.
        if agent not in self.agent_intents:
            self.agent_intents[agent] = categorise_agent(agent, categories=self.category_map)
        return self.agent_intents[agent]

    def filter_url(self, **changes):
        params = self.request.GET.copy()
        params.pop("p", None)
        # A conflicting agent may have been dropped when the operator was selected.
        # Do not resurrect that stale query value in card and clear-filter links.
        if self.report_form.is_valid() and not self.report_form.cleaned_data["agent"]:
            params.pop("agent", None)
        for key, value in changes.items():
            if value:
                params[key] = value
            else:
                params.pop(key, None)
        query = urlencode(params, doseq=True)
        return f"{self.request.path}?{query}" if query else self.request.path

    def get_queryset(self):
        queryset = AgentAccess.objects.all()
        if not self.report_form.is_valid():
            return queryset.none()
        data = self.report_form.cleaned_data
        queryset = queryset.filter(access_date__range=(data["start"], data["end"]))
        if data["page_id"]:
            queryset = queryset.filter(page_id=int(data["page_id"]))
        if data["agent"]:
            queryset = queryset.filter(agent=data["agent"][len("label:") :])
        if data["operator"]:
            queryset = queryset.filter(
                agent__in=[
                    agent
                    for agent in self.dimensions[2]
                    if operator_for_agent(agent) == data["operator"]
                ]
            )
        if data["method"]:
            queryset = queryset.filter(access_method=data["method"])
        if data["intent"]:
            queryset = queryset.filter(
                agent__in=[
                    agent
                    for agent, intent in self.agent_intents.items()
                    if intent == data["intent"]
                ]
            )
        return queryset.order_by("-access_date", "page_id", "agent", "access_method", "pk")

    def decorate_paginated_queryset(self, object_list):
        for row in object_list:
            row.page_label = page_label(row.page_id, self.dimensions[1])
            row.intent = self.intent_for_agent(row.agent)
            row.intent_label = INTENT_LABELS[row.intent]
        return object_list

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = None
        if self.report_form.is_valid():
            data = self.report_form.cleaned_data
            summary = summarise(self.object_list, data["start"], data["end"], self.intent_for_agent)
            agent_counts = summary.pop("agents")
            operator_counts = Counter()
            operator_agents = defaultdict(Counter)
            for agent, count in agent_counts.items():
                key = operator_for_agent(agent)
                operator_counts[key] += count
                operator_agents[key][agent] += count
            cards = []
            keys = sorted(
                (key for key in operator_counts if key != "unattributed"),
                key=lambda key: (-operator_counts[key], OPERATOR_NAMES[key].casefold()),
            )
            if operator_counts["unattributed"]:
                keys.append("unattributed")
            for key in keys:
                agents = sorted(
                    operator_agents[key].items(), key=lambda item: (-item[1], item[0].casefold())
                )
                active = data["operator"] == key
                cards.append(
                    {
                        "key": key,
                        "name": OPERATOR_NAMES.get(key, _("Unattributed")),
                        "count": operator_counts[key],
                        "agents": agents[:5],
                        "more": max(0, len(agents) - 5),
                        "active": active,
                        "url": self.filter_url(
                            operator="" if active else key,
                            agent=""
                            if not active
                            and data["agent"]
                            and operator_for_agent(data["agent"][6:]) != key
                            else data["agent"],
                        ),
                    }
                )
            summary["operator_cards"] = cards
            summary["agent_leader"] = leader(
                agent_counts,
                empty=_("No identified agents in this range"),
                eligible=lambda agent: (
                    bool(agent.strip()) and agent.casefold() not in ACCESS_METHODS
                ),
            )
            summary["operator_leader"] = leader(
                operator_counts,
                empty=_("No attributed operators in this range"),
                label_for=lambda key: OPERATOR_NAMES[key],
                eligible=lambda key: key != "unattributed",
            )
            page_rows = list(
                self.object_list.order_by()
                .values("page_id")
                .annotate(total=Sum("count"))
                .order_by("-total", "page_id")[:50]
            )
            page_counts = {row["page_id"]: row["total"] for row in page_rows}
            summary["top_pages"] = top_pages(page_rows, summary["tiles"][0]["count"])
            for row in summary["top_pages"]:
                row["title"] = self.dimensions[1].get(
                    row["page_id"], page_label(row["page_id"], self.dimensions[1])
                )
                row["url"] = self.filter_url(page_id=row["page_id"], page_search="")
            summary["page_leader"] = leader(
                page_counts,
                empty=_("No pages requested in this range"),
                label_for=lambda pk: page_label(pk, self.dimensions[1]),
            )
            if len(page_rows) == 50 and page_rows[-1]["total"] == page_rows[0]["total"]:
                summary["page_leader"]["truncated"] = True
            for name, key in summary["page_leader"].get("names", []):
                summary.setdefault("page_links", []).append(
                    (name, self.filter_url(page_id=key, page_search=""))
                )
            for name, key in summary["agent_leader"].get("names", []):
                summary.setdefault("agent_links", []).append(
                    (name, self.filter_url(agent=f"label:{key}"))
                )
            for name, key in summary["operator_leader"].get("names", []):
                summary.setdefault("operator_links", []).append(
                    (name, self.filter_url(operator=key))
                )
            summary["clear_operator_url"] = self.filter_url(operator="")
            summary["clear_page_url"] = self.filter_url(page_id="", page_search="")
            if data["page_id"]:
                page_id = int(data["page_id"])
                summary["filtered_page_title"] = self.dimensions[1].get(
                    page_id, page_label(page_id, self.dimensions[1])
                )
            if data["start"] and data["end"]:
                summary["method_rows"] = list(
                    self.object_list.order_by()
                    .values("agent", "access_method")
                    .annotate(requests=Sum("count"), unique_pages=Count("page_id", distinct=True))
                    .order_by("-requests", "agent", "access_method")
                )
        context.update(
            report_form=self.report_form, summary=summary, has_history=bool(self.dimensions[0])
        )
        return context
