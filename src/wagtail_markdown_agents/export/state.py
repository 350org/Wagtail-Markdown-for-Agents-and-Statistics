"""Fresh publication inputs, independent of the caller's page instance."""

from dataclasses import dataclass

from wagtail.models import Page, Site

from ..models import PageAgentSettings
from ..settings import DEFAULTS, NON_CONTENT_SETTINGS, get_setting
from .policy import ExportPolicy
from .snapshot import SiteSnapshot
from .storage import digest


class StaleBuild(ValueError):
    """Captured publication inputs are obsolete; rebuild from fresh state."""


def content_config():
    """The package settings that change rendered documents."""
    # Discovery copy is site-dependent metadata; AUTO_GENERATE controls
    # scheduling only. Neither changes the rendered leaf document.
    return {key: get_setting(key) for key in DEFAULTS if key not in NON_CONTENT_SETTINGS}


def page_state(page_id, site_id=None, *, snapshot=None, config=None):
    """The page, its site, export path and publication state digest.

    ``snapshot`` and ``config`` come from one :func:`site_freshness` call when
    many pages of a site are checked at once; both are read fresh otherwise.
    """
    page = snapshot.pages.get(page_id) if snapshot else Page.objects.filter(pk=page_id).first()
    policy = ExportPolicy(snapshot)
    if page is None or not policy.is_eligible(page.specific):
        raise StaleBuild(f"Page {page_id} is no longer live and eligible")
    site = policy.site_for_page(page)
    if site_id is not None and site.pk != site_id:
        raise StaleBuild(f"Page {page_id} moved to another site")
    path = policy.relative_path(page)
    extra = (
        ([snapshot.settings[page_id]] if page_id in snapshot.settings else [])
        if snapshot
        else list(
            PageAgentSettings.objects.filter(page_id=page_id).values(
                "excluded", "extra_frontmatter"
            )
        )
    )
    state = digest(
        {
            "revision": page.live_revision_id,
            "published": [page.first_published_at, page.last_published_at],
            "url_path": page.url_path,
            "path": path,
            "site": [site.pk, site.hostname, site.port, site.root_page_id],
            "extra": extra,
            "config": content_config() if config is None else config,
        }
    )
    return page.specific, site, path, state


@dataclass(frozen=True)
class SiteFreshness:
    """One reading of a site's publication inputs, for checking many exports.

    Checking each export against its own fresh reading costs a site scan per
    page-owned index, so listing a large site's exports grew quadratically
    (#66). Use one reading per listing; never keep it beyond that operation.
    """

    site: Site
    snapshot: SiteSnapshot
    config: dict
    state: str


def site_freshness(site_id):
    site = Site.objects.filter(pk=site_id).select_related("root_page").first()
    if site is None:
        raise StaleBuild(f"Site {site_id} no longer exists")
    snapshot = SiteSnapshot(site)
    config = content_config()
    states = []
    for page in snapshot.pages.values():
        try:
            _, _, path, state = page_state(page.pk, site_id, snapshot=snapshot, config=config)
        except StaleBuild:
            continue
        states.append([page.pk, path, state])
    state = digest(
        {
            "site": [site.pk, site.hostname, site.port, site.root_page_id, site.site_name],
            "llms_description": get_setting("LLMS_TXT_DESCRIPTION"),
            "pages": states,
        }
    )
    return SiteFreshness(site, snapshot, config, state)


def site_state(site_id):
    fresh = site_freshness(site_id)
    return fresh.site, fresh.state
