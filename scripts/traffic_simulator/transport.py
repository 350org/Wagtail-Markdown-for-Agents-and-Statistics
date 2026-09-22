"""Bounded sequential HTTP transport with durable attempt/receipt evidence."""

import hashlib
import http.client
import json
import os
import time
import uuid
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .planning import assess, positive, safe_url, target_origin

RECORDED_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-encoding",
        "cache-control",
        "vary",
        "age",
        "cf-cache-status",
        "cf-ray",
        "date",
        "etag",
        "last-modified",
        "x-cache",
    }
)
CACHE_HITS = frozenset({"HIT"})
CACHE_REVALIDATIONS = frozenset({"STALE", "UPDATING", "REVALIDATED"})


def utc_now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class BudgetExhausted(Exception):
    """No further request may start in this run."""


class FetchFailed(Exception):
    """Transport did not deliver a complete response."""


class CachePoisoning(Exception):
    """A browser received Markdown; stop traffic and investigate the cache."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_transport(spec, headers, timeout, max_bytes):
    # No ambient proxy credentials, cookies, redirects or automatic retries.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    started = time.monotonic()
    try:
        response = opener.open(
            Request(spec.url, headers=headers, method=spec.method), timeout=timeout
        )
    except HTTPError as exc:
        response = exc
    with response:
        chunks, size = [], 0
        response_headers = dict(response.headers.items())
        try:
            while spec.method != "HEAD":
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("Response deadline exceeded")
                chunk = response.read1(min(65536, max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    raise FetchFailed("Response exceeded byte limit")
            if (
                spec.method != "HEAD"
                and response.headers.get("Content-Length")
                and size != int(response.headers["Content-Length"])
            ):
                raise FetchFailed("Incomplete response body")
        except (
            OSError,
            http.client.HTTPException,
            FetchFailed,
            ValueError,
            KeyboardInterrupt,
        ) as exc:
            exc.response_metadata = {
                "status": response.status,
                "headers": {
                    k.lower(): v
                    for k, v in response_headers.items()
                    if k.lower() in RECORDED_HEADERS
                },
                "received_bytes": size,
                "partial_sha256": hashlib.sha256(b"".join(chunks)).hexdigest(),
            }
            raise
        return response.status, response_headers, b"".join(chunks)


class Runner:
    def __init__(
        self,
        path,
        target,
        *,
        max_requests=1000,
        duration=3600,
        rate=1,
        retries=0,
        timeout=20,
        max_bytes=8 * 1024 * 1024,
        cache_profile="strict",
        transport=http_transport,
        clock=time,
        phase="run",
        metadata=None,
    ):
        self.path, self.target = path, target_origin(target)
        self.max_requests = positive(max_requests, "max_requests")
        self.duration = positive(duration, "duration")
        self.rate = positive(rate, "rate")
        self.timeout = positive(timeout, "timeout")
        self.max_bytes = positive(max_bytes, "max_bytes")
        if type(retries) is not int or retries < 0:
            raise ValueError("retries must be a non-negative integer")
        self.retries, self.cache_profile = retries, cache_profile
        self.transport, self.clock, self.phase = transport, clock, phase
        self.metadata = metadata or {}
        self.run_id = uuid.uuid4().hex
        self.attempts = self.failures = self.limitations = 0
        self.started = self.last_start = None
        self.file = None

    def __enter__(self):
        # Append only, owner-readable. Refuse truncated logs instead of hiding
        # their final incomplete event by appending to it.
        fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o600)
        try:
            size = os.lseek(fd, 0, os.SEEK_END)
            if size:
                os.lseek(fd, -1, os.SEEK_END)
                if os.read(fd, 1) != b"\n":
                    raise ValueError("Log has an unfinished final line; use a new log file")
            self.file = os.fdopen(fd, "a", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        self.started = self.clock.monotonic()
        self.emit(
            "run-start",
            target=self.target,
            phase=self.phase,
            max_requests=self.max_requests,
            duration=self.duration,
            rate=self.rate,
            retries=self.retries,
            cache_profile=self.cache_profile,
            **self.metadata,
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        reason = "complete"
        if exc_type:
            reason = "interrupted" if issubclass(exc_type, KeyboardInterrupt) else exc_type.__name__
        try:
            self.emit(
                "run-end",
                reason=reason,
                attempts=self.attempts,
                failures=self.failures,
                limitations=self.limitations,
            )
        finally:
            self.file.close()

    def emit(self, event, **data):
        row = dict(schema_version=1, event=event, run_id=self.run_id, timestamp=utc_now(), **data)
        self.file.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())
        return row

    def pace(self, multiplier):
        if self.attempts >= self.max_requests:
            raise BudgetExhausted("Request limit reached")
        due = self.started if self.last_start is None else self.last_start + multiplier / self.rate
        if due >= self.started + self.duration:
            raise BudgetExhausted("Duration reached")
        self.clock.sleep(max(0, due - self.clock.monotonic()))
        if self.clock.monotonic() >= self.started + self.duration:
            raise BudgetExhausted("Duration reached")

    def fetch(self, spec):
        safe_url(spec.url, self.target)
        if spec.method not in {"GET", "HEAD"} or any(ord(c) < 32 for c in spec.ua):
            raise ValueError("Only GET/HEAD and valid User-Agent headers are supported")
        retry_of = None
        for attempt in range(self.retries + 1):
            self.pace(positive(spec.delay, "delay"))
            self.last_start = self.clock.monotonic()
            remaining = self.started + self.duration - self.last_start
            request_id = uuid.uuid4().hex
            self.attempts += 1
            self.emit(
                "attempt",
                request_id=request_id,
                retry_of=retry_of,
                attempt_number=attempt + 1,
                **spec.as_dict(),
            )
            headers = {
                "User-Agent": spec.ua,
                "Accept": spec.accept,
                "Accept-Encoding": "identity",
                "X-Sim-Run": self.run_id,
                "X-Sim-Request": request_id,
            }
            try:
                status, raw_headers, body = self.transport(
                    spec, headers, min(self.timeout, remaining), self.max_bytes
                )
                response_headers = {
                    key.lower(): value
                    for key, value in raw_headers.items()
                    if key.lower() in RECORDED_HEADERS
                }
            except KeyboardInterrupt as exc:
                self.emit(
                    "interrupted",
                    request_id=request_id,
                    receipt_complete=False,
                    **getattr(exc, "response_metadata", {}),
                    elapsed_ms=(self.clock.monotonic() - self.last_start) * 1000,
                )
                raise
            except (OSError, URLError, http.client.HTTPException, FetchFailed, ValueError) as exc:
                # Exception messages can contain URLs, credentials or response bytes.
                self.emit(
                    "error",
                    request_id=request_id,
                    error=type(exc).__name__,
                    receipt_complete=False,
                    **getattr(exc, "response_metadata", {}),
                    elapsed_ms=(self.clock.monotonic() - self.last_start) * 1000,
                    will_retry=attempt < self.retries,
                )
                retry_of = request_id
                if attempt == self.retries:
                    self.failures += 1
                    raise FetchFailed(type(exc).__name__) from None
                continue
            result = assess(spec, status, response_headers, body, cache_profile=self.cache_profile)
            self.emit(
                "response",
                request_id=request_id,
                status=status,
                headers=response_headers,
                receipt_complete=True,
                body_sha256=hashlib.sha256(body).hexdigest(),
                received_bytes=len(body),
                elapsed_ms=(self.clock.monotonic() - self.last_start) * 1000,
                **result,
            )
            if result["outcome"] == "known-limitation":
                self.limitations += 1
            if result["outcome"] in {"failure", "cache-poisoning"}:
                self.failures += 1
            if result["outcome"] == "cache-poisoning":
                raise CachePoisoning(result["reason"])
            return body
        raise AssertionError("Unreachable retry state")
