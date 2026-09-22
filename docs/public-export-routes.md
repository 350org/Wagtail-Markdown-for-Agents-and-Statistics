# Public managed export routes

The URLconf implements the direct retrieval portion of #72 and request containment
checks from #68. It serves previously published managed objects through Django's
storage API. It never generates content during a request.

## Install the routes

Include the package before Wagtail's catch-all in the project's URLconf:

```python
from django.urls import include, path
from wagtail import urls as wagtail_urls

urlpatterns = [
    # Keep existing admin, document and application routes here.
    path("markdown/", include("wagtail_markdown_agents.urls")),
    path("", include(wagtail_urls)),
]
```

The sandbox uses `/markdown/`. A project may choose another prefix or include at
`""` to expose `/llms.txt`, `/manifest.json` and the mirrored `.md` tree at the site
root. The package claims only those two filenames and paths ending in `.md`;
ordinary HTML routes continue to the rest of the URLconf. Choose a prefix that does
not conflict with existing project routes and include the package once per URLconf.

| Named route | Example with the sandbox prefix |
| --- | --- |
| `wagtail_markdown_agents:export` (`export_path` argument) | `/markdown/blog/post.md` or `/markdown/blog/index.md` |
| `wagtail_markdown_agents:llms_txt` | `/markdown/llms.txt` |
| `wagtail_markdown_agents:manifest` | `/markdown/manifest.json` |

Generate a page with the existing Python API after applying package migrations:

```python
from wagtail_markdown_agents.export.writer import FileWriter
from wagtail_markdown_agents.public_urls import export_url

record = FileWriter().generate(page)
url = export_url(record)
```

`export_url` uses the record's owning Wagtail Site, its configured `root_url`, and
the included named route. Configure the Site hostname/port to match the public
origin (port 443 gives HTTPS). The helper preserves hook-relocated paths and accepts
`urlconf=` for offline generation with a custom project URLconf. It checks that the
record still owns its published pointer; callers building listings must also check
current eligibility and availability. Formatting a URL never authorises a read.

`alternate_url(record)` chooses a page's canonical HTML URL with
`output_format=md` when `NEGOTIATE_QUERY_PARAM` is enabled, otherwise its explicit
export URL. Aggregates always use explicit URLs. The same choice is advertised by the
HTML discovery headers and template tag in the [discovery guide](discovery-headers.md).
Query/Accept/UA negotiation at the canonical URL is implemented by the middleware
described in the [negotiation guide](negotiation.md). `route_url(site, path)` formats
an explicit URL for any site-relative artefact path and `query_alternate(url)`
appends the query trigger; neither checks ownership or existence.

## Read and revocation behaviour

GET returns stored bytes as `text/markdown`, `text/plain` for `llms.txt`, or
`application/json` for the manifest, all with UTF-8 charset. HEAD has the same
headers, closes the opened storage stream and returns no body. Other methods return
405. Missing, stale, restricted, excluded and unowned artefacts return 404.
Response sizing uses only the opened stream, never the backend filename or local
filesystem metadata. Nonseekable streams omit the optional Content-Length header;
no private storage filename is exposed in Content-Disposition.

The request Host is validated against `ALLOWED_HOSTS`, then matched to Wagtail's
Site. A fallback to a default Site with a different hostname is rejected. The site
must be enabled by export policy. Logical paths are checked for containment before
storage IO; request paths are never joined to backend keys. Reads use the current
site's ownership row and recorded key, bound to the exact immutable generation.
Raw `.objects` keys, traversal, percent escapes remaining after URL decoding,
backslashes, controls and overlong paths cannot reach storage.

The writer checks current published state and policy before and after opening the
stream. A changed listing dependency makes the old index/manifest unavailable,
including when a child becomes private and physical cleanup has not run yet.
Already-open streams retain the writer's documented complete-generation semantics.
Storage objects must remain private; only these checked routes expose their bytes.

`serve_export(request, logical_path, access_method=...)` is the shared response
function used by the negotiation middleware. It returns `None` on a miss/veto so
negotiated requests fall through to HTML; the explicit route maps that result to
404. Both entry points perform site, ownership and current-state checks.

## Response hooks and notifications

Successful responses default to:

- `Cache-Control: private, no-store, max-age=0`
- `Vary: Accept, User-Agent`
- `X-Markdown-Source`: canonical HTML URL for page-owned exports; omitted for aggregates
- `Content-Signal`: `ai-input=yes, search=yes`

`CONTENT_SIGNAL` is an operator policy statement enabling AI input and search in
that header; it makes no `ai-train` statement. Set it to `""` to omit the header or
provide another string for the project's policy. These headers do not replace a
deployment's CDN/cache configuration; the [CDN and cache guide](cdn-caching.md)
explains when each access method may be cached.

Two Wagtail hooks run on every selected request, in normal hook order:

```python
from wagtail import hooks


@hooks.register("markdown_serve_allowed")
def allow_request(request, artifact, site):
    # Return False to veto. Aggregates have artifact.page_id == None.
    return request.GET.get("disable_markdown") != "yes"


@hooks.register("construct_markdown_response_headers")
def configure_headers(headers, request, context):
    # context: page (None for aggregates), site, logical path, access_method.
    headers["X-Accel-Expires"] = "0"
    headers["X-LiteSpeed-Cache-Control"] = "no-cache"
```

The serving veto is request-specific and never cached; it cannot override failed
export eligibility. The header hook mutates the mapping in place; its return value
is ignored. `None` or `""` omits a header, including default headers. Names must be
valid HTTP tokens and nonempty values must be strings without control characters.
Invalid configuration raises `ImproperlyConfigured` and closes the stream. A hook
that weakens cache headers takes responsibility for the resulting cache behaviour.

`markdown_served` is emitted once after successful **page GET response selection**,
with `request`, `page_id`, `site_id`, logical `path` and `access_method`. Direct routes
use `export-url`. HEAD, aggregates, vetoes and failed reads emit nothing. A page-owned
directory index counts as a page read; a standalone navigation index does not.
This is a best-effort notification, not proof of completed client receipt. Receiver
failures are logged without failing the response. The
[statistics receiver](agent-access-stats.md) (#32/#33) records daily counters from
this signal, excluding requests marked as previews.

## Remaining integration

The tests exercise direct link traversal using generated URL helpers and supplied
aggregate content on filesystem and restricted fake remote storage. Automatic
[link rewriting](internal-links.md) (#14) now uses these URL helpers.
[Root/directory indexes](indexes.md) (#20) now build checked listings through those
URLs. [`llms.txt` generation](llms-txt.md) (#21) provides the site discovery entry point.
Manifest generation (#22) and lifecycle receivers and
commands (#23/#24/#69/#70) are separate work. [Negotiation](negotiation.md)
(#25/#26/#30) now serves the same records at canonical page URLs with the
`query-param`, `accept-header` and `ua` labels, and
[discovery headers](discovery-headers.md) (#27/#28) advertise them on HTML;
persistent [statistics](agent-access-stats.md) (#32/#33) count page GETs. A live S3-compatible backend and CDN
deployment still need their own integration validation.
