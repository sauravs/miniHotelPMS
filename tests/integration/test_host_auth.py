# -*- coding: utf-8 -*-
"""
v3 slice 24's exit tests - D3 §80, against the JSON API and not the UI.

D14: the host authenticates, the engine verifies. With auth ON, the property a request is about
comes from a signed tenant context and from nothing else - not `?property=`, not a POST's
`property` field. So hotel A, holding a perfectly valid context for A, asks for hotel B's things
by every route that has one, naming B as loudly as a URL can, and gets A's own or a 404.

Every test protects criterion V11 (plan-v3 §7) unless it names another; the isolation tests also
protect V4.
"""
import json
import shutil
import urllib.parse

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.web import App
from hotelcontrols.web import auth
from tools.proposers import StubProposer

SECRET = "test-secret-" + "x" * 40        # a test key, long enough to be accepted
CLOCK = FixedClock.at("2026-10-11T09:00", "UTC")
NOW = int(CLOCK.now().timestamp())
A, B = "sandbox", "demo"


def context(prop, subject="someone", expires=None, secret=SECRET):
    return auth.sign(secret, prop, subject, NOW + 300 if expires is None else expires)


def get(app, path, prop=A, token=None):
    response = app.handle(path, context=token if token is not None else context(prop))
    body = response.body
    return response.status, (json.loads(body) if path.startswith("/api/") else body)


def post(app, path, form, prop=A, token=None):
    response = app.handle_post(path, urllib.parse.urlencode(form),
                               context=token if token is not None else context(prop))
    body = response.body
    return response.status, (json.loads(body) if path.startswith("/api/") else body)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One engine, auth ON, and hotel B holding one of everything a JSON route can read:
    a stored run, a task in its queue, a guest decision and a composed draft."""
    drafts = tmp_path_factory.mktemp("auth") / "drafts"
    (drafts / "ir").mkdir(parents=True)
    for name in ("canonical_fields.json", "ir_schema.json"):
        shutil.copy(SPEC_DIR / name, drafts / name)
    app = App(proposer=StubProposer(), draft_dir=drafts, clock=CLOCK,
              auth=auth.Verifier(SECRET, CLOCK))

    # B's run: a FAIL on 007004348 (the overpaid departure) raises B a task.
    status, _ = get(app, "/api/run/checkout_unrefunded_credit", prop=B)
    assert status == 200
    _s, history = get(app, "/api/history/checkout_unrefunded_credit", prop=B)
    _s, queue = get(app, "/api/actions", prop=B)
    _s, decided = post(app, "/api/guest/requests",
                       {"reservation_id": "007004351", "requested_time": "12:00"}, prop=B)
    _s, filed = post(app, "/api/compose/accept", {
        "control_id": "b_only_rule", "template": "checkout_money_owed",
        "sentence": 'every reservation where reservation.status is "checked_out" '
                    "must have folio.balance_due at most 0"}, prop=B)
    assert filed["property"] == B, filed
    return {"app": app, "run": history["runs"][0]["run_id"],
            "action": queue["records"][0]["action_id"],
            "decision": decided["decision_id"], "draft": "b_only_rule"}


# --------------------------------------------------------------------------- isolation
class TestAsContextCannotReadBsAnything:
    """A holds a valid context for A, and names B in the URL or the form every time."""

    def test_bs_stored_run_is_the_same_404_as_a_run_that_never_existed(self, world):
        status, body = get(world["app"], "/api/runs/%s?property=%s" % (world["run"], B))
        assert status == 404, body

    def test_bs_history_is_not_what_a_gets(self, world):
        status, body = get(world["app"], "/api/history/checkout_unrefunded_credit?property=" + B)
        assert status == 200 and body["property"] == A
        assert world["run"] not in json.dumps(body)

    def test_bs_queue_is_not_what_a_gets(self, world):
        status, body = get(world["app"], "/api/actions?property=" + B)
        assert status == 200 and body["property"] == A
        assert world["action"] not in json.dumps(body)

    def test_bs_task_cannot_be_read(self, world):
        status, _ = get(world["app"], "/api/actions/%s?property=%s" % (world["action"], B))
        assert status == 404

    def test_bs_task_cannot_be_moved(self, world):
        app = world["app"]
        status, _ = post(app, "/api/actions/%s" % world["action"],
                         {"state": "dismissed", "property": B})
        assert status == 404
        _s, theirs = get(app, "/api/actions/%s" % world["action"], prop=B)
        assert theirs["state"] == "pending", "A moved B's task"

    def test_bs_guest_decisions_are_not_what_a_gets(self, world):
        status, body = get(world["app"], "/api/guest/decisions?property=" + B)
        assert status == 200 and body["property"] == A
        assert world["decision"] not in json.dumps(body)

    def test_bs_guest_decision_cannot_be_read(self, world):
        status, _ = get(world["app"],
                        "/api/guest/decisions/%s?property=%s" % (world["decision"], B))
        assert status == 404

    def test_bs_drafts_are_not_listed_run_or_read(self, world):
        app = world["app"]
        _s, listed = get(app, "/api/drafts?property=" + B)
        assert world["draft"] not in json.dumps(listed)
        for path in ("/api/run/%s?property=%s", "/api/readiness/%s?property=%s",
                     "/api/history/%s?property=%s"):
            status, _ = get(app, path % (world["draft"], B))
            assert status == 404, path

    def test_a_guest_request_naming_b_is_decided_for_a_under_as_policy(self, world):
        """The POST half: a form's `property` selects nothing either."""
        status, body = post(world["app"], "/api/guest/requests", {
            "property": B, "reservation_id": "007004351", "requested_time": "12:30"})
        assert status in (200, 201) and body["property"] == A, body

    def test_only_as_own_property_is_listed(self, world):
        """Another hotel's name is not A's business either."""
        _s, body = get(world["app"], "/api/properties")
        assert [p["id"] for p in body["properties"]] == [A]
        assert body["default"]["property"] == A

    @pytest.mark.parametrize("path", ["/queue?property=demo", "/guest?property=demo",
                                      "/history/checkout_unrefunded_credit?property=demo"])
    def test_the_engines_own_pages_follow_the_context_too(self, world, path):
        status, page = get(world["app"], path)
        assert status == 200
        assert world["run"] not in page and world["action"] not in page \
            and world["decision"] not in page


