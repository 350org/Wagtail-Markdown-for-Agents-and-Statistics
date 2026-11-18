"""Shared scope validation and read-only inspection for operator commands (#24)."""

from dataclasses import dataclass

from django.apps import apps
from django.core.management.base import CommandError
from wagtail.models import Page, Site

from ..export.policy import ExportPolicy
from ..export.state import StaleBuild, site_freshness
from ..export.writer import StorageConfigurationChanged, _after_commit_required
from ..models import ExportArtifact, ExportFile, ExportScope
from ..rendering.page import PageRenderError, _require_supported_page, unsupported_reason

#: A larger selection in one site is checked against one reading of the site
#: rather than page by page (#74).
BATCH_INSPECTION = 50


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
    known_sites = {site.pk: site for site in Site.objects.all()}
    for page in pages.order_by("pk").specific():
        owner = _owner_site(page, known_sites)
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


def _owner_site(page, sites):
    """``page.get_site()`` without its query per page, keeping project overrides.

    Wagtail's ``get_site`` reads the site row again for every page; selecting a
    large site made one query per page before any page was checked (#74).
    """
    if type(page).get_site is not Page.get_site:
        return page.get_site()
    parts = page.get_url_parts()
    return sites.get(parts[0]) if parts else None


def inspect_page(page_id, writer, *, verify_file=True):
    """Return availability without rendering, allocating records or repairing IO.

    ``verify_file`` also opens the recorded storage object, so a lost file
    reads as ``unavailable``; without it the database record is trusted.
    """
    page = Page.objects.filter(pk=page_id).specific().first()
    if page is None:
        return "missing_page", None, None
    policy = ExportPolicy()
    if not policy.is_eligible(page):
        return "ineligible", page, None
    try:
        _require_supported_page(page)
    except PageRenderError:
        return "unsupported", page, None
    path = policy.relative_path(page)
    site = policy.site_for_page(page)
    record = (
        ExportArtifact.objects.filter(page_id=page_id, scope__site_id=site.pk)
        .select_related("scope", "file")
        .defer("scope__manifest_state")
        .first()
    )
    if record is None:
        return "missing", page, path
    # The page's own document only: navigation is rebuilt by the site's
    # finalisation, and checking it here read the whole site per index (#69).
    if record.logical_path != path or not writer.is_current(record, own=True):
        return "unavailable", page, path
    if not _file_readable(writer, record.file, verify_file):
        return "unavailable", page, path
    stale_before = record.scope.stale_before
    if stale_before is not None and record.published_at < stale_before:
        return "outdated", page, path
    return "current", page, path


def current_pages(site, page_ids, writer, *, verify_files=False):
    """The pages of ``page_ids`` whose exports in ``site`` are current (#74).

    The same answer as ``inspect_page(...)`` returning ``"current"``, read from
    one reading of the site and one query for its export records instead of
    about 25 queries per page. A page not confirmed here may still be current:
    inspect it on its own. ``verify_files`` opens each confirmed page's stored
    object, one storage request per page.
    """
    try:
        freshness = site_freshness(site.pk)
    except StaleBuild:
        return set()
    stale_before = (
        ExportScope.objects.filter(site_id=site.pk).values_list("stale_before", flat=True).first()
    )
    records = ExportArtifact.objects.filter(
        scope__site_id=site.pk, page_id__isnull=False
    ).select_related("file")
    by_page, repeated = {}, set()
    for record in records:
        if record.page_id in by_page:
            repeated.add(record.page_id)  # Leave anything unusual to inspect_page.
        by_page[record.page_id] = record
    supported = {}
    current = set()
    for page_id in set(page_ids) - repeated:
        record, page = by_page.get(page_id), freshness.snapshot.pages.get(page_id)
        if record is None or page is None:
            continue
        if freshness.pages.get(page_id) != (record.logical_path, record.source_state):
            continue
        if stale_before is not None and record.published_at < stale_before:
            continue
        model = type(page)
        if model not in supported:
            supported[model] = not unsupported_reason(model)
        if not supported[model]:
            continue
        if not _file_readable(writer, record.file, verify_files):
            continue
        current.add(page_id)
    return current


def _file_readable(writer, file, verify):
    """Whether ``file`` is in the configured storage, opening it only if ``verify``.

    Without opening anything, a file recorded under a different storage
    configuration (a new bucket, region or location) is not readable, so the
    next run rebuilds it rather than trusting the old record (#74).
    """
    try:
        if not verify:
            writer._backend(file)
            return True
        with writer._open_file(file):
            return True
    except (FileNotFoundError, StorageConfigurationChanged):
        return False


def require_autocommit():
    try:
        _after_commit_required()
    except RuntimeError as exc:
        raise CommandError(str(exc)) from exc


def report(command, counts, *, dry_run=False):
    prefix = "Dry run: " if dry_run else ""
    command.stdout.write(prefix + " ".join(f"{key}={value}" for key, value in counts.items()))
