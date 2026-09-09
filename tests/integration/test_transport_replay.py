# -*- coding: utf-8 -*-
"""
RECORD, THEN REPLAY - the loop that makes probing reproducible.

Review finding F13's valuable half. A probe that fetches a response and leaves somebody to copy
it into a directory is a call spent on somebody else's server to learn something nobody can
check afterwards. So the transport writes each response down WITH THE REQUEST THAT PRODUCED IT,
in the shape `FrozenSource` already reads - and this file closes the loop by recording a
response and then replaying it through the ordinary frozen path.

The assertion is the strong one: a `Value` resolved through the recorded capture is IDENTICAL
to the same `Value` resolved through the shipped fixture. Not "similar", not "also known" -
identical, field by field, including the currency, the reason on every gap and the provenance.
If recording lost anything, this is where it shows.

NO SOCKET IS OPENED ANYWHERE IN THIS FILE. The dialer is a callable that hands back bytes we
already have, which is exactly what a live one would do and is the reason this can be asserted
at all (criterion 11).
"""
import json
import pathlib

import pytest

from hotelcontrols.evidence import BudgetExceeded, CallBudget, gather
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.providers.base import Request
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.providers.transport import (Credentials, LiveSource, Recorder,
                                               TransportDisabled)
from hotelcontrols.providers.transport import http as transport_http
from hotelcontrols.spec import TenantConfig, load

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "minihotel"
CLOCK = FixedClock.at("2026-07-08T09:00", "Asia/Jerusalem")
CREDENTIALS = Credentials(user="U", password="P", hotel="H", base_url="https://host.invalid")

# The three calls control 6 makes: the population, and one folio per reservation it finds. Held
# as (request, the file the shipped capture answered it with) so the fake dialer can answer
# exactly what the sandbox answered, and nothing is invented.
CAPTURED = {
    "GetReservationKey": "9_departures_2026-07.xml",
    "GetReservationBalance": {
        "007004348": "5_balance_007004348.xml",
        "007004351": "5_balance_007004351.xml",
        "007004354": "5_balance_007004354.xml",
    },
}


@pytest.fixture(scope="module")
def tenant():
    return TenantConfig.load("sandbox")


def replaying_dialer(seen):
    """A dialer that answers with the bytes the sandbox actually returned.

    It reads the request BODY to decide which captured response to hand back, which is what
    makes the recorded fixture a real fixture rather than a copy: the encoder had to compose a
    request specific enough to identify the answer.
    """
    def dial(call):
        seen.append(call)
        if "GetReservationBalance" in call.url:
            for reservation, file in CAPTURED["GetReservationBalance"].items():
                if reservation in call.body:
                    return (FIXTURES / file).read_text(encoding="utf-8")
            raise OSError("no captured folio for that reservation")
        return (FIXTURES / CAPTURED["GetReservationKey"]).read_text(encoding="utf-8")
    return dial


def recorded_capture(tmp_path, tenant, requests):
    """Fetch through a LiveSource with a recorder, and hand back the directory it wrote."""
    from hotelcontrols.providers.minihotel import live

    recorder = Recorder(tmp_path, provider="minihotel", capture="recorded",
                        observed_at="2026-09-08", as_of="2026-07-08")
    source = LiveSource("minihotel", live.encode, CREDENTIALS, CLOCK,
                        dialer=replaying_dialer([]), recorder=recorder,
                        sleeper=lambda seconds: None)
    for request in requests:
        source.fetch(request)
    return tmp_path


