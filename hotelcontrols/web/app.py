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

WHERE A FAILED CONTROL BECOMES A TASK (slice 18)
-------------------------------------------------
Here, one layer above the run, and never inside it: `runner/` is untouched. `_execute` saves a
run and then asks `actions.findings_from` what it raises, and the store keeps one task per
natural key. Only a reviewed control raises one - a draft's `action` block is borrowed from the
control whose population it borrowed, so its severity and audience were never decided by
anybody. The POSTs that move a task write our own store and nothing else.

AND, WHEN SOMEBODY WIRES ONE, EMAILS IT (slice 19)
---------------------------------------------------
A `Notifier` is injected - by `tools/serve.py`, never looked up - and `_execute` hands it the
tasks the run just failed, each emailed once. With none wired, which is the default and what
`python3 -m hotelcontrols.web.server` builds, nothing is sent and every payload is exactly what
it was before this slice.

AND WRITES DOWN WHAT IT DID (slice 20)
---------------------------------------
Three operational records, all from this layer: one per REQUEST (path without its query string,
status, duration), one per RUN (after it is saved, so it carries its `run_id`: calls, counts,
coverage, duration), and one per DISPATCH (audience and outcome). The run's own identity is
gathered into `_trace` while a request is handled, so the request line can name the run it
caused. `runner/` is untouched; nothing is logged below this layer.
"""
from __future__ import annotations

import json
import pathlib
import urllib.parse
import uuid
from dataclasses import replace
from typing import NamedTuple

from ..actions import OPERATOR, TransitionRefused, dispatch, findings_from
from ..ops import OpsLog, elapsed_ms
from ..compiler import Turn, compile_sentence, deployment_of, normalise
from ..kernel import FixedClock, Outcome, PropertyClock
from ..providers import registry as providers
from ..runner import Coverage, next_evaluation, readiness, run
from ..spec import (ControlIR, Registry, SpecError, TenantConfig, available, available_tenants,
                    load, provider_map)
from ..store import RunStore
from . import render

HTML = "text/html; charset=utf-8"

# Where an email's link points when nobody says otherwise: this engine's own default address.
# Not a secret, so it has a default - the same reasoning as the React UI's engine address.
PUBLIC_URL = "http://127.0.0.1:8765"
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
                 proposer=None, draft_dir=None, clock=None, notifier=None,
                 public_url: str = PUBLIC_URL, ops: OpsLog | None = None) -> None:
        self.spec_dir = spec_dir
        self.store = store if store is not None else RunStore(":memory:")
        # THE CLOCK A PERSON'S MOVES ARE STAMPED WITH (slice 18). A run's instants come from
        # the fixed clock its evidence decides; marking a task done happens NOW, at the hotel.
        # Injected so a test can pin it. None means each property's own clock, read through
        # the kernel - `kernel/clock.py` stays the only module that reads a wall clock.
        self.clock = clock
        # EMAIL IS OFF UNLESS SOMEBODY HANDS IN A NOTIFIER (slice 19) - the same safety property
        # as the proposer below. The engine never goes looking for one, and the only backend
        # that can reach a mail server lives in `tools/notifiers/`, behind two locks.
        self.notifier = notifier
        self.public_url = public_url
        # THE OPERATIONAL LOG (slice 20). Stamped by the injected clock when there is one, by
        # the kernel's clock in UTC otherwise. Its logger has no handler until the server
        # attaches one (`--log`), so an App built in a test or a notebook writes nothing.
        self.ops = ops if ops is not None else OpsLog(clock=clock)
        # The identity of whatever this request touched - its property, and the run it made -
        # gathered while it is handled so the request line can carry it. Reset per request;
        # the server is serial, so one request is handled at a time.
        self._trace: dict = {}
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
        started = self._begin()
        try:
            response = self.route(segments, query)
        except Exception as exc:                                        # noqa: BLE001
            response = self._failure(exc, wants_json)
        return self._logged("GET", path, response, started)

    def handle_post(self, path: str, body: str) -> Response:
        """The same, for the routes that write something.

        A SEPARATE entry point rather than a method flag on `handle`, so `handle(path)` stays a
        pure function of a string exactly as `architecture.md` declares it - every existing test
        and every existing docstring about that signature remains true.

        Nothing here writes to a PMS; this engine is read-only against a provider, permanently
        (`prd.md` §6). What a POST writes is our own `spec/drafts/` and our own run store -
        which, since slice 18, holds the findings queue a person moves tasks through.
        """
        segments, query, wants_json = self._parse(path)
        form = {key: values[0] for key, values
                in urllib.parse.parse_qs(body or "").items() if values}
        started = self._begin()
        try:
            response = self.route_post(segments, {**query, **form})
        except Exception as exc:                                        # noqa: BLE001
            response = self._failure(exc, wants_json)
        return self._logged("POST", path, response, started)

    def _begin(self):
        self._trace = {}
        return self.ops.now()

    def _logged(self, method: str, path: str, response: Response, started) -> Response:
        """One request line. The PATH only - never the query string, never a form body - which
        is the access log's existing rule (`server.Handler.log_message`), kept."""
        self.ops.emit("request", method=method, path=urllib.parse.urlsplit(path).path,
                      status=response.status,
                      duration_ms=elapsed_ms(started, self.ops.now()), **self._trace)
        return response

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
            return self._history(parts[1], query)
        if len(parts) == 3 and parts[:2] == ["api", "run"]:
            return self._run_json(parts[2], query)
        if len(parts) == 3 and parts[:2] == ["api", "runs"]:
            return self._stored_run(parts[2], query)
        if len(parts) == 3 and parts[:2] == ["api", "readiness"]:
            return Response(200, JSON, render.readiness_json(
                parts[2], self._readiness(self._ir(parts[2], self._selection(query)[0]))))
        if parts == ["compose"]:
            return self._compose_page(query)
        # Slice 15: what a second client needs to build the index and history pages.
        if parts == ["api", "controls"]:
            return self._controls_json()
        if parts == ["api", "properties"]:
            return self._properties_json()
        if len(parts) == 3 and parts[:2] == ["api", "history"]:
            return self._history_json(parts[2], query)
        if parts == ["api", "drafts"]:
            return self._drafts_json(query)
        if parts == ["api", "outcomes"]:
            return self._outcomes_json()
        if parts == ["api", "compose"]:
            return self._compose_state_json(query)
        if len(parts) == 3 and parts[:2] == ["api", "plan"]:
            return self._plan_json(parts[2], query)
        # Slice 18: the findings queue, as a page and as data.
        if parts == ["queue"]:
            return self._queue_page(query)
        if parts == ["api", "actions"]:
            return self._queue_json(query)
        if len(parts) == 3 and parts[:2] == ["api", "actions"]:
            return self._action_json(parts[2], query)

        raise _Refused(404, "There is nothing at /%s. The controls are listed at /."
                       % "/".join(parts))

    def route_post(self, segments: tuple[str, ...], form: dict) -> Response:
        """The routes that write: the compose front end, and moving a task in the queue."""
        parts = list(segments)

        if parts == ["compose"]:
            return self._compose_turn(form)
        if parts == ["compose", "accept"]:
            return self._compose_accept(form)
        # Slice 15, with the owner's sign-off: the same two writes, as JSON, for the second
        # surface. Same proposer, same grammar, same validator, same draft file.
        if parts == ["api", "compose"]:
            return self._compose_turn_json(form)
        if parts == ["api", "compose", "accept"]:
            return self._compose_accept_json(form)
        # Slice 18: a person marks a task done or dismisses it. Our store, nothing else.
        if len(parts) == 3 and parts[:2] == ["api", "actions"]:
            return self._move_json(parts[2], form)
        if len(parts) == 2 and parts[0] == "queue":
            return self._move_page(parts[1], form)

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
            drafts=self._draft_irs(self._selection(query)[0]),
            **extra))

    def _compose_turn(self, form: dict) -> Response:
        """One exchange: prose in, a sentence or a question out, nothing written."""
        conversation, template, result = self._turn(form)
        return self._compose_page({**form, "conversation": conversation,
                                   "template": template}, result=result)

    def _turn(self, form: dict):
        """The exchange itself, shared by the HTML and the JSON window so they cannot differ."""
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
        return conversation, template, result

    def _compose_accept(self, form: dict) -> Response:
        """Compile the sentence as it now stands, write it to the drafts directory, and run it.

        The sentence compiled here is whatever is in the BOX, which may be what a person edited
        rather than what the proposer said. That is deliberate: the model's output is a
        suggestion, and the rule that runs is the one a human pressed the button on.
        """
        control_id, sentence, compilation = self._file_draft(form)
        if not compilation.ok:
            return self._compose_page(form, compilation=compilation, sentence=sentence)
        tenant_id, capture = self._selection(form)
        return Response(303, HTML, render.redirect(
            "/run/%s?property=%s&evidence=%s" % (control_id, tenant_id, capture)))

    def _file_draft(self, form: dict):
        """Compile the sentence in the box and, only if it compiles, write it as a draft.

        Shared by the HTML and the JSON window. Returns the compilation either way, so each
        surface can show the validator's own reasons for a refusal.
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
        if compilation.ok:
            # Filed under the property it was composed for (slice 17, QA Q10 collision A2): two
            # hotels composing `late_checkout_policy` are two drafts, not one overwriting the
            # other. Reviewed controls in spec/ir/ stay a shared library by design.
            path = self._draft_root(self._selection(form)[0]) / "ir" / ("%s.json" % control_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(compilation.ir, indent=2) + "\n", encoding="utf-8")
        return control_id, sentence, compilation

    # ------------------------------------------------------------------ compose, as JSON
    def _compose_state_json(self, query: dict) -> Response:
        """Whether compose is wired, by which proposer, and one conversation's transcript.

        Read-only, and an absence is STATED: with no proposer this answers `wired: false`
        rather than 404, exactly as the HTML window explains itself instead of vanishing.
        """
        conversation = query.get("conversation") or ""
        return Response(200, JSON, json.dumps({
            "wired": self.proposer is not None,
            "proposer": self._proposer_name() or None,
            "drafts_wired": self.draft_dir is not None,
            "templates": [{"control_id": c, "entity": e} for c, e in self._templates()],
            "template": self._template_id(query.get("template")),
            "conversation": conversation,
            "transcript": [_turn_json(t) for t in self.conversations.get(conversation, ())],
        }, indent=2))

    def _compose_turn_json(self, form: dict) -> Response:
        """One exchange, as data. Writes nothing but the in-memory transcript."""
        conversation, template, result = self._turn(form)
        ok = result.ok
        return Response(200, JSON, json.dumps({
            "conversation": conversation,
            "template": template,
            "proposer": self._proposer_name(),
            "result": {
                "prose": result.prose,
                "sentence": result.sentence,
                "question": result.question,
                "is_question": result.is_question,
                "ok": ok,
                # Exactly the reasons the HTML refusal lists, from the same objects.
                "problems": list(result.as_turn().problems),
                "fields": ([entry["field"] for entry in
                            result.compilation.ir.get("required_evidence", [])] if ok else []),
            },
            "transcript": [_turn_json(t) for t in self.conversations.get(conversation, ())],
        }, indent=2))

    def _compose_accept_json(self, form: dict) -> Response:
        """File the sentence sent back as a draft - 201 - or say why not - 422.

        Does NOT run it. Running spends provider calls, and the client decides that as a
        separate, deliberate step; the answer names the property and evidence to run it on.
        """
        control_id, sentence, compilation = self._file_draft(form)
        if not compilation.ok:
            reasons = ([str(p) for p in compilation.problems]
                       + ["ambiguous: %s" % a for a in compilation.ambiguities])
            return Response(422, JSON, json.dumps({
                "error": "This sentence does not compile, so nothing was filed.",
                "status": 422, "sentence": sentence, "problems": reasons}, indent=2))
        tenant_id, capture = self._selection(form)
        return Response(201, JSON, json.dumps({
            "control_id": control_id, "property": tenant_id, "evidence": capture,
            "reviewed": False}, indent=2))

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
                                          drafts=self._draft_irs(tenant_id)))

    def _run_page(self, control_id: str, query: dict) -> Response:
        result, ir, tenant = self._execute(control_id, query)
        links = {capture: "/run/%s?property=%s&evidence=%s" % (control_id, tenant.tenant_id,
                                                               capture)
                 for capture in providers.load(tenant.provider).captures}
        return Response(200, HTML, render.run_page(result, plan=self._plan(ir, tenant, result.as_of),
                                                   readiness=self._readiness(ir), links=links))

    def _run_json(self, control_id: str, query: dict) -> Response:
        result, ir, tenant = self._execute(control_id, query)
        return Response(200, JSON, render.run_json(result, plan=self._plan(ir, tenant, result.as_of),
                                                   readiness=self._readiness(ir)))

    def _stored_run(self, run_id: str, query: dict) -> Response:
        """A past run, re-read from SQLite. Zero provider calls, by construction (R1).

        Read FOR the selected property (slice 17). Another property's run is the same 404 as a
        run that never existed, word for word, so the difference cannot be used to learn which
        run ids exist in somebody else's hotel. Until slice 24, `?property=` is a selection and
        not an identity; what this guarantees is that the selection is honoured.
        """
        stored = self.store.load(run_id, tenant_id=self._selection(query)[0])
        if stored is None:
            raise _Refused(404, "No stored run called %r. Past runs are listed at "
                                "/history/<control_id>." % run_id)
        return Response(200, JSON, render.run_json(stored))

    def _history(self, control_id: str, query: dict) -> Response:
        tenant_id = self._selection(query)[0]
        self._ir(control_id, tenant_id)   # refuse an unknown id here rather than an empty page
        return Response(200, HTML, render.history_page(
            control_id, self.store.history(control_id, tenant_id=tenant_id),
            tenant_id=tenant_id))

    # ------------------------------------------------------------------ JSON for a second client
    # Slice 15 adds a React UI as a SECOND client of this API, and these four routes are what it
    # could not build from the three that existed. All read-only, all answerable without running
    # a control, and all built from the serialisers `render.py` already has - one shape per
    # object, because two shapes for the same readiness report is how two surfaces drift apart.
    def _controls_json(self) -> Response:
        """Every reviewed control and its readiness per provider, in ONE request.

        One rather than eleven because the server is serial, and must stay so until the store
        is thread-safe: eleven parallel readiness fetches would be served one at a time.
        """
        return Response(200, JSON, json.dumps(
            {"controls": [self._control_json(ir, reviewed=True)
                          for ir in map(self._ir, self._controls())]}, indent=2))

    def _drafts_json(self, query: dict) -> Response:
        """The composed controls, each flagged unreviewed IN the object, not by its list.

        With no drafts directory the absence is stated: "nothing filed" and "nowhere to file"
        are different answers, and a bare empty list would give the first for the second.
        """
        return Response(200, JSON, json.dumps(
            {"wired": self.draft_dir is not None,
             "drafts": [self._control_json(ir, reviewed=False)
                        for ir in self._draft_irs(self._selection(query)[0])]},
            indent=2))

    def _outcomes_json(self) -> Response:
        """The four answers' words, in the page's two orders - served, never restated.

        A run payload carries each verdict's `means` but not its badge, and criterion 2's third
        signal is the badge. A client that typed "VIOLATION" into its own source would hold a
        second copy of `render.WORDING`, free to drift; this is the only copy, served.
        """
        return Response(200, JSON, json.dumps({
            "outcomes": [{"outcome": outcome.value,
                          "badge": render.WORDING[outcome][0],
                          "means": render.WORDING[outcome][1],
                          "group_meaning": render.GROUP_MEANING[outcome],
                          "open": outcome in render.OPEN_GROUPS}
                         for outcome in render.TILE_ORDER],
            "group_order": [outcome.value for outcome in render.GROUP_ORDER]}, indent=2))

    def _plan_json(self, control_id: str, query: dict) -> Response:
        """When this control runs next on this property's provider, as of a given instant.

        For a run read back from the store, which does not carry its plan. A plan is a fact
        about the spec - the declared trigger, the provider's events, an instant - like
        readiness, so it is served beside the stored run rather than bolted into it, and every
        existing route stays byte-identical. Costs no provider call: building an adapter reads
        no evidence, and `events()` is a declaration.

        `as_of` is REQUIRED. A plan is relative to an instant, and defaulting to today would
        answer a different question from the stored run it is shown beside.
        """
        tenant_id, _capture = self._selection(query)
        ir = self._ir(control_id, tenant_id)
        tenant = self._tenant(tenant_id)
        as_of = query.get("as_of")
        if not as_of:
            raise _Refused(400, "A plan is relative to an instant: give as_of=YYYY-MM-DD, the "
                                "instant the run asked about.")
        try:
            plan = self._plan(ir, tenant, as_of)
        except (TypeError, ValueError):
            raise _Refused(400, "%r is not a date this engine can read. Write it as "
                                "YYYY-MM-DD." % as_of) from None
        return Response(200, JSON, json.dumps({
            "control_id": ir.control_id, "property": tenant_id, "as_of": as_of,
            "mode": plan.mode, "declared_mode": plan.declared_mode,
            "fell_back": plan.fell_back, "headline": plan.headline}, indent=2))

    def _control_json(self, ir: ControlIR, reviewed: bool) -> dict:
        return {"control_id": ir.control_id, "name": ir.name,
                "natural_language": ir.natural_language, "entity": ir["entity"],
                "reviewed": reviewed,
                "readiness": [render._readiness_json(r) for r in self._readiness(ir)]}

    def _properties_json(self) -> Response:
        """Each property, its provider and the evidence it can be replayed against.

        `default` is the selection a request naming nothing would use, stated rather than left
        for the client to guess: a client that picked its own default could ask a different
        question than the page it mirrors. Nothing here builds an adapter - a package's list of
        captures is metadata, not a call.
        """
        properties = []
        for name in available_tenants(self.spec_dir) if self.spec_dir else available_tenants():
            tenant = self._tenant(name)
            package = providers.load(tenant.provider)
            properties.append({"id": name, "name": tenant.name, "provider": tenant.provider,
                               "captures": list(package.captures),
                               "default_capture": package.default_capture})
        tenant_id, capture = self._selection({})
        return Response(200, JSON, json.dumps(
            {"properties": properties, "default": {"property": tenant_id, "evidence": capture}},
            indent=2))

    def _history_json(self, control_id: str, query: dict) -> Response:
        """The rows `/history/<id>` renders, as data, with the two gates a chart needs.

        THE SAME RULES `run_json` KEEPS, because a history row is a run seen from further away.
        A blocked run carries its reason and NO counts. A run that concluded nothing keeps its
        counts - `ooo_room_protection`'s 28 exclusions are true - but says `concluded: false`
        beside them, so a client has a gate that is not "are there numbers?" (trap 1, F5).
        `concluded` comes from the engine's own `Coverage`, never re-derived here.

        Newest first with ties broken by `run_id`, in the store's own ORDER BY (issue #35), so
        this payload, the page and the golden copy in `fixtures/api/` list runs in one order.

        ONE PROPERTY'S runs (slice 17), and `property` says which: `?property=` falls back to
        the default when it names nothing, and a client must be able to see that it was given
        the default's history rather than the one it asked for.
        """
        tenant_id = self._selection(query)[0]
        self._ir(control_id, tenant_id)   # the same 404 the page gives, for the same reason
        runs = [_history_entry(row)
                for row in self.store.history(control_id, tenant_id=tenant_id)]
        return Response(200, JSON, json.dumps(
            {"control_id": control_id, "property": tenant_id, "runs": runs}, indent=2))

    # ------------------------------------------------------------------ the findings queue
    # Slice 18 (G2(a), G8's queue). A task a person can see, mark done or dismiss - and beside
    # the tasks, what each control last concluded, because an empty queue must never read as
    # "all clear" (criterion 8 applied to a new surface).
    def _queue_page(self, query: dict) -> Response:
        tenant_id = self._selection(query)[0]
        return Response(200, HTML, render.queue_page(
            tenant_id, self._property_ids(), self.store.actions(tenant_id=tenant_id),
            self._queue_controls(tenant_id), self.store.persistent,
            email=self._notifier_name()))

    def _queue_json(self, query: dict) -> Response:
        """One property's queue as data: its tasks, and each control's latest conclusion.

        `persistent` and its sentence are IN the payload because the demo's default store is in
        memory, and a client showing a queue must be able to say it is lost on restart rather
        than imply a persistence it lacks (brief §8.8).
        """
        tenant_id = self._selection(query)[0]
        records = self.store.actions(tenant_id=tenant_id)
        wired = self.notifier is not None
        payload = {
            "property": tenant_id,
            "persistent": self.store.persistent,
            "persistence": render.persistence_sentence(self.store.persistent),
            "pending": sum(1 for r in records if r.is_pending),
            "records": [render.action_json(r, delivery=wired) for r in records],
            "controls": self._queue_controls(tenant_id),
        }
        # Slice 19, present ONLY when a notifier is wired. Unwired is today's demo exactly, so
        # every golden in fixtures/api/ stays byte-identical - this slice may not touch them.
        if wired:
            payload["email"] = {"wired": True, "via": self._notifier_name()}
        return Response(200, JSON, json.dumps(payload, indent=2))

    def _action_json(self, action_id: str, query: dict) -> Response:
        """One task, for the selected property. Another property's task is the same 404 as a
        task that never existed, word for word (slice 17's rule, on slice 18's table)."""
        record = self.store.action(action_id, tenant_id=self._selection(query)[0])
        if record is None:
            raise _Refused(404, _no_such_action(action_id))
        return Response(200, JSON, json.dumps(
            render.action_json(record, delivery=self.notifier is not None), indent=2))

    def _move_json(self, action_id: str, form: dict) -> Response:
        _tenant_id, moved = self._move(action_id, form)
        return Response(200, JSON, json.dumps(
            render.action_json(moved, delivery=self.notifier is not None), indent=2))

    def _move_page(self, action_id: str, form: dict) -> Response:
        """The page's two buttons. A 303 back to the queue, so a reload re-reads the queue
        rather than re-posting the move - the same reason compose ends in a redirect."""
        tenant_id, _moved = self._move(action_id, form)
        return Response(303, HTML, render.redirect(
            "/queue?property=%s" % tenant_id, title="Moved",
            subtitle="The task was updated.", sentence="Task updated",
            onward="the queue"))

    def _move(self, action_id: str, form: dict):
        """pending -> done | dismissed, stamped through the injected clock, by the operator.

        `operator` until slice 24 gives the engine a verified identity. A malformed state is a
        400, a closed task a 409, and a task this property does not have a 404.
        """
        tenant_id = self._selection(form)[0]
        try:
            moved = self.store.transition(action_id, form.get("state") or "",
                                          tenant_id=tenant_id, at=self._now(tenant_id),
                                          actor=OPERATOR)
        except TransitionRefused as exc:
            raise _Refused(409, str(exc)) from None
        except ValueError as exc:
            raise _Refused(400, str(exc)) from None
        if moved is None:
            raise _Refused(404, _no_such_action(action_id))
        return tenant_id, moved

    def _queue_controls(self, tenant_id: str) -> list[dict]:
        """Every reviewed control, with what its latest run in this store concluded.

        Four answers, and only one of them is a conclusion: never run here, blocked, reached no
        conclusion, or concluded about N of M records. The latest run is read exactly as the
        history reads it, through `_history_entry`, so the two cannot word it differently.
        Drafts are not listed: they raise no task (see the module docstring).
        """
        pending: dict[str, int] = {}
        for record in self.store.actions(tenant_id=tenant_id):
            if record.is_pending:
                pending[record.control_id] = pending.get(record.control_id, 0) + 1
        controls = []
        for ir in map(self._ir, self._controls()):
            rows = self.store.history(ir.control_id, limit=1, tenant_id=tenant_id)
            latest = _history_entry(rows[0]) if rows else None
            status, headline = _status_of(latest)
            controls.append({
                "control_id": ir.control_id, "name": ir.name,
                "severity": ir["action"]["severity"], "audience": ir["action"].get("audience"),
                # `label` is the status in words, served so a second client never types its
                # own copy of them - the `/api/outcomes` rule, applied to the queue.
                "status": status, "label": render.STATUS_WORDS[status], "headline": headline,
                "pending": pending.get(ir.control_id, 0), "latest_run": latest})
        return controls

    def _now(self, tenant_id: str):
        """The instant a person acted, at the hotel. Through the kernel, never `datetime`."""
        clock = self.clock or PropertyClock(self._tenant(tenant_id).timezone)
        return clock.now()

    def _notifier_name(self) -> str:
        """The wired notifier's name, or "" when email is not wired."""
        if self.notifier is None:
            return ""
        return str(getattr(self.notifier, "name", type(self.notifier).__name__))

    def _property_ids(self) -> tuple[str, ...]:
        return tuple(available_tenants(self.spec_dir) if self.spec_dir else available_tenants())

    # ------------------------------------------------------------------ doing the work
    def _execute(self, control_id: str, query: dict):
        """Run one control over one body of evidence, and keep the result."""
        tenant_id, capture = self._selection(query)
        ir = self._ir(control_id, tenant_id)
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

        started = self.ops.now()
        result = run(control_id, tenant, adapter, clock, evidence_label=capture,
                     spec_dir=self._spec_dir_for(control_id, tenant_id))
        self.provider_calls += result.calls
        saved = replace(result, run_id=self.store.save(result))
        # Slice 20: from here on, every line this request writes names this run.
        self._trace.update(tenant_id=tenant_id, run_id=saved.run_id, control_id=control_id,
                           policy_version=saved.policy_version, provider=saved.provider)
        raised = 0
        # THE LAYER ABOVE THE RUN RAISES ITS TASKS (slice 18). Only a FAIL raises one, only for
        # a reviewed control, and only once per natural key however often this is re-run. A
        # draft raises none: its `action` block was borrowed along with its population.
        deliveries = ()
        if control_id in self._controls():
            findings = findings_from(saved, ir)
            raised = self.store.record_findings(findings)
            # Slice 19: each task this run failed, emailed once. Scoped to THIS run's FAILs, so a
            # run that concluded nothing or was blocked sends nothing, by construction.
            if self.notifier is not None:
                deliveries = dispatch(saved, findings, self.store, self.notifier,
                                      public_url=self.public_url, at=self._now(tenant_id))
        self._log_run(saved, started, raised)
        for delivery in deliveries:
            # The audience and the outcome. Never the note and never the addresses: a route is
            # staff personal data, and a note is a backend's words.
            record = self.store.action(delivery.action_id, tenant_id=tenant_id)
            self.ops.emit("dispatch", action_id=delivery.action_id, outcome=delivery.outcome,
                          audience=record.audience if record else None, **self._trace)
        return saved, ir, tenant

    def _log_run(self, saved, started, raised: int) -> None:
        """One run line: what it asked, what it cost, and whether it concluded anything.

        Counts only for a run that was not blocked - the payload's own rule (F5) - and the
        blocked REASON is not copied: it is a provider's words, and nothing a provider says is
        logged above the boundary. `blocked: true` and the run id lead to it on the run itself.
        """
        coverage = saved.coverage
        fields = dict(evidence=saved.evidence_label, as_of=saved.as_of, calls=saved.calls,
                      blocked=saved.is_blocked,
                      coverage={"evaluated": coverage.evaluated, "total": coverage.total,
                                "concluded": coverage.concluded},
                      raised=raised, started_at=started.isoformat(),
                      duration_ms=elapsed_ms(started, self.ops.now()))
        if not saved.is_blocked:
            fields["counts"] = saved.counts
        self.ops.emit("run", **fields, **self._trace)

    def _plan(self, ir: ControlIR, tenant: TenantConfig, as_of: str) -> object:
        """When this control runs next on this provider - finding F7, on the page at last.

        Rendered beside the verdicts because the two answer different halves of one question:
        the verdicts say what is true now, and the plan says how soon we would notice if it
        stopped being true.
        """
        package = providers.load(tenant.provider)
        adapter, _source = package.build(tenant, package.default_capture)
        return next_evaluation(ir, adapter.events(), FixedClock.at(as_of, tenant.timezone))

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

    def _draft_root(self, tenant_id: str):
        """One property's drafts: a spec root of its own, `<drafts>/<property>/ir/*.json`.

        Per property since slice 17 (QA Q10, collision A2). A spec root, so `available` and
        `load` read it with no change to the spec layer. `tenant_id` has already been through
        `_selection`, so it names a configured property and never a path of its own.
        """
        return self.draft_dir / tenant_id

    def _drafts(self, tenant_id: str) -> tuple[str, ...]:
        """Controls this property composed from prose and filed but not reviewed."""
        if self.draft_dir is None or not (self._draft_root(tenant_id) / "ir").is_dir():
            return ()
        return available(self._draft_root(tenant_id))

    def _draft_irs(self, tenant_id: str) -> tuple[ControlIR, ...]:
        return tuple(load(control_id, self._draft_root(tenant_id))
                     for control_id in self._drafts(tenant_id))

    def is_draft(self, control_id: str, tenant_id: str) -> bool:
        """Whether this id names one of this property's drafts, to badge it as unreviewed."""
        return control_id in self._drafts(tenant_id)

    def _spec_dir_for(self, control_id: str, tenant_id: str | None = None):
        """Which spec root holds this control, as `load` and `run` both want it.

        Reviewed controls win over drafts, and `_compose_accept` refuses an id that already
        names one - so the precedence here can never be the thing that decides which of two
        rules a stored run was produced by. A draft is found only under the property asking:
        another property's draft of the same name is not this property's rule (slice 17).
        """
        if control_id in self._controls():
            return self.spec_dir
        if tenant_id is not None and control_id in self._drafts(tenant_id):
            return self._draft_root(tenant_id)
        # Neither. Let the spec loader refuse it by name, exactly as it did before drafts
        # existed - it is the layer that owns that message, and it renders as a 404.
        return self.spec_dir

    def _ir(self, control_id: str, tenant_id: str | None = None) -> ControlIR:
        spec_dir = self._spec_dir_for(control_id, tenant_id)
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
        # The VALIDATED property, for this request's log line (slice 20) - never the raw value
        # from the URL, which is whatever somebody typed.
        self._trace.setdefault("tenant_id", tenant_id)
        package = providers.load(self._tenant(tenant_id).provider)
        capture = query.get("evidence")
        if capture not in package.captures:
            capture = package.default_capture
        return tenant_id, capture

    def captures_for(self, tenant_id: str) -> tuple[str, ...]:
        """Every body of evidence this property's provider can be replayed against."""
        return providers.load(self._tenant(tenant_id).provider).captures


