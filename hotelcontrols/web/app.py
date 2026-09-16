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

import json
import pathlib
import urllib.parse
import uuid
from dataclasses import replace
from typing import NamedTuple

from ..compiler import Turn, compile_sentence, deployment_of, normalise
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
    history - and, when a proposer is wired, the compose conversations."""

    def __init__(self, spec_dir=None, store: RunStore | None = None,
                 proposer=None, draft_dir=None) -> None:
        self.spec_dir = spec_dir
        self.store = store if store is not None else RunStore(":memory:")
        self.registry = Registry.load(spec_dir) if spec_dir else Registry.load()
        # Every provider call this app has spent, so a test can assert that re-reading a stored
        # run costs none of them (R1). It is also the number a demo operator should watch.
        self.provider_calls = 0

        # THE COMPOSE FRONT END, AND IT IS OFF UNLESS SOMEBODY HANDS IN A PROPOSER.
        #
        # `None` is the default and it is the whole safety property: `python3 -m
        # hotelcontrols.web.server` builds an App with no arguments, so the demo that has
        # always existed behaves exactly as it always did, and every test that exercises it is
        # still testing the thing it was written against. Only `tools/serve.py` injects one.
        #
        # The engine never goes looking for a model - see `compiler/sentences.py`. Everything
        # that can talk to one lives under `tools/`, outside the package, which is what keeps
        # criterion 11 true and both AST guards green.
        self.proposer = proposer
        self.draft_dir = pathlib.Path(draft_dir) if draft_dir else None
        # Compose transcripts, keyed by an id the form carries. In memory and capped: a draft
        # persists to disk, a conversation does not, and nothing here is worth a schema.
        self.conversations: dict[str, tuple[Turn, ...]] = {}

    # ------------------------------------------------------------------ entry points
    def handle(self, path: str) -> Response:
        """Answer any path, always. This is the last thing before a socket.

        Every failure below becomes a page or a JSON object, because a dropped connection tells
        a reader nothing and a stack trace tells them nothing they can act on.
        """
        segments, query, wants_json = self._parse(path)
        try:
            return self.route(segments, query)
        except Exception as exc:                                        # noqa: BLE001
            return self._failure(exc, wants_json)

    def handle_post(self, path: str, body: str) -> Response:
        """The same, for the two routes that write something.

        A SEPARATE entry point rather than a method flag on `handle`, so `handle(path)` stays a
        pure function of a string exactly as `architecture.md` declares it - every existing test
        and every existing docstring about that signature remains true.

        Nothing here writes to a PMS; this engine is read-only against a provider, permanently
        (`prd.md` §6). What a POST writes is our own `spec/drafts/` and our own run store.
        """
        segments, query, wants_json = self._parse(path)
        form = {key: values[0] for key, values
                in urllib.parse.parse_qs(body or "").items() if values}
        try:
            return self.route_post(segments, {**query, **form})
        except Exception as exc:                                        # noqa: BLE001
            return self._failure(exc, wants_json)

    def _parse(self, path: str) -> tuple[tuple[str, ...], dict, bool]:
        split = urllib.parse.urlsplit(path)
        # Unquoted PER SEGMENT, after splitting - never before. Unquoting the whole path first
        # would turn a `%2F` inside an id into a real separator, which silently reshapes the
        # route: `/run/..%2F..%2Fetc%2Fpasswd` would stop being a control id and start being a
        # four-deep path. The id is meant to reach the spec loader, which refuses it by name.
        segments = tuple(urllib.parse.unquote(part) for part in split.path.split("/") if part)
        query = {key: values[0] for key, values
                 in urllib.parse.parse_qs(split.query).items() if values}
        return segments, query, segments[:1] == ("api",)

    def _failure(self, exc: Exception, wants_json: bool) -> Response:
        if isinstance(exc, _Refused):
            return self._error(exc.status, exc.message, wants_json)
        if isinstance(exc, SpecError):
            # The spec layer's refusals are addressed to a reader as they are: "no control
            # called that", "this tenant declares no such setting".
            return self._error(404, str(exc), wants_json)
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
        if parts == ["compose"]:
            return self._compose_page(query)

        raise _Refused(404, "There is nothing at /%s. The controls are listed at /."
                       % "/".join(parts))

    def route_post(self, segments: tuple[str, ...], form: dict) -> Response:
        """The two routes that write. Both belong to the compose front end."""
        parts = list(segments)

        if parts == ["compose"]:
            return self._compose_turn(form)
        if parts == ["compose", "accept"]:
            return self._compose_accept(form)

        raise _Refused(405, "Nothing at /%s accepts a form. The controls are listed at /."
                       % "/".join(parts))

    # ------------------------------------------------------------------ compose
    def _compose_page(self, query: dict, **extra) -> Response:
        """The chat window, or a page explaining why there is not one.

        An absence is STATED rather than 404'd. Everywhere else in this system a thing that
        cannot happen says which thing is missing - a blocked run, an unresolvable field, a
        control that applies to nobody - and a compose route that merely vanished when no
        proposer was wired would be the one place that breaks the habit.
        """
        conversation = query.get("conversation") or ""
        return Response(200, HTML, render.compose_page(
            proposer=self._proposer_name(),
            conversation=conversation,
            transcript=self.conversations.get(conversation, ()),
            templates=self._templates(),
            template=self._template_id(query.get("template")),
            selection=self._selection(query),
            drafts=self._draft_irs(),
            **extra))

    def _compose_turn(self, form: dict) -> Response:
        """One exchange: prose in, a sentence or a question out, nothing written."""
        proposer = self._require_proposer()
        prose = (form.get("prose") or "").strip()
        conversation = form.get("conversation") or uuid.uuid4().hex[:12]
        history = self.conversations.get(conversation, ())

        template = self._template_id(form.get("template"))
        result = normalise(prose, proposer, self.registry,
                           deployment=self._template(template),
                           ir_schema=self._schema(), history=history)

        # Capped, and the cap is the point: a transcript is a convenience, and an unbounded
        # dict keyed by anything a form supplies is a way to spend a demo's memory.
        self.conversations[conversation] = (history + (result.as_turn(),))[-12:]
        if len(self.conversations) > 64:
            self.conversations.pop(next(iter(self.conversations)))

        return self._compose_page({**form, "conversation": conversation,
                                   "template": template}, result=result)

    def _compose_accept(self, form: dict) -> Response:
        """Compile the sentence as it now stands, write it to the drafts directory, and run it.

        The sentence compiled here is whatever is in the BOX, which may be what a person edited
        rather than what the proposer said. That is deliberate: the model's output is a
        suggestion, and the rule that runs is the one a human pressed the button on.
        """
        if self.draft_dir is None:
            raise _Refused(409, "There is nowhere to file a draft: this app was built without "
                                "a drafts directory.")
        sentence = (form.get("sentence") or "").strip()
        if not sentence:
            raise _Refused(400, "There is no sentence to compile.")

        control_id = _slug(form.get("control_id") or "")
        if not control_id:
            raise _Refused(400, "A draft needs an id - lowercase letters, digits and "
                                "underscores - so it can be filed and re-read under one.")
        if control_id in self._controls():
            raise _Refused(409, "%r is already a reviewed control in spec/ir/. Drafts may not "
                                "shadow one: two rules under one id would make a stored run "
                                "ambiguous about which rule produced it." % control_id)

        deployment = dict(self._template(form.get("template")) or {})
        if not deployment:
            raise _Refused(400, "A draft needs a population to run against. Pick one of the "
                                "existing controls' bounded queries.")
        deployment.update({
            "control_id": control_id,
            "version": 1,
            "name": (form.get("name") or "").strip() or control_id.replace("_", " ").title(),
            # Said plainly in the document itself, so the provenance survives being read six
            # months later by somebody who never saw this screen.
            "source_control": "composed",
            "caveats": [
                "Composed from prose through the %s proposer and filed as a DRAFT. The rule "
                "was built by the deterministic grammar from the sentence above, not by the "
                "model - but nobody has reviewed it, and it is not counted in the criterion-1 "
                "figure in docs/plan.md. See spec/drafts/README.md before promoting it."
                % self._proposer_name()],
        })

        compilation = compile_sentence(sentence, self.registry, deployment=deployment,
                                       tenant=self._tenant(self._selection(form)[0]),
                                       ir_schema=self._schema())
        if not compilation.ok:
            return self._compose_page(form, compilation=compilation, sentence=sentence)

        path = self.draft_dir / "ir" / ("%s.json" % control_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(compilation.ir, indent=2) + "\n", encoding="utf-8")

        tenant_id, capture = self._selection(form)
        return Response(303, HTML, render.redirect(
            "/run/%s?property=%s&evidence=%s" % (control_id, tenant_id, capture)))

    # ------------------------------------------------------------------ compose helpers
    def _require_proposer(self):
        if self.proposer is None:
            raise _Refused(409, "No proposer is wired, so there is nothing to ask. Start the "
                                "demo with `python3 -m tools.serve --llm local` (or --llm "
                                "stub, which needs nothing installed).")
        return self.proposer

    def _proposer_name(self) -> str:
        if self.proposer is None:
            return ""
        try:
            return str(self.proposer.name)
        except AttributeError:
            return type(self.proposer).__name__

    def _templates(self) -> tuple[tuple[str, str], ...]:
        """The reviewed controls a draft can borrow a bounded population from.

        A sentence cannot name an endpoint without breaking criterion 5, so the deployment half
        arrives as data - and the honest source of that data is a control that already runs
        over the records the new rule is about. It is also what a hotel adding a second rule
        over the same reservations would actually do.
        """
        return tuple((control_id, self._ir(control_id)["entity"])
                     for control_id in self._controls())

    def _template_id(self, control_id: str | None) -> str:
        """Which control's population a draft is borrowing, defaulted rather than demanded.

        A sentence cannot be judged without a deployment - the validator wants a whole document
        - so asking "does this parse?" with no population picked would answer "it has no
        population", which is true and useless. So one is chosen, and the screen SAYS which:
        a defaulted borrow that is stated is honest, a silent one is not.
        """
        reviewed = self._controls()
        if control_id and control_id in reviewed:
            return control_id
        return reviewed[0] if reviewed else ""

    def _template(self, control_id: str | None) -> dict | None:
        """One control's deployment half, reused verbatim."""
        chosen = self._template_id(control_id)
        if not chosen:
            return None
        return deployment_of(self._ir(chosen).raw)

    def _schema(self) -> dict:
        from ..spec import load_schema
        return load_schema(self.spec_dir) if self.spec_dir else load_schema()

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
                        render.index_page(entries, properties, (tenant_id, capture),
                                          compose=self._proposer_name(),
                                          drafts=self._draft_irs()))

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
                     spec_dir=self._spec_dir_for(control_id))
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
        """The REVIEWED controls. Drafts are deliberately not in here.

        Everything that counts - the index's own list, what a draft may borrow a population
        from, what a draft id may not collide with - reads this, so a composed rule cannot
        quietly become one of the eleven.
        """
        return available(self.spec_dir) if self.spec_dir else available()

    def _drafts(self) -> tuple[str, ...]:
        """Controls composed from prose and filed but not reviewed."""
        if self.draft_dir is None:
            return ()
        return available(self.draft_dir)

    def _draft_irs(self) -> tuple[ControlIR, ...]:
        return tuple(load(control_id, self.draft_dir) for control_id in self._drafts())

    def is_draft(self, control_id: str) -> bool:
        """Whether this id names a draft. Read by the renderer to badge it as unreviewed."""
        return control_id in self._drafts()

    def _spec_dir_for(self, control_id: str):
        """Which spec root holds this control, as `load` and `run` both want it.

        Reviewed controls win over drafts, and `_compose_accept` refuses an id that already
        names one - so the precedence here can never be the thing that decides which of two
        rules a stored run was produced by.
        """
        if control_id in self._controls():
            return self.spec_dir
        if control_id in self._drafts():
            return self.draft_dir
        # Neither. Let the spec loader refuse it by name, exactly as it did before drafts
        # existed - it is the layer that owns that message, and it renders as a 404.
        return self.spec_dir

    def _ir(self, control_id: str) -> ControlIR:
        spec_dir = self._spec_dir_for(control_id)
        return load(control_id, spec_dir) if spec_dir else load(control_id)

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


def _slug(value: str) -> str:
    """A control id from whatever a form supplied, or "" if nothing usable is left.

    Built by KEEPING the characters an id may contain rather than by stripping the ones it may
    not - the allow-list is the only direction that is safe here, because this value becomes a
    file name and arrives from a text box. `load` also refuses an id that is not in its own
    directory listing, so this is the first of two locks on the same door.
    """
    kept = [c if (c.isascii() and (c.isalnum() or c == "_")) else "_"
            for c in (value or "").strip().lower().replace("-", "_").replace(" ", "_")]
    return "_".join(part for part in "".join(kept).split("_") if part)[:64]


_DEFAULT: App | None = None


def handle(path: str) -> Response:
    """`handle(path) -> (status, content_type, body)`, against a default in-memory demo."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = App()
    return _DEFAULT.handle(path)
