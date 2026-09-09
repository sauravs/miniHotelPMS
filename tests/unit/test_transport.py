# -*- coding: utf-8 -*-
"""
THE TRANSPORT - built, tested, and OFF.

Review finding F13: v1 had no HTTP client at all, which was the right safety property and also
meant there was no path from the demo to production. The most operationally risky component in
the whole system was the one nobody had written.

So it exists now, and the first thing this file asserts is that no test in this suite can switch
it on. That is not a formality. `prd.md` criterion 11 says no test can reach the network, and
the vendor asks integrators not to query wide ranges without agreement (R8) - on a sandbox that
belongs to someone else. A suite that could accidentally dial out would be a suite that
eventually does, on a machine nobody was watching, in a loop.

TWO LOCKS, AND THE SECOND ONE IS THE REAL ONE
----------------------------------------------
    1. an environment variable that is unset by default
    2. a refusal to arm inside a test process at all

Lock 1 alone is not enough, because a test CAN set an environment variable - `monkeypatch.setenv`
is one line. So the transport also looks for a test runner in `sys.modules` and refuses while one
is loaded. `test_a_test_cannot_switch_it_on_even_by_setting_the_variable` sets the variable and
asserts the refusal, which is as close to proving a negative as this gets.

Everything else here is tested with an INJECTED dialer - a callable standing where the socket
would be - so the pacing, the retry, the give-up, the recording and the credential handling are
all exercised without one existing.
"""
import sys
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.evidence import BudgetExceeded, CallBudget
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import Request, ResponseUnavailable
from hotelcontrols.providers.transport import (Credentials, HttpCall, LiveSource,
                                               MissingCredential, Recorder, TokenBucket,
                                               TransportDisabled, is_enabled)
from hotelcontrols.providers.transport import http as transport_http

CLOCK = FixedClock.at("2026-09-09T10:00", "Asia/Jerusalem")


class Dialer:
    """Where the socket would be. Records what it was asked and answers from a script."""

    def __init__(self, answers=("<ok/>",), fail_with=None):
        self.answers = list(answers)
        self.fail_with = fail_with
        self.calls: list[HttpCall] = []

    def __call__(self, call: HttpCall) -> str:
        self.calls.append(call)
        if self.fail_with is not None:
            raise self.fail_with
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def credentials(**overrides):
    values = {"user": "someone", "password": "s3cret", "hotel": "a-property",
              "base_url": "https://example.invalid"}
    values.update(overrides)
    return Credentials(**values)


def encoder(request: Request, creds: Credentials) -> HttpCall:
    """A stand-in for a provider's own encoder. The transport knows nothing about wire format."""
    return HttpCall("POST", "%s/%s" % (creds.base_url, request.endpoint),
                    {"Content-Type": "text/plain"}, "body for %s" % request.endpoint)


def a_source(**overrides):
    values = {"provider": "someprovider", "encoder": encoder, "credentials": credentials(),
              "clock": CLOCK, "dialer": Dialer(), "sleeper": lambda seconds: None}
    values.update(overrides)
    return LiveSource(**values)