# --------------------------------------------------------------------------- bad contexts
GET_ROUTES = ["/", "/queue", "/guest", "/compose", "/run/checkout_money_owed",
              "/history/checkout_money_owed", "/api/controls", "/api/properties",
              "/api/outcomes", "/api/compose", "/api/drafts", "/api/actions",
              "/api/guest/decisions", "/api/history/checkout_money_owed", "/api/runs/abc",
              "/api/run/checkout_money_owed", "/api/readiness/checkout_money_owed",
              "/api/plan/checkout_money_owed?as_of=2026-07-08", "/api/actions/abc",
              "/api/guest/decisions/abc"]
POST_ROUTES = ["/api/guest/requests", "/api/actions/abc", "/api/compose",
               "/api/compose/accept", "/queue/abc", "/guest", "/guest/tasks/abc"]

BAD = {
    "unsigned": "",
    "wrongly signed": context(A, secret="another-secret-" + "y" * 40),
    "expired": context(A, expires=NOW - 1),
    "malformed": "not-a-context",
    "tampered": context(A).replace(context(A).split(".")[0],
                                   context(B).split(".")[0]),
    "too long-lived": context(A, expires=NOW + auth.MAXIMUM_LIFETIME + 60),
}


class TestBadContextsAreRefused:

    @pytest.fixture
    def app(self):
        return App(clock=CLOCK, auth=auth.Verifier(SECRET, CLOCK))

    @pytest.mark.parametrize("kind", sorted(BAD))
    @pytest.mark.parametrize("path", GET_ROUTES)
    def test_every_read_refuses_each_bad_context(self, app, kind, path):
        response = app.handle(path, context=BAD[kind] or None)
        assert response.status == 401, (kind, path, response.body[:200])
        assert app.provider_calls == 0, "a refused request ran a control"

    @pytest.mark.parametrize("kind", sorted(BAD))
    @pytest.mark.parametrize("path", POST_ROUTES)
    def test_every_write_refuses_each_bad_context(self, app, kind, path):
        response = app.handle_post(path, "property=sandbox&state=done", context=BAD[kind] or None)
        assert response.status == 401, (kind, path, response.body[:200])

    def test_each_refusal_says_which_check_failed_and_never_echoes_the_token(self, app):
        reasons = set()
        for kind, token in BAD.items():
            body = json.loads(app.handle("/api/actions", context=token or None).body)
            reasons.add(body["error"])
            if token:
                assert token not in body["error"]
                assert token.split(".")[0] not in body["error"]
        assert len(reasons) >= 5, reasons

    def test_a_context_signed_for_a_property_this_engine_lacks_is_forbidden(self, app):
        response = app.handle("/api/actions", context=context("somewhere-else"))
        assert response.status == 403

    def test_a_token_minted_for_another_audience_is_refused(self, app):
        """The UI's own session cookie is signed with the same secret; it must not open the
        engine. Built by hand here, exactly as `sign` would, with the audience changed."""
        import base64
        import hashlib
        import hmac
        payload = base64.urlsafe_b64encode(json.dumps(
            {"v": 1, "aud": "hotelcontrols-ui-session", "property": A, "sub": "s",
             "exp": NOW + 60}).encode()).rstrip(b"=").decode()
        mac = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), payload.encode(),
                                                hashlib.sha256).digest()).rstrip(b"=").decode()
        assert app.handle("/api/actions", context="%s.%s" % (payload, mac)).status == 401

    def test_the_stylesheet_needs_no_context(self, app):
        """Not tenant data: both surfaces share it, and the UI fetches it before anybody has
        signed in."""
        assert app.handle("/style.css").status == 200

    def test_the_token_never_reaches_the_operational_log(self, app, caplog):
        """V7's rule for a new secret: a context is a credential for fifteen minutes."""
        import logging
        token = context(A)
        with caplog.at_level(logging.INFO, logger="hotelcontrols"):
            app.handle("/api/actions", context=token)
            app.handle("/api/actions", context=BAD["wrongly signed"])
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert token not in logged and token.split(".")[1] not in logged


