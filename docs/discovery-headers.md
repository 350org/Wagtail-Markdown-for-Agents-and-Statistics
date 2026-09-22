# HTML discovery headers and template tag

`AgentMarkdownMiddleware` implements the response phase of #27 and the
`{% agent_markdown_link %}` template tag implements #28. Browsers keep receiving
HTML; when the page has a current export, that HTML tells agents where the
Markdown is. Nothing is generated during a request and nothing here authorises a
Markdown read: serving always re-runs the checked path described in the
[negotiation guide](negotiation.md).

## What an HTML response gains

On an HTML `200` response to a GET or HEAD request at a page's canonical URL,
outside previews, the middleware appends

```http
Link: <https://example.org/blog/my-post/?output_format=md>; rel="alternate"; type="text/markdown"
Vary: Accept
```

Existing `Link` values are kept and ours is appended; `Vary` is merged, so
`Vary: Cookie` becomes `Vary: Cookie, Accept`. Only `Accept` is added — HTML
deliberately does not vary on `User-Agent` (see [Caching](#caching-and-the-user-agent-trade-off)).

The advertised URL is the page's canonical URL with `output_format=md` while
`NEGOTIATE_QUERY_PARAM` is enabled, otherwise the page's explicit export route
(`/markdown/blog/my-post.md` with the sandbox prefix). The choice is shared with
`alternate_url(record)` in the [public route guide](public-export-routes.md).
When query negotiation is disabled and the package URLconf is not included there
is no URL to advertise, so no header is added; system check `E006` reports that
configuration.

`LINK_HEADER = False` disables the response phase entirely for hosts that cannot
afford it. The template tag is unaffected by that setting.

Non-page routes (admin, documents, API, the explicit export routes), non-`200`
responses, non-HTML responses, negotiated Markdown responses, RoutablePage
sub-routes, paths without a trailing slash and requests whose host does not match
a policy-enabled site are never given discovery headers.

## When a page is advertised

A page is advertised only when all of the following hold on resolution:

- the request resolves to Wagtail's page route and the routed page's own URL equals
  the request path;
- the request host matches a policy-enabled Wagtail Site;
- `ExportPolicy.is_eligible(page)` is true (live, enabled type, no view
  restriction, not excluded, not vetoed);
- the page's published export record exists at the path the policy computes now,
  including any `markdown_export_path` relocation — so `blog.md` versus
  `blog/index.md` and hook-relocated files are found through the record, and a
  request path is never turned into a storage path;
- that record's actual storage key exists in the configured backend.

Resolution also checks the record's source and dependency state, as serving does.
An export made obsolete by changed content, rendering settings or hierarchy
dependencies is not advertised on a fresh resolution, even if its file remains
in storage.

A page whose export is missing, revoked, replaced by a different path, private,
unpublished or excluded gets a plain HTML response with no `Link` and no `Vary:
Accept` contribution.

## Caching and invalidation

Resolution costs page routing, policy queries and a storage existence probe (an
S3-style HEAD), so results — hits and misses alike — are cached in Django's default
cache for `DISCOVERY_CACHE_TIMEOUT` seconds (default `60`; `0` disables caching).

The cache key contains the site, the canonical request path, the export storage
identity and the site's export publication version. Every generation, deletion,
relocation and parent leaf/index transition goes through the writer and increments
that version, so those events invalidate affected entries immediately, in every
process and without a shared cache backend. Changes that publish nothing — a
removed `markdown_export_path` hook, a storage object deleted behind the package's
back, a code-level policy change — become visible when the entry expires. A
per-process `LocMemCache` is therefore sufficient; a shared cache only reduces
repeated resolution across workers.

The cache advertises exports only. A negotiated request or an explicit export
route never consults it: they re-run ownership, eligibility, veto and storage
checks on every read, so a stale advertisement can at worst produce an HTML
fallback or a `404`, never a wrong file.

## The `construct_markdown_html_headers` hook

```python
from wagtail import hooks


@hooks.register("construct_markdown_html_headers")
def adjust(values, request, context):
    if request.path.startswith("/campaigns/"):
        values["Link"] = None  # omit ours; an existing Link is untouched
    values["X-Robots-Tag"] = "noai"  # add or override another header
```

`values` starts as `{"Link": "<…>; rel=\"alternate\"; type=\"text/markdown\"",
"Vary": "Accept"}`. `context` has `site`, `path` (the canonical request path),
`alternate_url`, `export_path` (site-relative, such as `blog/my-post.md`) and
`page`, loaded lazily so hooks that ignore it cost no query. Setting a value to
`None` or `""` omits it; headers already on the HTML response are never removed.
`Link` is appended to an existing value and `Vary` merged; any other name is set
on the response. Names must be HTTP tokens and values strings without control
characters, otherwise `ImproperlyConfigured` is raised. Hooks run by `order`, then
registration order, and run after the cache lookup on every advertised response.

## The `{% agent_markdown_link %}` template tag

```django
{% load wagtail_markdown_agents %}
<head>
  …
  {% agent_markdown_link %}
</head>
```

Emits `<link rel="alternate" type="text/markdown" href="…">` for the `page` in
the template context (or an explicit argument, `{% agent_markdown_link other %}`)
and nothing otherwise. It shares the middleware's site, policy, record and storage
resolution, its cache and its alternate-URL choice, so the element appears exactly
when the header does. It emits nothing during previews and for missing, revoked or
ineligible exports, and the URL is HTML-escaped. Without a `request` in the
context it resolves the page's own site.

## Settings

| Setting | Default | Effect |
| --- | --- | --- |
| `LINK_HEADER` | `True` | Add discovery headers to eligible HTML responses. |
| `DISCOVERY_CACHE_TIMEOUT` | `60` | Seconds to cache resolution per site, path and storage; `0` disables. |
| `NEGOTIATE_QUERY_PARAM` | `True` | Advertise the canonical URL with `output_format=md`; when off, the explicit route. |

Neither `LINK_HEADER` nor `DISCOVERY_CACHE_TIMEOUT` affects rendered documents, so
changing them never invalidates existing exports.

## Caching and the User-Agent trade-off

`Vary: Accept` lets a shared cache store the HTML and the Markdown variants of a
canonical URL separately for clients that negotiate through `Accept`. HTML
deliberately does not carry `Vary: User-Agent`: that would fragment the cache by
every browser string. The consequence is that an HTML response stored by a CDN or
reverse proxy can be returned to a known agent that identifies itself only through
its User-Agent, because the cache never asks Django. Deployments that rely on UA
negotiation need a cache bypass or variant rule for known agents, and the live
verification (#59) must test cached HTML followed by a UA-only fetch as well as the
reverse order; the [CDN and cache guide](cdn-caching.md) sets out both orderings and
the bypass rules per cache layer. Negotiated Markdown responses remain
`private, no-store` and are never shared-cached.