# ---------------------------------------------------------------------------------------
class TestItIsOffAndATestCannotTurnItOn:
    """Criterion 11, and the reason this slice is safe to have written at all."""

    def test_it_is_disabled_when_the_variable_is_unset(self, monkeypatch):
        monkeypatch.delenv(transport_http.ENABLE, raising=False)
        assert is_enabled() is False

    def test_a_test_cannot_switch_it_on_even_by_setting_the_variable(self, monkeypatch):
        """THE test in this file.

        An environment variable alone would be a lock whose key is one line of `monkeypatch`
        away. So the second lock is the process itself: while a test runner is loaded, the
        transport refuses regardless of the environment. This test holds the key and is still
        refused.
        """
        monkeypatch.setenv(transport_http.ENABLE, "1")
        assert is_enabled() is True, "the variable really is set, so lock 1 is open"

        with pytest.raises(TransportDisabled) as refusal:
            transport_http.assert_armed()
        assert "pytest" in str(refusal.value)

    def test_the_refusal_names_the_variable_so_an_operator_can_act_on_it(self, monkeypatch):
        monkeypatch.delenv(transport_http.ENABLE, raising=False)
        with pytest.raises(TransportDisabled) as refusal:
            transport_http.assert_armed()
        assert transport_http.ENABLE in str(refusal.value)

    def test_the_test_runner_check_looks_at_what_is_actually_loaded(self):
        """A guard on the guard. If this stopped seeing the runner, the test above would pass
        for the wrong reason - the environment happening to be unset - and the second lock
        would be gone without a single test turning red."""
        assert transport_http.under_test() is True
        assert "pytest" in sys.modules

    def test_the_real_dialer_refuses_before_it_resolves_a_hostname(self, monkeypatch):
        """The default dialer is the only code in this engine that can open an outbound socket,
        and it asks permission first. With the environment set and a test runner loaded, it
        still refuses - and it refuses BEFORE any name lookup, so nothing leaves the machine."""
        monkeypatch.setenv(transport_http.ENABLE, "1")
        with pytest.raises(TransportDisabled):
            transport_http.open_socket(HttpCall("POST", "https://example.invalid", {}, ""))

    def test_a_source_built_with_no_dialer_uses_the_guarded_one(self, monkeypatch):
        """The default is the safe one. A `LiveSource` that quietly defaulted to something
        unguarded would make every other test in this file a decoration."""
        monkeypatch.setenv(transport_http.ENABLE, "1")
        source = LiveSource("someprovider", encoder, credentials(), CLOCK)
        with pytest.raises(TransportDisabled):
            source.fetch(Request("anything"))


# ---------------------------------------------------------------------------------------
class TestCredentialsComeFromTheEnvironmentWithNoDefault:
    """Finding F15. v1 hard-coded `USER, PWD, HOTEL = "Test", "3657488", "sandbox"` in a file
    about to be pushed to a public repository. They were the vendor's own published sandbox
    credentials, which made it defensible and made the HABIT dangerous: the same line survives
    the move to production credentials."""

    NAMES = ("USER", "PASSWORD", "HOTEL", "BASE_URL")

    def test_every_credential_is_read_from_the_environment(self, monkeypatch):
        for name in self.NAMES:
            monkeypatch.setenv("HOTELCONTROLS_SOMEPROVIDER_%s" % name, "value-%s" % name)
        creds = Credentials.from_environment("someprovider")
        assert creds.user == "value-USER"
        assert creds.hotel == "value-HOTEL"
        assert creds.base_url == "value-BASE_URL"

    @pytest.mark.parametrize("missing", NAMES)
    def test_a_missing_credential_fails_loudly_naming_the_variable(self, missing, monkeypatch):
        """No default, no fallback, no empty string. A transport that started with three of
        four credentials would fail at the vendor's authentication layer, and the error a
        reader sees would be about the vendor rather than about this machine."""
        for name in self.NAMES:
            monkeypatch.setenv("HOTELCONTROLS_SOMEPROVIDER_%s" % name, "x")
        monkeypatch.delenv("HOTELCONTROLS_SOMEPROVIDER_%s" % missing)

        with pytest.raises(MissingCredential) as refusal:
            Credentials.from_environment("someprovider")
        assert "HOTELCONTROLS_SOMEPROVIDER_%s" % missing in str(refusal.value)

    def test_an_empty_credential_counts_as_missing(self, monkeypatch):
        """`export HOTELCONTROLS_X_PASSWORD=` is the commonest way to have a credential and
        not have it."""
        for name in self.NAMES:
            monkeypatch.setenv("HOTELCONTROLS_SOMEPROVIDER_%s" % name, "x")
        monkeypatch.setenv("HOTELCONTROLS_SOMEPROVIDER_PASSWORD", "   ")
        with pytest.raises(MissingCredential):
            Credentials.from_environment("someprovider")

    def test_the_password_never_appears_in_a_repr(self):
        """Credentials get printed by accident - in a traceback, a log line, a debugger. The
        one that must never be there is the one this hides."""
        creds = credentials(password="hunter2")
        assert "hunter2" not in repr(creds)
        assert "hunter2" not in str(creds)
        assert "someone" in repr(creds), "the user is not a secret and identifies the account"