# --------------------------------------------------------------------------- switching it on
class TestAuthModeIsSwitchedByTheEnvironment:

    def test_absent_secret_means_todays_demo(self, monkeypatch):
        """Auth OFF: no context needed, and every golden in fixtures/api/ stays byte-identical
        (asserted by `tools.dump_api_fixtures --check` in tests/integration/test_api_goldens.py,
        which builds its App with no secret)."""
        app = App()
        assert app.auth is None
        assert app.handle("/api/actions").status == 200

    def test_the_secrets_presence_switches_it_on(self, monkeypatch):
        monkeypatch.setenv(auth.SECRET_VARIABLE, SECRET)
        app = App()
        assert app.auth is not None
        assert app.handle("/api/actions").status == 401

    def test_demanding_auth_with_no_secret_refuses_to_build(self, monkeypatch):
        monkeypatch.setenv(auth.DEMAND_VARIABLE, "1")
        with pytest.raises(auth.AuthMisconfigured) as refusal:
            App()
        assert auth.SECRET_VARIABLE in str(refusal.value)

    @pytest.mark.parametrize("secret", ["", "   ", "short"])
    def test_an_empty_or_short_secret_refuses_rather_than_turning_auth_off(
            self, monkeypatch, secret):
        monkeypatch.setenv(auth.SECRET_VARIABLE, secret)
        with pytest.raises(auth.AuthMisconfigured):
            App()

    def test_the_server_refuses_to_start_and_says_why(self, monkeypatch, capsys):
        from hotelcontrols.web import server

        def never(*_args, **_kwargs):
            # If the server is ever built here, it would listen: fail instead of hanging.
            raise AssertionError("the server started with auth demanded and no secret")

        monkeypatch.setattr(server, "SERVER", never)
        monkeypatch.setenv(auth.DEMAND_VARIABLE, "1")
        assert server.main(["--port", "0"]) == 2
        assert auth.SECRET_VARIABLE in capsys.readouterr().err

    def test_the_server_passes_the_header_through(self):
        from hotelcontrols.web import server
        app = App(clock=CLOCK, auth=auth.Verifier(SECRET, CLOCK))
        assert server.respond(app, "/api/actions")[0] == 401
        assert server.respond(app, "/api/actions", context=context(A))[0] == 200


