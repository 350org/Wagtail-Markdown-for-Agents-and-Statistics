"""Immutable uploads, atomic database publication and managed cleanup (#19).

Storage needs save/open/delete/exists, read-after-write visibility and open
handles that survive deletion. Resolve logical paths through ExportArtifact;
storage objects must be private. See docs/storage-writer.md for failure semantics.
"""

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.db import DEFAULT_DB_ALIAS, OperationalError, connection, router, transaction
from django.db.models import F
from wagtail.models import Page, PageViewRestriction, Revision, Site

from ..models import ExportArtifact, ExportFile, ExportScope, PageAgentSettings
from ..settings import get_setting
from ..signals import markdown_deleted, markdown_generated
from .paths import ExportPathError, site_path, validate_path
from .state import StaleBuild, page_state, site_state
from .storage import resolve_storage

logger = logging.getLogger(__name__)


class StorageContractError(ValueError):
    """A backend or caller violated the managed publication contract."""


class ConcurrentAggregateUpdate(StaleBuild):
    """Only aggregate publication advanced the scope; a pure updater may retry."""


@dataclass(frozen=True)
class BuildToken:
    site_id: int
    version: int
    page_id: int | None
    path: str
    source_state: str
    dependency_state: str = ""
    content_version: int = 0


def _retry_locked(fn):
    """Bounded SQLite contention retry; other database errors propagate."""
    deadline = time.monotonic() + 10
    while True:
        try:
            return fn()
        except OperationalError as exc:
            if (
                connection.vendor != "sqlite"
                or "locked" not in str(exc)
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(0.01)


def _scope(site_id):
    return _retry_locked(lambda: ExportScope.objects.get_or_create(site_id=site_id)[0])


@contextmanager
def _locked(site_id):
    scope = _scope(site_id)
    deadline = time.monotonic() + 10
    while True:
        acquired = False
        try:
            with transaction.atomic():
                # Unlike select_for_update, UPDATE locks on SQLite too.
                ExportScope.objects.filter(pk=scope.pk).update(version=F("version"))
                acquired = True
                yield ExportScope.objects.get(pk=scope.pk)
            return
        except OperationalError as exc:
            if (
                acquired
                or connection.vendor != "sqlite"
                or "locked" not in str(exc)
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(0.01)


def _after_commit_required():
    if connection.in_atomic_block or not connection.get_autocommit():
        raise RuntimeError("Publish Markdown after commit, using transaction.on_commit()")


def _emit(signal, **kwargs):
    def send():
        for receiver, response in signal.send_robust(sender=FileWriter, **kwargs):
            if isinstance(response, Exception):
                logger.error("Markdown signal receiver %r failed: %s", receiver, response)

    transaction.on_commit(send)


class FileWriter:
    def __init__(self):
        # Transactions/locks and fresh CMS reads must use the same primary DB.
        # Reject routed deployments rather than accidentally guarding a replica.
        for model in (
            Page,
            Revision,
            Site,
            PageViewRestriction,
            PageAgentSettings,
            ExportScope,
            ExportFile,
            ExportArtifact,
        ):
            if any(
                route(model) != DEFAULT_DB_ALIAS
                for route in (router.db_for_read, router.db_for_write)
            ):
                raise ImproperlyConfigured(
                    "The v0.1 export writer requires CMS and export records on the default database"
                )

    def begin(self, page, *, depends_on_site=False) -> BuildToken:
        """Capture before rendering; a supplied page contributes only its ID."""
        if isinstance(page, Page) and page._state.db not in {None, DEFAULT_DB_ALIAS}:
            raise ImproperlyConfigured("The export page must come from the default database")
        page_id = page.pk if isinstance(page, Page) else page
        _, site, _, _ = page_state(page_id)
        with _locked(site.pk) as scope:
            current, _, path, state = page_state(page_id, site.pk)
            dependency = ""
            if (
                depends_on_site
                or get_setting("INCLUDE_HIERARCHY")
                or current.get_children().live().exists()
            ):
                _, dependency = site_state(site.pk)
            return BuildToken(
                site.pk, scope.version, page_id, path, state, dependency, scope.content_version
            )

    def begin_site(self, site_id: int, path: str) -> BuildToken:
        with _locked(site_id) as scope:
            site, state = site_state(site_id)
            site_path(path, site.hostname)
            return BuildToken(
                site_id, scope.version, None, path, state, content_version=scope.content_version
            )

    def generate(self, page, *, navigation="", depends_on_site=False):
        """Render and publish one page; index/discovery generation is separate."""
        from ..rendering import render_page

        _after_commit_required()
        token = self.begin(page, depends_on_site=depends_on_site or bool(navigation))
        return self.publish(
            token, render_page(Page.objects.get(pk=token.page_id), navigation=navigation)
        )

    def publish(self, token: BuildToken, markdown: str, *, replace_index=False, commit=None):
        """Publish a captured build or raise StaleBuild; no silent retries.

        ``replace_index`` lets a page index take over standalone navigation at
        that exact path. Another page's ownership can never be replaced.
        ``commit(scope, record)`` optionally updates private database state in
        the pointer transaction. It must perform no IO or recursive publication;
        an exception rolls back both the pointer and that state.
        """
        _after_commit_required()
        candidate = self._allocate(token.site_id, token.path, token.page_id)
        try:
            self._upload(candidate, markdown)
            with _locked(token.site_id) as scope:
                self._check(token, scope)
                if replace_index:
                    if token.page_id is None or not token.path.endswith("/index.md"):
                        raise StorageContractError(
                            "Only a page index can replace a navigation index"
                        )
                    self._retire(
                        ExportArtifact.objects.filter(
                            scope=scope, logical_path=token.path, page_id__isnull=True
                        ),
                        notify=False,
                    )
                record = self._swap(scope, token, candidate)
                if commit is not None:
                    commit(scope, record)
        except Exception:
            self._abandon(candidate)
            raise
        self._published(record)
        return record

    def update_aggregate(self, site_id: int, path: str, update, *, commit=None):
        """Optimistic listing/manifest update; update receives str or None.

        The callback returns complete new text, with no database mutations or
        recursive writer calls. It may run up to three times on competing aggregate
        writes; a page change/revocation always aborts. Uploads run outside locks.
        An expired/missing aggregate is None. Page-owned indexes are protected.
        ``commit`` has the same atomic database-only contract as in ``publish``.
        """
        _after_commit_required()
        baseline = None
        for attempt in range(3):
            with _locked(site_id) as scope:
                site, state = site_state(site_id)
                token = BuildToken(
                    site_id,
                    scope.version,
                    None,
                    site_path(path, site.hostname),
                    state,
                    content_version=scope.content_version,
                )
                existing = (
                    ExportArtifact.objects.filter(scope=scope, logical_path=path)
                    .select_related("file")
                    .first()
                )
                if existing and existing.page_id is not None:
                    raise StorageContractError(f"Path {path!r} is owned by a page")
            current = (token.source_state, token.content_version)
            if baseline is not None and current != baseline:
                raise StaleBuild("Page content or eligibility changed during aggregate update")
            baseline = current
            previous = None
            if existing and existing.source_state == state:
                try:
                    with self._open_file(existing.file) as stream:
                        previous = stream.read().decode("utf-8")
                except FileNotFoundError:
                    pass
            try:
                return self.publish(token, update(previous), commit=commit)
            except ConcurrentAggregateUpdate:
                if attempt == 2:
                    raise

    def open(self, path: str, *, site_id: int | None = None, file_id: int | None = None):
        """Open a current owned logical path or raise FileNotFoundError.

        Public routes must also apply request-specific serving gates. Never
        expose a Storage.url() or client-provided raw storage key directly.
        Optional site/file IDs bind a caller's ownership and metadata checks to
        the opened generation; a replacement becomes a miss for that caller.
        """
        validate_path(path)
        for _ in range(3):
            record = self._record(path)
            if (
                record is None
                or (site_id is not None and record.scope.site_id != site_id)
                or (file_id is not None and record.file_id != file_id)
                or not _retry_locked(lambda record=record: self._current(record))
            ):
                raise FileNotFoundError(path)
            try:
                stream = self._open_file(record.file)
            except FileNotFoundError:
                continue  # A replacement may have retired this object before open.
            keep = False
            try:
                latest = self._record(path)
                if (
                    latest
                    and latest.file_id == record.file_id
                    and latest.scope_id == record.scope_id
                    and _retry_locked(lambda latest=latest: self._current(latest))
                ):
                    keep = True
                    return stream
            finally:
                if not keep:
                    stream.close()
        raise FileNotFoundError(path)

    @staticmethod
    def _record(path):
        return _retry_locked(
            lambda: (
                ExportArtifact.objects.filter(logical_path=path)
                .select_related("file", "scope")
                .first()
            )
        )

    def exists(self, path: str) -> bool:
        try:
            with self.open(path):
                return True
        except (FileNotFoundError, ExportPathError):
            return False

    def object_exists(self, record) -> bool:
        """Whether a current publication's recorded storage object exists.

        A discovery-only probe for advertising an export: it opens nothing and
        checks publication freshness before probing storage. It never authorises
        a read: serving still checks ownership and freshness around opening the
        file. A changed storage configuration reports the object as absent.
        """
        try:
            if not _retry_locked(lambda: self._current(record)):
                return False
            return self._backend(record.file).exists(record.file.storage_key)
        except StorageContractError:
            return False

    def delete_page(self, page_id: int, *, site_id: int):
        """Withdraw a page and site aggregates, even if no file currently exists.

        May run inside revocation transactions: physical deletion is immediate.
        Rollback may restore a pointer to a missing file (safe HTML fallback).
        The scope lock prevents a concurrent build passing revocation's commit.
        """
        with _locked(site_id) as scope:
            self._retire(ExportArtifact.objects.filter(scope=scope, page_id=page_id), notify=True)
            self._retire(
                ExportArtifact.objects.filter(scope=scope, page_id__isnull=True), notify=True
            )
            self._retire(
                ExportArtifact.objects.filter(scope=scope).exclude(dependency_state=""), notify=True
            )
            ExportScope.objects.filter(pk=scope.pk).update(
                version=F("version") + 1, content_version=F("content_version") + 1
            )
        self._cleanup_safely(site_id)

    def cleanup(self, site_id: int):
        """Retry explicitly retired objects only; never list/sweep storage trees."""
        # Retired objects are immutable and can never be republished. Their IO
        # needs no site mutex; concurrent cleaners may repeat an idempotent delete.
        files = _retry_locked(
            lambda: list(
                ExportFile.objects.filter(
                    scope__site_id=site_id, cleanup_pending=True, artifact__isnull=True
                )
            )
        )
        for file in files:
            try:
                self._backend(file).delete(file.storage_key)
            except Exception:
                logger.exception(
                    "Could not delete managed export file %s; retained for retry", file.pk
                )
                continue
            deleted, _ = _retry_locked(
                lambda file=file: ExportFile.objects.filter(
                    pk=file.pk, cleanup_pending=True, artifact__isnull=True
                ).delete()
            )
            if deleted and file.notify_deleted:
                _emit(
                    markdown_deleted,
                    page_id=file.page_id,
                    site_id=site_id,
                    path=file.logical_path,
                    storage_key=file.storage_key,
                    storage_alias=file.storage_alias,
                )

    def delete_site(self, site_id: int):
        """Withdraw exactly this site's managed records; keep unrelated objects."""
        with _locked(site_id) as scope:
            self._retire(ExportArtifact.objects.filter(scope=scope), notify=True)
            ExportScope.objects.filter(pk=scope.pk).update(
                version=F("version") + 1, content_version=F("content_version") + 1
            )
        self._cleanup_safely(site_id)

    def delete_stale(self, site_id: int):
        """Withdraw obsolete pointers before rebuilding a site's navigation.

        Recheck under the publication mutex so a concurrent fresh replacement
        cannot be deleted. Missing storage objects remain safe read misses.
        """
        with _locked(site_id) as scope:
            obsolete = [
                record.pk
                for record in ExportArtifact.objects.filter(scope=scope).select_related("scope")
                if not self._current(record)
            ]
            if obsolete:
                self._retire(ExportArtifact.objects.filter(pk__in=obsolete), notify=True)
                ExportScope.objects.filter(pk=scope.pk).update(
                    version=F("version") + 1, content_version=F("content_version") + 1
                )
        self._cleanup_safely(site_id)

    def prune_indexes(self, token: BuildToken, keep_paths):
        """Remove unused standalone indexes from a captured directory inventory.

        Capture a site token before reading that inventory. Only navigation
        indexes are retired; page-owned documents and discovery files are kept.
        """
        _after_commit_required()
        if token.page_id is not None:
            raise StorageContractError("Index pruning requires a site build token")
        with _locked(token.site_id) as scope:
            self._check(token, scope)
            obsolete = ExportArtifact.objects.filter(
                scope=scope, page_id__isnull=True, logical_path__endswith="/index.md"
            ).exclude(logical_path__in=keep_paths)
            if obsolete.exists():
                self._retire(obsolete, notify=True)
                ExportScope.objects.filter(pk=scope.pk).update(version=F("version") + 1)
        self._cleanup_safely(token.site_id)

    def _allocate(self, site_id, path, page_id):
        site = Site.objects.get(pk=site_id)
        site_path(path, site.hostname)
        _, alias, fingerprint = resolve_storage()
        requested = f"{site.hostname}/.objects/{uuid.uuid4().hex}/content"
        scope = _scope(site_id)
        return _retry_locked(
            lambda: ExportFile.objects.create(
                scope=scope,
                page_id=page_id,
                logical_path=path,
                storage_alias=alias,
                storage_fingerprint=fingerprint,
                requested_key=requested,
                storage_key=requested,
            )
        )

    def _backend(self, file):
        backend, _, fingerprint = resolve_storage(file.storage_alias)
        if fingerprint != file.storage_fingerprint:
            raise StorageContractError(
                "Export storage configuration changed; restore its recorded backend before cleanup"
            )
        validate_path(file.storage_key, objects=True)
        if file.storage_key.rpartition("/")[0] != file.requested_key.rpartition("/")[0]:
            raise StorageContractError(
                "Returned storage key escaped its allocated object directory"
            )
        return backend

    def _upload(self, file, markdown):
        if not isinstance(markdown, str):
            raise TypeError("Export content must be a Markdown/text string")
        backend = self._backend(file)
        content = markdown.encode("utf-8")
        key = backend.save(file.requested_key, ContentFile(content))
        try:
            validate_path(key, objects=True)
        except ExportPathError as exc:
            raise StorageContractError("Backend returned an unsafe storage key") from exc
        if key.rpartition("/")[0] != file.requested_key.rpartition("/")[0]:
            raise StorageContractError(
                "Returned storage key escaped its allocated object directory"
            )
        file.storage_key = key
        file.save(update_fields=["storage_key"])
        if not backend.exists(key):
            raise StorageContractError("Saved export is not immediately visible")
        with backend.open(key, "rb") as stream:
            if stream.read() != content:
                raise StorageContractError(
                    "Saved export does not match the complete uploaded content"
                )

    def _check(self, token, scope):
        if token.version != scope.version:
            if token.content_version != scope.content_version:
                raise StaleBuild("A page publication or revocation superseded this site build")
            raise ConcurrentAggregateUpdate("Another aggregate update superseded this site build")
        if token.page_id is None:
            site, state = site_state(token.site_id)
            site_path(token.path, site.hostname)
        else:
            _, _, path, state = page_state(token.page_id, token.site_id)
            if path != token.path:
                raise StaleBuild("The page's export path changed during rendering")
        if state != token.source_state:
            raise StaleBuild("Publication inputs changed during rendering")
        if token.dependency_state and site_state(token.site_id)[1] != token.dependency_state:
            raise StaleBuild("Related site content changed during rendering")

    def _swap(self, scope, token, file):
        self._backend(file)  # Recheck storage identity after upload too.
        occupied = ExportArtifact.objects.filter(logical_path=token.path).first()
        if occupied and (occupied.scope_id != scope.pk or occupied.page_id != token.page_id):
            raise StorageContractError(f"Path {token.path!r} is owned by another page or aggregate")
        if token.page_id is not None:
            for record in ExportArtifact.objects.filter(scope=scope, page_id=token.page_id):
                self._retire(
                    ExportArtifact.objects.filter(pk=record.pk),
                    notify=record.logical_path != token.path,
                )
            self._retire(
                ExportArtifact.objects.filter(scope=scope, page_id__isnull=True), notify=True
            )
            # Rebuilding one page-owned index must not withdraw other indexes
            # built from the same CMS state. Revocation withdraws them all.
            dependents = ExportArtifact.objects.filter(scope=scope).exclude(dependency_state="")
            if dependents.exists():
                current_site_state = token.dependency_state or site_state(scope.site_id)[1]
                self._retire(dependents.exclude(dependency_state=current_site_state), notify=True)
        else:
            self._retire(
                ExportArtifact.objects.filter(scope=scope, logical_path=token.path), notify=False
            )
        record = ExportArtifact.objects.create(
            scope=scope,
            page_id=token.page_id,
            logical_path=token.path,
            file=file,
            source_state=token.source_state,
            dependency_state=token.dependency_state,
        )
        changes = {"version": F("version") + 1}
        if token.page_id is not None:
            changes["content_version"] = F("content_version") + 1
        ExportScope.objects.filter(pk=scope.pk).update(**changes)
        return record

    @staticmethod
    def _retire(records, *, notify):
        file_ids = list(records.values_list("file_id", flat=True))
        records.delete()
        ExportFile.objects.filter(pk__in=file_ids).update(
            cleanup_pending=True, notify_deleted=notify
        )

    def _abandon(self, file):
        # A failed aggregate transaction may roll back its returned-key update.
        # Preserve the actual key from memory before retryable cleanup.
        try:
            file.cleanup_pending = True
            file.save(update_fields=["storage_key", "cleanup_pending"])
            self.cleanup(file.scope.site_id)
        except Exception:
            logger.exception("Failed build left candidate %s for operator recovery", file.pk)

    def _current(self, record):
        try:
            if record.page_id is None:
                _, state = site_state(record.scope.site_id)
            else:
                _, _, path, state = page_state(record.page_id, record.scope.site_id)
                if path != record.logical_path:
                    return False
            return state == record.source_state and (
                not record.dependency_state
                or site_state(record.scope.site_id)[1] == record.dependency_state
            )
        except StaleBuild:
            return False

    def _open_file(self, file):
        backend = self._backend(file)
        if not backend.exists(file.storage_key):
            raise FileNotFoundError(file.logical_path)
        return backend.open(file.storage_key, "rb")

    def _published(self, record):
        try:
            _emit(
                markdown_generated,
                page=Page.objects.filter(pk=record.page_id).specific().first()
                if record.page_id
                else None,
                page_id=record.page_id,
                site_id=record.scope.site_id,
                path=record.logical_path,
                storage_key=record.file.storage_key,
                storage_alias=record.file.storage_alias,
            )
        except Exception:
            logger.exception(
                "Export %s committed, but its generated notification failed", record.pk
            )
        finally:
            self._cleanup_safely(record.scope.site_id)

    def _cleanup_safely(self, site_id):
        try:
            self.cleanup(site_id)
        except Exception:
            # Publication already committed; cleanup failure must not look like
            # an upload failure or invite a caller to republish obsolete bytes.
            logger.exception("Export cleanup for site %s needs retry", site_id)
