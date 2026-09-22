"""Read-only Wagtail reporting over the daily access counters."""

import math
from datetime import UTC, date, datetime, timedelta

from django import forms
from django.db.models import F, Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.admin.views.reports import ReportView
from wagtail.models import Page
from wagtail.permission_policies import ModelPermissionPolicy

from .models import AgentAccess
from .stats import ACCESS_METHODS, INTENT_CATEGORIES, categorise_agent, get_agent_categories

REPORT_PERMISSION = ModelPermissionPolicy(AgentAccess)
INTENT_LABELS = {
    "on-demand": _("On-demand (estimate)"),
    "search": _("Search"),
    "training": _("Training"),
    "unknown": _("Unknown"),
}


def page_label(page_id, titles):
    if page_id in titles:
        return f"{titles[page_id]} (#{page_id})"
    return _("Deleted page #%(id)s") % {"id": page_id}


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
    page_id = forms.ChoiceField(label=_("Page"), required=False)
    agent = forms.ChoiceField(label=_("Agent"), required=False)
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
        preset = data.get("preset") or ("custom" if data.get("start") or data.get("end") else "30")
        data["preset"] = preset
        if preset in {"7", "30", "90", "365"}:
            data["start"] = (today - timedelta(days=int(preset) - 1)).isoformat()
            data["end"] = today.isoformat()
        super().__init__(data)
        self.fields["page_id"].choices = [("", _("All pages")), *pages]
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


def points(values, maximum, *, width=900, height=220):
    """Numeric SVG coordinates only; no user content enters SVG attributes."""
    if len(values) == 1:
        values = values * 2
    return " ".join(
        f"{i * width / max(1, len(values) - 1):.2f},{height - value * height / max(1, maximum):.2f}"
        for i, value in enumerate(values)
    )


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
    for row in aggregates:
        counts[row["bucket"]][intent_for_agent(row["agent"])] += row["total"]
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
                "points": points(values, max(values), width=160, height=32),
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
    }


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
        context.update(
            report_form=self.report_form, summary=summary, has_history=bool(self.dimensions[0])
        )
        return context
