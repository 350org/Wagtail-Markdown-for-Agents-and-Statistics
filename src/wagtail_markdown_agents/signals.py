"""Custom signals — the port of the WP plugin's public actions."""

import django.dispatch

#: After committed publication. kwargs: page (None for aggregates), page_id,
#: site_id, path (logical), storage_key (actual), storage_alias.
markdown_generated = django.dispatch.Signal()

#: After physical deletion and DB commit, including deferred cleanup retries.
#: kwargs: page_id (None for aggregates), site_id, path, storage_key, storage_alias.
#: Replacing bytes at the same logical path does not emit a deletion event.
markdown_deleted = django.dispatch.Signal()

#: Successful page Markdown GET response selection (not completed transfer).
#: kwargs: request, page_id, site_id, path (logical), access_method. Never emitted
#: for HEAD, aggregate downloads or failed/vetoed reads. Best effort; the stats
#: receiver records one daily increment, excluding requests marked as previews.
markdown_served = django.dispatch.Signal()

#: Sent when an internal link cannot be rewritten to a .md target.
#: kwargs: url, reason ("not_found" | "ineligible"), once per parsed URL per run.
#: Missing/stale stored exports count as not_found. Ignored external, asset and
#: query-dependent URLs do not emit. Receiver failures are logged best effort.
link_unresolved = django.dispatch.Signal()