# ---------------------------------------------------------------------------------------
class TestARecordedResponseReplaysThroughTheFrozenPath:

    def test_the_recorded_directory_is_a_capture_the_frozen_source_can_open(
            self, tmp_path, tenant):
        recorded_capture(tmp_path, tenant, [Request("getRooms")])
        source = FrozenSource("recorded", tmp_path)
        assert source.is_synthetic is False
        assert source.as_of == "2026-07-08"
        assert source.observed_at == "2026-09-08"

    def test_every_value_is_identical_to_the_shipped_fixture(self, tmp_path, tenant):
        """The strong assertion. Field by field, through the same adapter, over the same
        records - including the reason on every gap and the provenance on every value."""
        request = Request("GetReservationKey",
                          {"DepartureDate": {"From": "2026-07-01", "To": "2026-08-09"}})
        recorded_capture(tmp_path, tenant, [request])

        shipped = MiniHotelAdapter(tenant, FrozenSource("sandbox2026", FIXTURES))
        replayed = MiniHotelAdapter(tenant, FrozenSource("recorded", tmp_path))

        one = shipped.records(shipped.fetch(request), "reservation")
        other = replayed.records(replayed.fetch(request), "reservation")
        assert len(one) == len(other) > 0

        fields = [entry["field"] for entry in load("checkout_money_owed")["required_evidence"]
                  if entry["field"].startswith("reservation.")]
        for first, second in zip(one, other):
            for name in fields:
                assert shipped.resolve(name, first) == replayed.resolve(name, second), name

    def test_the_fingerprint_beside_it_is_the_request_that_produced_it(self, tmp_path, tenant):
        """Finding F19c, and the reason a bare response is worthless. Without the question
        recorded, a later replay answers a window the capture never covered - and an empty
        population is indistinguishable on screen from "no violations found"."""
        window = {"DepartureDate": {"From": "2026-07-01", "To": "2026-08-09"}}
        recorded_capture(tmp_path, tenant, [Request("GetReservationKey", window)])

        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index["responses"][0]["request"] == window

    def test_a_replay_outside_the_recorded_window_is_refused(self, tmp_path, tenant):
        """The fingerprint doing its job on a capture this test made ten lines ago. The guard
        is not a property of the shipped fixtures; it is a property of recording the question.
        """
        from hotelcontrols.providers.base import ResponseUnavailable

        recorded_capture(tmp_path, tenant, [Request(
            "GetReservationKey", {"DepartureDate": {"From": "2026-07-01", "To": "2026-08-09"}})])

        adapter = MiniHotelAdapter(tenant, FrozenSource("recorded", tmp_path))
        with pytest.raises(ResponseUnavailable):
            adapter.fetch(Request("GetReservationKey",
                                  {"DepartureDate": {"From": "2020-01-01", "To": "2030-01-01"}}))

    def test_a_whole_control_runs_off_a_recorded_capture(self, tmp_path, tenant):
        """End to end: record the three calls control 6 makes, then run the control against
        what was recorded, and reach the same verdicts as the shipped capture."""
        from hotelcontrols.runner import run

        requests = [Request("GetReservationKey",
                            {"DepartureDate": {"From": "2026-07-01", "To": "2026-08-09"}})]
        requests += [Request("GetReservationBalance", {"ReservationNumber": number})
                     for number in CAPTURED["GetReservationBalance"]]
        recorded_capture(tmp_path, tenant, requests)

        # The recorded capture holds one departure window; ask it about the day it covers.
        clock = FixedClock.at("2026-07-08T09:00", tenant.timezone)
        shipped = run("checkout_unrefunded_credit", tenant,
                      MiniHotelAdapter(tenant, FrozenSource("sandbox2026", FIXTURES)), clock)
        replayed = run("checkout_unrefunded_credit", tenant,
                       MiniHotelAdapter(tenant, FrozenSource("recorded", tmp_path)), clock)

        assert not replayed.is_blocked, replayed.blocked
        assert [(v.record_id, v.outcome) for v in replayed.verdicts] == \
               [(v.record_id, v.outcome) for v in shipped.verdicts]


