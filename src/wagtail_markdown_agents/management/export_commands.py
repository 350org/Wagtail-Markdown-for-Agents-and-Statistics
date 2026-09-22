"""Shared scope validation and read-only inspection for operator commands (#24)."""

from dataclasses import dataclass

from django.apps import apps
from django.core.management.base import CommandError
from wagtail.models import Page, Site

from ..export.policy import ExportPolicy
from ..export.writer import _after_commit_required
from ..models import ExportArtifact, ExportFile
from ..rendering.page import PageRenderError, _require_supported_page


def add_scope_arguments(parser):
    parser.add_argument("--page-id", type=int, help="Select one page by ID (not its descendants)")
    parser.add_argument("--type", help="Select an exact page model, e.g. blog.BlogPage")
    parser.add_argument("--site", help="Select a site hostname; combined filters intersect")


@dataclass(frozen=True)
class Selection:
    page_ids: tuple
    site_ids: tuple
    pages_by_site: dict


def select(options, *, operation):
    """Resolve scope before any publication, cleanup, locks or confirmation."""
    deleting = operation == "delete"
    generating = operation in {"generate", "indexes"}
    page_id, label, hostname = (options.get(key) for key in ("page_id", "type", "site"))
    if any(value is not None and not value.strip() for value in (label, hostname)):
        raise CommandError("Type and site filters must not be empty.")
    everything = options.get("all", False)
    if deleting:
        if not (everything or page_id is not None or label or hostname):
            raise CommandError("Select --page-id, --type, --site or --all for deletion.")
        if everything and (page_id is not None or label or hostname):
            raise CommandError("--all cannot be combined with page/type/site filters.")
    pages = Page.objects.all() if page_id is not None else Page.objects.filter(depth__gt=1)
    if page_id is not None:
        if page_id <= 0:
            raise CommandError("--page-id must be a positive page ID.")
        pages = pages.filter(pk=page_id)
        if not pages.exists():
            if deleting and not label and ExportFile.objects.filter(page_id=page_id).exists():
                pages = Page.objects.none()  # Ownership can outlive the CMS page.
            else:
                raise CommandError(f"Page {page_id} does not exist.")
    if label:
        try:
            model = apps.get_model(label)
        except (LookupError, ValueError) as exc:
            raise CommandError(f"Unknown page type {label!r}; use app_label.ModelName.") from exc
        if not issubclass(model, Page) or model._meta.abstract:
            raise CommandError(f"{label!r} is not a concrete Page type.")
        if generating:
            try:
                _require_supported_page(model())
            except PageRenderError as exc:
                raise CommandError(f"Type {label!r} is unsupported: {exc}") from exc
        pages = pages.filter(
            content_type__app_label=model._meta.app_label,
            content_type__model=model._meta.model_name,
        )
    sites = list(Site.objects.select_related("root_page").order_by("pk"))
    if hostname:
        sites = [site for site in sites if site.hostname.lower() == hostname.lower()]
        if len(sites) != 1:
            raise CommandError(
                f"Site hostname {hostname!r} must match exactly one configured site."
            )
        if generating and not ExportPolicy.site_enabled(sites[0]):
            raise CommandError(f"Site {hostname!r} is disabled by the export policy.")
    elif not deleting:
        sites = [site for site in sites if ExportPolicy.site_enabled(site)]
    site_ids = {site.pk for site in sites}
    if deleting and page_id is None and not label:
        return Selection((), tuple(sorted(site_ids)), {})
    selected = []
    pages_by_site = {}
    for page in pages.order_by("pk").specific():
        owner = page.get_site()
        if (owner is None or owner.pk not in site_ids) and not deleting:
            continue
        if generating and page_id is not None:
            try:
                _require_supported_page(page)
            except PageRenderError as exc:
                raise CommandError(f"Page {page_id} is unsupported: {exc}") from exc
        selected.append(page.pk)
        if owner is not None:
            pages_by_site.setdefault(owner.pk, []).append(page.pk)
    if page_id is not None and page_id not in selected:
        owned = ExportFile.objects.filter(page_id=page_id)
        if hostname:
            owned = owned.filter(scope__site_id__in=site_ids)
        if deleting and not label and owned.exists():
            selected.append(page_id)
        else:
            raise CommandError(f"Page {page_id} does not match the selected type/site scope.")
    # Page/type selection rebuilds only the sites actually containing those pages.
    if not deleting and (page_id is not None or label):
        site_ids = set(pages_by_site)
    return Selection(
        tuple(selected),
        tuple(sorted(site_ids)),
        {site_id: tuple(ids) for site_id, ids in pages_by_site.items()},
    )


def inspect_page(page_id, writer):
    """Return availability without rendering, allocating records or repairing IO."""
    page = Page.objects.filter(pk=page_id).specific().first()
    if page is None:
        return "missing_page", None, None
    policy = ExportPolicy()
    if not page.live_revision_id or not policy.is_eligible(page):
        return "ineligible", page, None
    try:
        _require_supported_page(page)
    except PageRenderError:
        return "unsupported", page, None
    path = policy.relative_path(page)
    site = policy.site_for_page(page)
    record = ExportArtifact.objects.filter(page_id=page_id, scope__site_id=site.pk).first()
    if record is None:
        return "missing", page, path
    try:
        with writer.open(path, site_id=site.pk, file_id=record.file_id):
            pass
    except FileNotFoundError:
        return "unavailable", page, path
    return "current", page, path


def require_autocommit():
    try:
        _after_commit_required()
    except RuntimeError as exc:
        raise CommandError(str(exc)) from exc


def report(command, counts, *, dry_run=False):
    prefix = "Dry run: " if dry_run else ""
    command.stdout.write(prefix + " ".join(f"{key}={value}" for key, value in counts.items()))