# --------------------------------------------------------------------------- the verifier itself
class TestTheSignatureIsCompared:

    def test_verification_uses_compare_digest(self):
        """D14 names it: a comparison that stops at the first differing byte leaks how much of
        a forged MAC was right, one timing at a time."""
        import inspect
        assert "hmac.compare_digest" in inspect.getsource(auth.Verifier.verify)

    @staticmethod
    def _sealed(payload_bytes, secret=SECRET):
        """A correctly MACed token over ANY payload - so the checks after the signature can be
        reached with payloads the reference signer would never write."""
        import base64
        import hashlib
        import hmac
        text = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
        mac = base64.urlsafe_b64encode(hmac.new(secret.encode(), text.encode(),
                                                hashlib.sha256).digest()).rstrip(b"=").decode()
        return "%s.%s" % (text, mac)

    @pytest.mark.parametrize("payload", [
        b"not json at all",
        b'["a", "list"]',
        json.dumps({"v": 1, "aud": auth.AUDIENCE, "property": A, "exp": NOW + 60}).encode(),
        json.dumps({"v": 1, "aud": auth.AUDIENCE, "property": A, "sub": "s",
                    "exp": True}).encode(),
        json.dumps({"v": 2, "aud": auth.AUDIENCE, "property": A, "sub": "s",
                    "exp": NOW + 60}).encode(),
    ], ids=["not json", "not an object", "no subject", "a boolean expiry", "another version"])
    def test_a_correctly_signed_but_unreadable_payload_is_refused(self, payload):
        """The signature holding is necessary, not sufficient: what it signs must be a context
        this engine reads. A boolean is refused as an expiry although Python counts it an int."""
        with pytest.raises(auth.ContextRefused) as refusal:
            auth.Verifier(SECRET, CLOCK).verify(self._sealed(payload), [A])
        assert refusal.value.status == 401

    @pytest.mark.parametrize("signature", ["has spaces", "pad=ded", "plus+slash/"])
    def test_a_signature_outside_the_base64url_alphabet_is_refused(self, signature):
        """Strict: a lenient decoder silently drops characters it does not know, and a MAC
        check should never run on bytes the sender did not send."""
        token = "%s.%s" % (context(A).split(".")[0], signature)
        with pytest.raises(auth.ContextRefused) as refusal:
            auth.Verifier(SECRET, CLOCK).verify(token, [A])
        assert "base64url" in refusal.value.message

    def test_expiry_is_judged_by_the_injected_clock_not_the_machines(self):
        """`kernel/clock.py` stays the only wall-clock reader: move the injected clock past the
        expiry and the same token is refused, whatever the machine's time is."""
        token = context(A, expires=NOW + 60)
        assert auth.Verifier(SECRET, CLOCK).verify(token, [A]).property_id == A
        later = FixedClock.at("2026-10-11T09:02", "UTC")
        with pytest.raises(auth.ContextRefused):
            auth.Verifier(SECRET, later).verify(token, [A])


# --------------------------------------------------------------------------- the UI's signer
class TestTheUIsSignerIsTheEngines:
    """The context the React UI signs with `node:crypto` (ui/lib/auth.ts) must be the engine's
    wire form byte for byte, or every request it makes is a 401. One vector, asserted on both
    sides: here, and in ui/test/auth.test.ts."""

    VECTOR = json.loads((SPEC_DIR.parent / "ui" / "test" / "fixtures" / "auth-vector.json")
                        .read_text(encoding="utf-8"))

    def test_the_engines_reference_signer_writes_the_vector(self):
        v = self.VECTOR
        assert auth.sign(v["secret"], v["property"], v["sub"], v["exp"]) == v["token"]

    def test_the_engine_verifies_the_vector_token(self):
        import datetime
        v = self.VECTOR
        # A clock inside the token's last minute, so the short-lifetime rule holds as well.
        clock = FixedClock(datetime.datetime.fromtimestamp(v["exp"] - 30, datetime.timezone.utc))
        verified = auth.Verifier(v["secret"], clock).verify(v["token"], [v["property"]])
        assert (verified.property_id, verified.subject) == (v["property"], v["sub"])
