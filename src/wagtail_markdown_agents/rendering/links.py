"""Source-preserving Markdown links to currently available owned exports (#14)."""

import logging
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit

from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.urls import Resolver404, resolve
from markdown_it import MarkdownIt
from markdown_it.rules_inline import autolink, image, link
from wagtail.models import Page

from ..export.paths import ExportPathError
from ..export.state import StaleBuild, page_state
from ..export.writer import FileWriter
from ..models import ExportArtifact
from ..public_urls import export_url
from ..settings import get_setting
from ..signals import link_unresolved
from .context import render_context

logger = logging.getLogger(__name__)


class LinkResolver:
    """One render's URL/result cache; never reused across builds or requests."""

    def __init__(self, page, context):
        self.site = context.get("site")
        self.base = page.full_url
        self.urls = {}
        self.targets = {}

    def resolve(self, url):
        if url not in self.urls:
            replacement, reason = self._resolve(url)
            self.urls[url] = replacement
            if reason:
                for receiver, result in link_unresolved.send_robust(
                    sender=rewrite_links, url=url, reason=reason
                ):
                    if isinstance(result, Exception):
                        logger.error("Unresolved-link receiver %r failed: %s", receiver, result)
        return self.urls[url]

    def _internal(self, parts):
        origin = urlsplit(self.site.root_url)
        return (
            parts.scheme in {"http", "https"}
            and not parts.username
            and not parts.password
            and parts.hostname == origin.hostname
            and (parts.port or (443 if parts.scheme == "https" else 80))
            == (origin.port or (443 if origin.scheme == "https" else 80))
        )

    def _ignored(self, parts):
        # Only the negotiation query has semantics owned by this package.
        query = parse_qsl(parts.query, keep_blank_values=True)
        if parts.query and (
            not query
            or not get_setting("NEGOTIATE_QUERY_PARAM")
            or any(
                key != "output_format" or value not in {"md", "markdown"} for key, value in query
            )
        ):
            return True
        for name in ("MEDIA_URL", "STATIC_URL"):
            prefix = getattr(settings, name, "")
            if prefix:
                media = urlsplit(urljoin(self.site.root_url + "/", prefix))
                if media.netloc == parts.netloc and parts.path.startswith(
                    media.path.rstrip("/") + "/"
                ):
                    return True
        return False

    def _resolve(self, url):
        if not self.site or not self.base or not url or url.startswith("#"):
            return None, None
        try:
            parts = urlsplit(urljoin(self.base, url))
            if not self._internal(parts) or self._ignored(parts):
                return None, None
            fragment = parts.fragment
            visited = set()
            for _ in range(8):
                path = unquote(parts.path, errors="strict")
                if any(char in path for char in "\\\x00") or "%" in path or path in visited:
                    return None, "not_found"
                visited.add(path)
                try:
                    route = resolve(path)
                except Resolver404:
                    route = None
                if route and route.url_name == "wagtaildocs_serve":
                    return None, None
                if route and "wagtail_markdown_agents" in route.app_names:
                    target, reason = self._direct(route.kwargs["export_path"])
                    if target:
                        return urlunsplit(urlsplit(target)._replace(fragment=fragment)), None
                    return None, reason
                if route and route.url_name != "wagtail_serve":
                    return None, None  # A project/API route is not a canonical CMS page.
                tree_path = self.site.root_page.url_path + path.lstrip("/")
                page = Page.objects.filter(url_path=tree_path.rstrip("/") + "/").first()
                if page is not None:
                    canonical = page.specific.full_url
                    if not canonical or unquote(urlsplit(canonical).path).rstrip(
                        "/"
                    ) != path.rstrip("/"):
                        return None, None
                    target, reason = self._export(page)
                    if target:
                        return urlunsplit(urlsplit(target)._replace(fragment=fragment)), None
                    return None, reason
                redirect = self._redirect(path)
                if not redirect:
                    return None, "not_found"
                parts = urlsplit(urljoin(urlunsplit(parts), redirect))
                if not self._internal(parts) or self._ignored(parts):
                    return None, None
                fragment = fragment or parts.fragment
            return None, "not_found"
        except (ValueError, UnicodeError):
            return None, "not_found"

    def _direct(self, path):
        logical = f"{self.site.hostname}/{path}"
        record = (
            ExportArtifact.objects.filter(scope__site_id=self.site.pk, logical_path=logical)
            .select_related("scope", "file")
            .first()
        )
        if record is None:
            return None, "not_found"
        if record.page_id is not None:
            page = Page.objects.filter(pk=record.page_id).first()
            return self._export(page) if page else (None, "not_found")
        try:
            with FileWriter().open(logical, site_id=self.site.pk, file_id=record.file_id):
                return export_url(record), None
        except (FileNotFoundError, ExportPathError):
            return None, "not_found"

    def _export(self, page):
        if page.pk in self.targets:
            return self.targets[page.pk]
        try:
            current, _, path, _ = page_state(page.pk, self.site.pk)
        except (StaleBuild, ExportPathError):
            result = (None, "ineligible")
        else:
            record = (
                ExportArtifact.objects.filter(
                    scope__site_id=self.site.pk, page_id=current.pk, logical_path=path
                )
                .select_related("scope", "file")
                .first()
            )
            if record is None:
                result = (None, "not_found")
            else:
                try:
                    with FileWriter().open(path, site_id=self.site.pk, file_id=record.file_id):
                        target = export_url(record)
                    result = (target, None)
                except (FileNotFoundError, ExportPathError):
                    result = (None, "not_found")
        self.targets[page.pk] = result
        return result

    def _redirect(self, path):
        if not apps.is_installed("wagtail.contrib.redirects"):
            return None
        from wagtail.contrib.redirects.models import Redirect

        matches = list(
            Redirect.objects.filter(
                Q(site_id=self.site.pk) | Q(site__isnull=True),
                old_path=Redirect.normalise_path(path),
            ).select_related("redirect_page")
        )
        scoped = [row for row in matches if row.site_id == self.site.pk]
        matches = scoped or matches
        if len(matches) != 1:
            return None
        row = matches[0]
        if row.redirect_page_id:
            if row.redirect_page_route_path not in {"", "/"}:
                return None
            return row.redirect_page.specific.full_url
        return row.redirect_link