def _history_entry(row) -> dict:
    """One stored run, summarised under the run page's rules - shared by history and the queue.

    THE SAME RULES `run_json` KEEPS, because a history row is a run seen from further away. A
    blocked run carries its reason and NO counts. A run that concluded nothing keeps its counts
    but says `concluded: false` beside them, and `concluded` comes from the engine's own
    `Coverage`, never re-derived here.
    """
    counts = {outcome.value: row[render._HISTORY_COLUMN[outcome]] or 0 for outcome in Outcome}
    counts["total"] = row["total"] or 0
    evaluated = sum(counts[outcome.value] for outcome in Outcome if outcome.is_answer)
    # `policy_version` and `policy_digest` (slice 16): which rule judged the run, or null for
    # one stored before rules carried a version. The page groups by the pair.
    entry = {key: row[key] for key in ("run_id", "created_at", "provider", "evidence_label",
                                       "as_of", "calls", "policy_version", "policy_digest",
                                       "blocked")}
    coverage = Coverage(evaluated=evaluated, total=counts["total"])
    entry["concluded"] = coverage.concluded
    # The sentence that goes where the counts would be, in the engine's words. Not for a
    # blocked run: coverage of zero verdicts says "the population was empty", which is false
    # for a run that never obtained its evidence - its reason is the sentence.
    entry["headline"] = None if row["blocked"] else coverage.headline
    if not row["blocked"]:
        entry["counts"] = counts
    return entry


