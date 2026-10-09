# -*- coding: utf-8 -*-
"""
Slice 20's exit tests, over a FULL RUN of every control x property x capture.

    "someone running the service can see what ran, for whom, how long it took and what it
     cost, without the log ever holding a guest's details or a password."

The app here is the real one, wired with a recording notifier (so dispatch happens and is
logged) and a capturing logger (so every line the formatter would write is inspected). Fake
credentials for every provider, and a fake SMTP password, are set in the environment first:
the test proves they never reach a line, rather than trusting that nothing reads them.
"""
import json
import logging
from datetime import datetime

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.ops import JsonLines, OpsLog
from hotelcontrols.providers.registry import names as provider_names
from hotelcontrols.spec import available, available_tenants, load
from hotelcontrols.web import App
from tests import guest_details
from tools.notifiers import RecordingNotifier

NOW = "2026-10-09T09:30:00+03:00"
FAKE = {"USER": "ops-test-user-7f3a", "PASSWORD": "ops-test-password-9c2e",
        "HOTEL": "ops-test-hotel-41d0", "BASE_URL": "https://ops-test-host-b6e1.example.test"}
SMTP_PASSWORD = "ops-test-smtp-password-2a8f"


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.setFormatter(JsonLines())

    def emit(self, record):
        self.lines.append(self.format(record))


@pytest.fixture(scope="module")
def full_run():
    """Every control x property x capture through one wired app, every line captured."""
    patch = pytest.MonkeyPatch()
    for provider in provider_names():
        for suffix, value in FAKE.items():
            patch.setenv("HOTELCONTROLS_%s_%s" % (provider.upper(), suffix), value)
    patch.setenv("HOTELCONTROLS_SMTP_PASSWORD", SMTP_PASSWORD)

    logger = logging.getLogger("test.ops.full_run")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    capture = Capture()
    logger.addHandler(capture)
    clock = FixedClock(datetime.fromisoformat(NOW))
    audiences = {load(c)["action"]["audience"] for c in available()}
    app = App(clock=clock, ops=OpsLog(clock=clock, logger=logger),
              notifier=RecordingNotifier({a: ("%s@example.test" % a,) for a in audiences}))
    try:
        for control_id in available():
            for property_id in available_tenants():
                for capture_label in app.captures_for(property_id):
                    response = app.handle("/api/run/%s?property=%s&evidence=%s"
                                          % (control_id, property_id, capture_label))
                    assert response.status == 200
        for property_id in available_tenants():
            app.handle("/queue?property=%s" % property_id)
        yield app, capture.lines
    finally:
        logger.removeHandler(capture)
        patch.undo()


def records(lines, event=None):
    parsed = [json.loads(line) for line in lines]
    return [r for r in parsed if event is None or r["event"] == event]


# ---------------------------------------------------------------------------------------
class TestOneRunCanBeTracedFromRequestToDispatch:
    """Exit test 1."""

    def test_the_real_fails_run_id_appears_on_its_request_its_run_and_its_dispatch(
            self, full_run):
        app, lines = full_run
        (sent,) = [r for r in records(lines, "dispatch")
                   if r["outcome"] == "sent" and r["tenant_id"] == "sandbox"]
        run_id = sent["run_id"]
        traced = [r for r in records(lines) if r["run_id"] == run_id]
        assert [r["event"] for r in traced] == ["run", "dispatch", "request"]
        request, run, dispatch = traced[2], traced[0], traced[1]
        assert request["path"] == "/api/run/checkout_unrefunded_credit"
        assert request["status"] == 200
        for record in traced:
            assert (record["tenant_id"], record["control_id"], record["policy_version"],
                    record["provider"]) == ("sandbox", "checkout_unrefunded_credit", 2,
                                            run["provider"])
        assert dispatch["audience"] == "finance"
        assert app.store.load(run_id, tenant_id="sandbox") is not None

    def test_every_run_says_what_it_cost_and_whether_it_concluded(self, full_run):
        """What ran, for whom, what it cost: calls, counts, coverage and a duration."""
        _app, lines = full_run
        runs = records(lines, "run")
        cells = len(available()) * sum(1 for _ in available_tenants()) * 2
        assert len(runs) == cells
        for run in runs:
            assert run["run_id"] and run["control_id"] and run["tenant_id"]
            assert isinstance(run["calls"], int) and isinstance(run["duration_ms"], int)
            assert set(run["coverage"]) == {"evaluated", "total", "concluded"}
            # The same rule as a payload: a blocked run has no counts (F5).
            assert ("counts" in run) is (not run["blocked"])

    def test_every_request_is_one_record_and_none_carries_a_query_string(self, full_run):
        _app, lines = full_run
        requests = records(lines, "request")
        assert len(requests) == len(records(lines, "run")) + 2      # + the two queue pages
        assert not [r for r in requests if "?" in r["path"]]

    def test_every_timestamp_is_the_injected_clocks(self, full_run):
        """Every line, not a sample: the LogRecord's own wall-clock read never reaches one."""
        _app, lines = full_run
        assert {r["at"] for r in records(lines)} == {NOW}


# ---------------------------------------------------------------------------------------
class TestNoRecordHoldsACredentialOrAGuest:
    """Exit test 2 and criterion V7, over EVERY line that full run emitted - not by review."""

    def test_no_line_contains_a_credential(self, full_run):
        _app, lines = full_run
        secrets = list(FAKE.values()) + [SMTP_PASSWORD]
        found = [(secret, line) for line in lines for secret in secrets if secret in line]
        assert not found, found[:3]

    def test_no_line_contains_a_guest_name_email_phone_or_card_token(self, full_run):
        _app, lines = full_run
        details = guest_details.collect()
        leaked = [(guest_details.leaks(line, details), line) for line in lines
                  if guest_details.leaks(line, details)]
        assert not leaked, leaked[:3]

    def test_no_line_carries_a_staff_address(self, full_run):
        """Slice 19's routes are personal data too. A dispatch line names the audience."""
        _app, lines = full_run
        assert not [line for line in lines if "@example.test" in line]

    def test_there_were_lines_to_check(self, full_run):
        _app, lines = full_run
        assert len(lines) > 90


# ---------------------------------------------------------------------------------------
class TestTheDemoKeepsItsShape:

    def test_an_app_with_no_ops_log_handed_in_still_answers_and_writes_nothing_by_default(self):
        """The default logger has no handler until the server attaches one, so an App built
        in a test or a notebook prints nothing it was not asked to."""
        response = App().handle("/api/run/checkout_money_owed?property=sandbox")
        assert response.status == 200

    def test_the_server_attaches_the_log_to_stderr_by_default_and_can_turn_it_off(
            self, tmp_path):
        from hotelcontrols.web import server

        assert server.parser().parse_args([]).log == "-"
        assert server.configure_log("off") is None
        to_stderr = server.configure_log("-")
        try:
            import sys
            assert to_stderr.stream is sys.stderr
        finally:
            logging.getLogger("hotelcontrols.ops").removeHandler(to_stderr)
        path = tmp_path / "ops.jsonl"
        handler = server.configure_log(str(path))
        try:
            app = App(clock=FixedClock(datetime.fromisoformat(NOW)))
            app.handle("/api/controls")
            handler.flush()
        finally:
            logging.getLogger("hotelcontrols.ops").removeHandler(handler)
            handler.close()
        (line,) = path.read_text(encoding="utf-8").splitlines()
        assert json.loads(line)["path"] == "/api/controls"