def _source_positions(content, line_map, lines, offsets):
    """Map parser-normalised inline characters to unchanged source lines.

    Block parsing removes list/quote markers and heading delimiters. If a
    construct cannot be mapped exactly, leave it untouched instead of guessing.
    """
    positions = []
    chunks = content.split("\n")
    for number, chunk in enumerate(chunks):
        line = line_map[0] + number
        if line >= line_map[1]:
            return None
        raw = lines[line].rstrip("\r\n")
        start = raw.find(chunk)
        if start < 0:
            return None
        positions.extend(range(offsets[line] + start, offsets[line] + start + len(chunk)))
        if number < len(chunks) - 1:
            positions.append(offsets[line] + len(lines[line]) - 1)
    positions.append(positions[-1] + 1 if positions else offsets[line_map[0]])
    return positions


def rewrite_links(markdown, page, context=None):
    """Edit recognised destinations, preserving surrounding Markdown bytes.

    Reference uses become inline links; definitions and images stay untouched.
    Code/HTML blocks and inline code are excluded by the Markdown parser.
    """
    context = context if context is not None else render_context(page)
    resolver = LinkResolver(page, context)
    edits = []
    lines = markdown.splitlines(keepends=True)
    offsets, offset = [], 0
    for line_text in lines:
        offsets.append(offset)
        offset += len(line_text)
    parser = MarkdownIt("commonmark")

    def capture_link(state, silent):
        start, count = state.pos, len(state.tokens)
        end_label = (
            state.md.helpers.parseLinkLabel(state, start, True) if state.src[start] == "[" else -1
        )
        accepted = link(state, silent)
        if accepted and not silent and not state.env.get("ignore_links"):
            token = next(item for item in state.tokens[count:] if item.type == "link_open")
            end = state.pos
            destination = end_label + 1
            if destination < end and state.src[destination] == "(":
                destination += 1
                while destination < end and state.src[destination] in " \t\n":
                    destination += 1
                parsed = state.md.helpers.parseLinkDestination(state.src, destination, end)
                left, right = destination, parsed.pos
                if state.src[left : left + 1] == "<":
                    left, right = left + 1, right - 1
                state.env["link_spans"].append((left, right, token.attrGet("href"), None))
            else:
                state.env["link_spans"].append(
                    (end_label + 1, end, token.attrGet("href"), token.attrGet("title") or "")
                )
        return accepted

    def capture_autolink(state, silent):
        start, count = state.pos, len(state.tokens)
        accepted = autolink(state, silent)
        if accepted and not silent and not state.env.get("ignore_links"):
            token = next(item for item in state.tokens[count:] if item.type == "link_open")
            state.env["link_spans"].append((start + 1, state.pos - 1, token.attrGet("href"), None))
        return accepted

    def skip_image(state, silent):
        previous = state.env.get("ignore_links", False)
        state.env["ignore_links"] = True
        try:
            return image(state, silent)
        finally:
            state.env["ignore_links"] = previous

    def capture_inline(state):
        for token in state.tokens:
            if token.type != "inline" or token.map is None:
                continue
            positions = _source_positions(token.content, token.map, lines, offsets)
            if positions is None:
                continue
            state.env["link_spans"] = []
            state.md.inline.parse(token.content, state.md, state.env, [])
            for left, right, href, title in state.env["link_spans"]:
                target = resolver.resolve(href)
                if target is None:
                    continue
                if title is not None:
                    escaped = title.replace("\\", "\\\\").replace('"', '\\"')
                    target = f"(<{target}>" + (f' "{escaped}"' if title else "") + ")"
                else:
                    target = target.replace("(", "%28").replace(")", "%29")
                end = positions[right - 1] + 1 if right > left else positions[left]
                edits.append((positions[left], end, target))

    parser.inline.ruler.at("link", capture_link)
    parser.inline.ruler.at("autolink", capture_autolink)
    parser.inline.ruler.at("image", skip_image)
    parser.core.ruler.at("inline", capture_inline)
    parser.parse(markdown)
    for left, right, target in sorted(edits, reverse=True):
        markdown = markdown[:left] + target + markdown[right:]
    return markdown