# ---------------------------------------------------------------------------------------
class TestWithTheEnvironmentUnsetEveryPathThatWouldOpenASocketRaises:
    """Criterion 11's other half, walked rather than asserted in the abstract."""

    def test_the_default_dialer_refuses(self, monkeypatch):
        monkeypatch.delenv(transport_http.ENABLE, raising=False)
        from hotelcontrols.providers.transport import HttpCall

        with pytest.raises(TransportDisabled):
            transport_http.open_socket(HttpCall("POST", "https://host.invalid", {}, ""))

    def test_a_source_with_no_injected_dialer_refuses(self, monkeypatch):
        from hotelcontrols.providers.minihotel import live

        monkeypatch.delenv(transport_http.ENABLE, raising=False)
        source = LiveSource("minihotel", live.encode, CREDENTIALS, CLOCK)
        with pytest.raises(TransportDisabled):
            source.fetch(Request("getRooms"))

    def test_a_whole_run_through_an_unarmed_transport_refuses_before_any_call(
            self, tenant, monkeypatch):
        """Not "returns UNKNOWN" - refuses. A transport nobody enabled is a mistake about this
        machine, and turning it into an evidence gap would hide it behind a hotel's data."""
        from hotelcontrols.providers.minihotel import live
        from hotelcontrols.runner import run

        monkeypatch.delenv(transport_http.ENABLE, raising=False)
        adapter = MiniHotelAdapter(
            tenant, LiveSource("minihotel", live.encode, CREDENTIALS, CLOCK))
        with pytest.raises(TransportDisabled):
            run("checkout_money_owed", tenant, adapter, CLOCK)

    def test_exactly_one_file_in_the_engine_can_reach_the_network_at_all(self):
        """The strongest form of the claim, and the one that survives a refactor.

        Not "no test happens to dial out" but "there is one file with an outbound client in
        it, and it refuses". `urllib.parse` and `http.server` are not on this list on purpose:
        splitting a URL and LISTENING on a port are not the capability R8 is about.
        """
        import ast

        engine = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"
        forbidden = {"urllib.request", "http.client", "socket", "ssl", "ftplib", "telnetlib"}
        offenders = set()
        for path in sorted(engine.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                if any(name in forbidden or name.split(".")[0] in forbidden
                       for name in names):
                    offenders.add(path.relative_to(engine).as_posix())
        assert sorted(offenders) == ["providers/transport/http.py"], offenders


# ---------------------------------------------------------------------------------------
def test_the_call_ceiling_over_a_live_source_is_the_run_s_own_budget(tmp_path, tenant):
    """R1 and R8 against a live-shaped source. The budget wraps the source above the adapter,
    so it counts live calls exactly as it counts frozen ones - and it RAISES rather than
    truncating, because a truncated population answers a different question from the one the
    control asked."""
    from hotelcontrols.providers.minihotel import live

    seen = []
    source = LiveSource("minihotel", live.encode, CREDENTIALS, CLOCK,
                        dialer=replaying_dialer(seen), sleeper=lambda seconds: None)
    adapter = MiniHotelAdapter(tenant, source)

    with pytest.raises(BudgetExceeded):
        gather(load("checkout_money_owed"), adapter, tenant, CLOCK, CallBudget(2))

    assert len(source.calls) == 2, "nothing was fetched after the budget was exhausted"
    # And the honest footnote: the budget counts LOGICAL calls, and one logical call may cost
    # up to `attempts` requests when the network is flaky. That amplification is bounded and
    # stated rather than hidden - what the vendor experiences moment to moment is the RATE,
    # which is what the token bucket is for (R8), and the worst-case total is this product.
    assert len(seen) <= 2 * source.attempts, seen


def test_a_provider_nobody_has_ever_called_has_no_live_request_form():
    """DemoPMS is fictional. It can be replayed and it cannot be probed, and that is a real
    difference rather than a gap to fill in: inventing a wire format for a PMS that does not
    exist would make the transport look more finished than it is."""
    encoders = {package.name: package.encoder for package in providers.all_providers()}
    assert sum(1 for e in encoders.values() if e is not None) == 1, encoders