def _status_of(latest: dict | None) -> tuple[str, str]:
    """What a control's latest run lets the queue say about it - and only one answer is a
    conclusion. The other three are the reason an empty queue is not an all-clear."""
    if latest is None:
        return ("not_run", "Not run against this store yet, so this queue knows nothing about "
                           "it. That is not a pass.")
    if latest["blocked"]:
        return ("blocked", "Its latest run could not happen, so it has said nothing about this "
                           "property. The reason is on the run.")
    if not latest["concluded"]:
        return ("no_conclusion", latest["headline"])
    counts = latest["counts"]
    evaluated = counts["PASS"] + counts["FAIL"]
    found = ("no violation in them" if counts["FAIL"] == 0 else
             "%d violation%s" % (counts["FAIL"], "" if counts["FAIL"] == 1 else "s"))
    return ("concluded", "Its latest run concluded about %d of %d record(s) and found %s."
            % (evaluated, counts["total"], found))


def _no_such_action(action_id: str) -> str:
    """The one 404 for a task, whether it never existed or belongs to another property."""
    return ("No task called %r in this property's queue. The queue is at /queue." % action_id)


def _turn_json(turn: Turn) -> dict:
    """One exchange of a transcript, as data."""
    return {"prose": turn.prose, "sentence": turn.sentence, "question": turn.question,
            "problems": list(turn.problems)}


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