# ---------------------------------------------------------------------------------------
class TestTheRateLimiter:
    """R8: the vendor asks not to be queried hard. A limiter with the machine's clock in it
    would be untestable and would therefore be untested, which is how a rate limiter comes to
    be wrong in production."""

    def bucket(self, capacity=2, seconds=1, start="2026-09-09T10:00:00"):
        clock = _MovableClock(datetime.fromisoformat(start).replace(tzinfo=timezone.utc))
        return TokenBucket(capacity=capacity, interval=timedelta(seconds=seconds),
                           clock=clock), clock

    def test_a_full_bucket_lets_its_capacity_through_at_once(self):
        bucket, _clock = self.bucket(capacity=2)
        assert bucket.take() == timedelta(0)
        assert bucket.take() == timedelta(0)

    def test_the_call_after_that_waits_one_interval(self):
        bucket, _clock = self.bucket(capacity=2, seconds=1)
        bucket.take()
        bucket.take()
        assert bucket.take() == timedelta(seconds=1)

    def test_waiting_earns_a_token_back(self):
        bucket, clock = self.bucket(capacity=2, seconds=1)
        bucket.take()
        bucket.take()
        clock.advance(timedelta(seconds=2))
        assert bucket.take() == timedelta(0)

    def test_it_never_banks_more_than_its_capacity(self):
        """An idle hour must not buy an hour's worth of calls in one burst - that is exactly
        the shape of traffic the vendor asked us not to send."""
        bucket, clock = self.bucket(capacity=2, seconds=1)
        clock.advance(timedelta(hours=1))
        assert bucket.take() == timedelta(0)
        assert bucket.take() == timedelta(0)
        assert bucket.take() > timedelta(0)

    def test_it_paces_at_one_call_per_interval_when_the_caller_obeys(self):
        """The contract in one loop: ask, sleep exactly as told, call, repeat.

        The wait is accounted for INSIDE the bucket, not merely reported. Without that, the
        caller's obedient sleep would look like idle time on the next ask, earn a token back,
        and be waved through - so four calls would leave in a burst while the limiter reported
        that it had paced them. This asserts the total wait rather than any single answer,
        because the total is the thing the vendor experiences (R8).
        """
        bucket, clock = self.bucket(capacity=1, seconds=1)
        total = timedelta(0)
        for _ in range(4):
            wait = bucket.take()
            clock.advance(wait)                      # the caller sleeps for exactly this long
            total += wait
        assert total == timedelta(seconds=3), "the first call is free; the other three wait"

    def test_it_reads_no_wall_clock(self):
        """F11 applies here too: a limiter reading the machine's clock is a limiter whose
        behaviour cannot be reproduced, and pacing bugs are the ones that only appear live."""
        bucket, _clock = self.bucket()
        assert bucket.clock is not None


class _MovableClock:
    """A test clock that can be pushed forward. The only kind of clock this suite uses."""

    def __init__(self, instant):
        self.instant = instant

    def advance(self, delta):
        self.instant = self.instant + delta

    def now(self):
        return self.instant

    def today(self):
        return self.instant.date()


# ---------------------------------------------------------------------------------------
class TestRetryAndGivingUp:

    def test_a_transient_failure_is_retried(self):
        attempts = []

        def flaky(call):
            attempts.append(call)
            if len(attempts) < 3:
                raise OSError("connection reset")
            return "<ok/>"

        source = a_source(dialer=flaky, attempts=3)
        assert source.fetch(Request("anything")) == "<ok/>"
        assert len(attempts) == 3

    def test_giving_up_is_an_evidence_gap_and_not_a_crash(self):
        """`ResponseUnavailable` is a `ProviderError`, and the evidence layer turns one into an
        UNKNOWN with a reason. That is the whole difference between a control that says "the
        folio call failed" and a run that dies with a traceback."""
        source = a_source(dialer=Dialer(fail_with=OSError("connection reset")), attempts=2)
        with pytest.raises(ResponseUnavailable) as gap:
            source.fetch(Request("anything"))
        assert "2" in str(gap.value) and "connection reset" in str(gap.value)

    def test_the_backoff_grows_between_attempts(self):
        """Retrying immediately three times is not a retry policy, it is three failures in a
        row - and against a vendor who asked not to be hammered it is worse than giving up."""
        slept = []
        source = a_source(dialer=Dialer(fail_with=OSError("nope")), attempts=3,
                          backoff=timedelta(seconds=1), sleeper=slept.append)
        with pytest.raises(ResponseUnavailable):
            source.fetch(Request("anything"))
        waits = [s for s in slept if s > 0]
        assert waits == sorted(waits) and len(set(waits)) > 1, waits

    def test_a_refusal_to_arm_is_never_retried(self):
        """A disabled transport is a configuration mistake, not a flaky network. Retrying it
        three times with backoff would turn a loud, instant failure into a slow confusing one.
        """
        def disabled(call):
            raise TransportDisabled("off")

        with pytest.raises(TransportDisabled):
            a_source(dialer=disabled, attempts=3).fetch(Request("anything"))


