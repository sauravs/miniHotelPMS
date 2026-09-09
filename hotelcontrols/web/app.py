# -*- coding: utf-8 -*-
"""
L7 · WEB - routing, and nothing else.

    handle(path) -> (status, content_type, body)

A PURE FUNCTION OF THE PATH. That signature is the whole design of this layer: a page produced
from a string can be tested from a string, and a demo whose correctness depends on a listening
port is a demo nobody can assert anything about. `server.py` is the only file that knows a
socket exists, and it is eleven lines around this function.

WHAT THE PAGE IS FOR
---------------------
One thing: showing that a verdict traces to the fields that produced it. It is thin on purpose
and is not trying to look like a product. `architecture.md` is blunt about why there is no
JavaScript - a page that assembles itself from an API call is a page a browser, a CSP or a
`file://` open can break, and the demo's job is to be believable rather than modern.

WHY A RUN IS SAVED ON A GET
----------------------------
Because the history has to come from somewhere, and this is a single-operator local demo with
no writes to any PMS. Asking the same control the same question over the same evidence at the
same instant produces the same `run_id`, so a refresh replaces rather than duplicates: the
history records distinct questions, not page loads.

WHAT DECIDES `as_of` WHEN THE READER DOES NOT
----------------------------------------------
The body of evidence itself. Each capture declares the instant it describes, and asking it
about that instant is the only default that is honest - a capture of July answers questions
about July. Asking today's date instead would produce a page of refusals for a reason that has
nothing to do with the controls. The page always says which instant it asked about, and
`?as_of=` overrides it.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import replace
from typing import NamedTuple

from ..kernel import FixedClock
from ..providers import registry as providers
from ..runner import next_evaluation, readiness, run
from ..spec import (ControlIR, Registry, SpecError, TenantConfig, available, available_tenants,
                    load, provider_map)
from ..store import RunStore
from . import render

HTML = "text/html; charset=utf-8"
JSON = "application/json; charset=utf-8"
CSS = "text/css; charset=utf-8"


class Response(NamedTuple):
    """`(status, content_type, body)` - the triple `architecture.md` declares, with names."""

    status: int
    content_type: str
    body: str


class _Refused(Exception):
    """A request this engine will not answer, with the status a reader should see.

    Separate from an unexpected failure on purpose. "There is no control called that" is a
    complete answer; a traceback is not, and the two must not render the same way.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class App:
    """The demo. One spec directory, one run store, no state that outlives a request but the
    history."""

    def __init__(self, spec_dir=None, store: RunStore | None = None) -> None:
        self.spec_dir = spec_dir
        self.store = store if store is not None else RunStore(":memory:")
        self.registry = Registry.load(spec_dir) if spec_dir else Registry.load()
        # Every provider call this app has spent, so a test can assert that re-reading a stored
        # run costs none of them (R1). It is also the number a demo operator should watch.
        self.provider_calls = 0

    # ------------------------------------------------------------------ entry point
    def handle(self, path: str) -> Response:
        """Answer any path, always. This is the last thing before a socket.

        Every failure below becomes a page or a JSON object, because a dropped connection tells
        a reader nothing and a stack trace tells them nothing they can act on.
        """
        split = urllib.parse.urlsplit(path)
        # Unquoted PER SEGMENT, after splitting - never before. Unquoting the whole path first
        # would turn a `%2F` inside an id into a real separator, which silently reshapes the
        # route: `/run/..%2F..%2Fetc%2Fpasswd` would stop being a control id and start being a
        # four-deep path. The id is meant to reach the spec loader, which refuses it by name.
        segments = tuple(urllib.parse.unquote(part) for part in split.path.split("/") if part)
        query = {key: values[0] for key, values
                 in urllib.parse.parse_qs(split.query).items() if values}
        wants_json = segments[:1] == ("api",)

        try:
            return self.route(segments, query)
        except _Refused as refused:
            return self._error(refused.status, refused.message, wants_json)
        except SpecError as exc:
            # The spec layer's refusals are addressed to a reader as they are: "no control
            # called that", "this tenant declares no such setting".
            return self._error(404, str(exc), wants_json)
        except Exception as exc:                                        # noqa: BLE001
            return self._error(500, "%s: %s" % (type(exc).__name__, exc), wants_json)

    def _error(self, status: int, message: str, wants_json: bool) -> Response:
        if wants_json:
            return Response(status, JSON, render.error_json(status, message))
        return Response(status, HTML, render.error_page(status, message))

    # ------------------------------------------------------------------ routing
    def route(self, segments: tuple[str, ...], query: dict) -> Response:
        """Which page a path is. Overridden in tests to prove `handle` catches anything."""
        parts = list(segments)

        if not parts:
            return self._index(query)
        if parts == ["style.css"]:
            return Response(200, CSS, render.STYLESHEET)
        if len(parts) == 2 and parts[0] == "run":
            return self._run_page(parts[1], query)
        if len(parts) == 2 and parts[0] == "history":
            return self._history(parts[1])
        if len(parts) == 3 and parts[:2] == ["api", "run"]:
            return self._run_json(parts[2], query)
        if len(parts) == 3 and parts[:2] == ["api", "runs"]:
            return self._stored_run(parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "readiness"]:
            return Response(200, JSON, render.readiness_json(
                parts[2], self._readiness(self._ir(parts[2]))))

        raise _Refused(404, "There is nothing at /%s. The controls are listed at /."
                       % "/".join(parts))

    # ------------------------------------------------------------------ pages
    def _index(self, query: dict) -> Response:
        tenant_id, capture = self._selection(query)
        entries = [(ir, self._readiness(ir)) for ir in map(self._ir, self._controls())]
        properties = []
        for name in available_tenants(self.spec_dir) if self.spec_dir else available_tenants():
            tenant = self._tenant(name)
            package = providers.load(tenant.provider)
            properties.append((name, tenant.provider, package.captures, tenant.name))
        return Response(200, HTML,
                        render.index_page(entries, properties, (tenant_id, capture)))

    def _run_page(self, control_id: str, query: dict) -> Response:
        result, ir, tenant = self._execute(control_id, query)
        links = {capture: "/run/%s?property=%s&evidence=%s" % (control_id, tenant.tenant_id,
                                                               capture)
                 for capture in providers.load(tenant.provider).captures}
        return Response(200, HTML, render.run_page(result, plan=self._plan(ir, tenant, result),
                                                   readiness=self._readiness(ir), links=links))

    def _run_json(self, control_id: str, query: dict) -> Response:
        result, ir, tenant = self._execute(control_id, query)
        return Response(200, JSON, render.run_json(result, plan=self._plan(ir, tenant, result),
                                                   readiness=self._readiness(ir)))

    def _stored_run(self, run_id: str) -> Response:
        """A past run, re-read from SQLite. Zero provider calls, by construction (R1)."""
        stored = self.store.load(run_id)
        if stored is None:
            raise _Refused(404, "No stored run called %r. Past runs are listed at "
                                "/history/<control_id>." % run_id)
        return Response(200, JSON, render.run_json(stored))

    def _history(self, control_id: str) -> Response:
        self._ir(control_id)          # refuse an unknown id here rather than showing an empty
        return Response(200, HTML, render.history_page(
            control_id, self.store.history(control_id)))

    # ------------------------------------------------------------------ doing the work
    def _execute(self, control_id: str, query: dict):
        """Run one control over one body of evidence, and keep the result."""
        ir = self._ir(control_id)
        tenant_id, capture = self._selection(query)
        tenant = self._tenant(tenant_id)
        package = providers.load(tenant.provider)
        adapter, source = package.build(tenant, capture)
        # The evidence decides the question when the reader does not: a capture declares the
        # instant it describes, and that is the only date it can honestly be asked about.
        as_of = query.get("as_of") or getattr(source, "as_of", None)
        try:
            clock = FixedClock.at(as_of, tenant.timezone)
        except (TypeError, ValueError):
            raise _Refused(400, "%r is not a date this engine can read. Write it as "
                                "YYYY-MM-DD." % as_of) from None

        result = run(control_id, tenant, adapter, clock, evidence_label=capture,
                     spec_dir=self.spec_dir)
        self.provider_calls += result.calls
        return replace(result, run_id=self.store.save(result)), ir, tenant

    def _plan(self, ir: ControlIR, tenant: TenantConfig, result) -> object:
        """When this control runs next on this provider - finding F7, on the page at last.

        Rendered beside the verdicts because the two answer different halves of one question:
        the verdicts say what is true now, and the plan says how soon we would notice if it
        stopped being true.
        """
        package = providers.load(tenant.provider)
        adapter, _source = package.build(tenant, package.default_capture)
        return next_evaluation(ir, adapter.events(),
                               FixedClock.at(result.as_of, tenant.timezone))

    def _readiness(self, ir: ControlIR) -> tuple:
        """What every provider could answer about this control, from the spec alone (F8)."""
        return tuple(
            readiness(ir, name,
                      provider_map(name, self.spec_dir) if self.spec_dir
                      else provider_map(name),
                      self.registry)
            for name in providers.names())

    # ------------------------------------------------------------------ small helpers
    def _controls(self) -> tuple[str, ...]:
        return available(self.spec_dir) if self.spec_dir else available()

    def _ir(self, control_id: str) -> ControlIR:
        return load(control_id, self.spec_dir) if self.spec_dir else load(control_id)

    def _tenant(self, tenant_id: str) -> TenantConfig:
        return (TenantConfig.load(tenant_id, self.spec_dir) if self.spec_dir
                else TenantConfig.load(tenant_id))

    def _selection(self, query: dict) -> tuple[str, str]:
        """Which property and which body of evidence this request is about.

        A value from a URL that names nothing falls back to the first property rather than
        raising: a mistyped query string is not worth a refusal, and the page states plainly
        which property and which evidence it actually used.
        """
        tenants = available_tenants(self.spec_dir) if self.spec_dir else available_tenants()
        if not tenants:
            raise _Refused(500, "No property is configured - spec/tenants/ is empty.")
        tenant_id = query.get("property")
        if tenant_id not in tenants:
            tenant_id = tenants[0]
        package = providers.load(self._tenant(tenant_id).provider)
        capture = query.get("evidence")
        if capture not in package.captures:
            capture = package.default_capture
        return tenant_id, capture

    def captures_for(self, tenant_id: str) -> tuple[str, ...]:
        """Every body of evidence this property's provider can be replayed against."""
        return providers.load(self._tenant(tenant_id).provider).captures


_DEFAULT: App | None = None


def handle(path: str) -> Response:
    """`handle(path) -> (status, content_type, body)`, against a default in-memory demo."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = App()
    return _DEFAULT.handle(path)