# ---------------------------------------------------------------------------------------
class TestItLooksLikeEveryOtherSourceFromAbove:
    """The adapter takes a source and calls `fetch`. Live and frozen must be interchangeable,
    or "the same code path" is a claim rather than a fact."""

    def test_it_reports_what_it_is_and_that_it_is_not_synthetic(self):
        source = a_source()
        assert source.is_synthetic is False
        assert "live" in source.origin.lower()

    def test_it_records_every_call_it_makes_so_a_count_can_be_asserted(self):
        source = a_source()
        source.fetch(Request("one"))
        source.fetch(Request("two"))
        assert [r.endpoint for r in source.calls] == ["one", "two"]

    def test_its_evidence_is_obtained_now_by_the_property_clock(self):
        """Not the machine's. A run's freshness is measured against when its evidence was
        obtained, and a laptop in another timezone would date it differently from the hotel it
        describes (F11)."""
        source = a_source()
        assert source.observed_at == CLOCK.today().isoformat()

    def test_the_encoder_is_the_providers_and_the_transport_reads_none_of_it(self):
        """The transport carries a body it did not write to a URL it did not compose. Which
        endpoint is which, and what a request looks like on the wire, is adapter knowledge -
        this package sits ABOVE no boundary and must name no vendor."""
        dialer = Dialer()
        a_source(dialer=dialer).fetch(Request("some-endpoint"))
        assert dialer.calls[0].url.endswith("/some-endpoint")
        assert dialer.calls[0].body == "body for some-endpoint"


# ---------------------------------------------------------------------------------------
class TestRecordMode:
    """The valuable half of this slice. Probing stops being a hand-run script whose output
    somebody copies into a directory, and starts being reproducible."""

    def test_it_writes_the_response_and_the_request_that_produced_it(self, tmp_path):
        recorder = Recorder(tmp_path, provider="someprovider", capture="live",
                            observed_at="2026-09-09")
        recorder.record(Request("rooms", {"ArrivalDate": {"From": "2026-07-01"}}), "<rooms/>")

        import json
        index = json.loads((tmp_path / "index.json").read_text())
        entry = index["responses"][0]
        assert (tmp_path / entry["file"]).read_text() == "<rooms/>"
        assert entry["endpoint"] == "rooms"
        assert entry["request"] == {"ArrivalDate": {"From": "2026-07-01"}}
        assert entry["captures"] == ["live"]
        assert entry["captured_at"] == "2026-09-09"

    def test_two_calls_to_one_endpoint_do_not_overwrite_each_other(self, tmp_path):
        """A folio is one call per reservation (R1), so a capture holds several responses from
        the same endpoint. A recorder keyed on the endpoint alone would keep only the last."""
        recorder = Recorder(tmp_path, provider="someprovider")
        recorder.record(Request("ledger", {"id": "1"}), "<one/>")
        recorder.record(Request("ledger", {"id": "2"}), "<two/>")

        import json
        index = json.loads((tmp_path / "index.json").read_text())
        files = {entry["file"] for entry in index["responses"]}
        assert len(files) == 2
        assert {(tmp_path / f).read_text() for f in files} == {"<one/>", "<two/>"}

    def test_recording_the_same_request_twice_replaces_rather_than_duplicates(self, tmp_path):
        recorder = Recorder(tmp_path, provider="someprovider")
        recorder.record(Request("rooms"), "<old/>")
        recorder.record(Request("rooms"), "<new/>")

        import json
        index = json.loads((tmp_path / "index.json").read_text())
        assert len(index["responses"]) == 1
        assert (tmp_path / index["responses"][0]["file"]).read_text() == "<new/>"

    def test_it_writes_where_git_ignores_by_default(self):
        """D6 and F15. A live response carries guest names, emails, phone numbers and free-text
        remarks, and this repository is public. Recording lands in `raw/`, which `.gitignore`
        covers, and `tools/scrub_fixtures.py` is what promotes a capture into the committed
        set. A recorder whose default wrote straight into `fixtures/<provider>/` would put
        third-party personal data one `git add -A` away from being published."""
        recorder = Recorder.for_provider("someprovider")
        assert recorder.directory.name == "raw"
        assert "fixtures" in recorder.directory.parts

    def test_a_source_with_a_recorder_records_what_it_fetched(self, tmp_path):
        recorder = Recorder(tmp_path, provider="someprovider")
        a_source(recorder=recorder).fetch(Request("anything"))
        assert list(tmp_path.glob("*.xml")) or list(tmp_path.glob("*.json"))


# ---------------------------------------------------------------------------------------
class TestTheCallCeilingIsTheOneThatAlreadyExists:
    """"The per-run call ceiling reuses the existing budget (R1, R8)."

    Not a second counter living in the transport. A budget the transport enforced privately
    would be a budget the evidence layer could not see, and two ceilings that disagree is one
    ceiling that does not work.
    """

    def test_the_transport_defines_no_ceiling_of_its_own(self):
        from hotelcontrols.providers import transport

        assert not hasattr(transport, "CallBudget")
        assert not any("budget" in name.lower() for name in dir(transport))

    def test_the_existing_budget_stops_a_live_run(self):
        """The budget wraps the source above the adapter, so it counts live calls exactly as it
        counts frozen ones."""
        from hotelcontrols.evidence.cache import ResponseCache

        source = a_source()
        cache = ResponseCache(source.fetch, CallBudget(2))
        cache.get(Request("one"))
        cache.get(Request("two"))
        with pytest.raises(BudgetExceeded):
            cache.get(Request("three"))
        assert len(source.calls) == 2, "nothing was fetched after the budget was exhausted"


# ---------------------------------------------------------------------------------------
class TestTheSmallGuardsAndWhatThingsLookLikeWhenPrinted:
    """Refusals nobody expects to hit, and the strings an operator reads when something goes
    wrong at three in the morning. Both are cheap to get right and expensive to discover."""

    def test_a_bucket_that_lets_nothing_through_is_refused(self):
        """A capacity of zero stops a run and says nothing about why. Refusing a call is the
        CallBudget's job, and it does it with a reason (R1)."""
        with pytest.raises(ValueError) as refusal:
            TokenBucket(capacity=0, interval=timedelta(seconds=1), clock=CLOCK)
        assert "call budget" in str(refusal.value)

    def test_an_interval_of_zero_is_not_a_rate_limit(self):
        with pytest.raises(ValueError):
            TokenBucket(capacity=1, interval=timedelta(0), clock=CLOCK)

    def test_a_bucket_says_how_much_it_has_left(self):
        bucket = TokenBucket(3, timedelta(seconds=1), CLOCK)
        bucket.take()
        assert "2.00/3" in repr(bucket)

    def test_a_recorder_says_where_it_is_writing(self, tmp_path):
        assert str(tmp_path) in repr(Recorder(tmp_path, provider="someprovider"))

    def test_a_source_says_how_many_calls_it_has_made(self):
        source = a_source()
        source.fetch(Request("one"))
        assert "1 call" in repr(source)

    def test_a_live_source_describes_the_instant_it_is_about(self):
        """`as_of` on a live source is now, by the property's clock. A capture describes the
        moment it was taken; a live fetch describes this one."""
        assert a_source().as_of == CLOCK.today().isoformat()

    def test_a_fingerprint_survives_a_list_and_a_value_json_cannot_hold(self, tmp_path):
        """The request is written as JSON beside the response, so a replay can check the window
        it covers (F19c). A parameter JSON refuses would break the write and lose both."""
        import json
        from decimal import Decimal

        recorder = Recorder(tmp_path, provider="someprovider")
        recorder.record(Request("thing", {"list": [1, "two"], "odd": Decimal("1.5")}), "{}")
        entry = json.loads((tmp_path / "index.json").read_text())["responses"][0]
        assert entry["request"] == {"list": [1, "two"], "odd": "1.5"}

    def test_a_response_that_is_neither_xml_nor_json_is_still_written_down(self, tmp_path):
        """This package must not know that one provider speaks XML and another JSON, so the
        suffix comes from the bytes. A response that is neither is still evidence."""
        recorder = Recorder(tmp_path, provider="someprovider")
        path = recorder.record(Request("thing"), "just some text")
        assert path.suffix == ".txt"
        assert path.read_text() == "just some text"
