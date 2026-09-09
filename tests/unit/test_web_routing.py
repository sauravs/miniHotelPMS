# -*- coding: utf-8 -*-
"""
L7 - routing and rendering, without a socket.

`handle(path) -> (status, content_type, body)` is a pure function of the path. That signature is
the whole design of this layer: a page that can be produced from a string can be tested from a
string, and a demo whose correctness depends on a listening port is a demo nobody can assert
anything about.

WHAT THIS LAYER IS FOR, AND WHAT IT IS NOT
-------------------------------------------
It is thin on purpose. Its single job is to prove a verdict traces to the fields that produced
it - criterion 3 - and every test in this file is about one of four claims:

    criterion 2   UNKNOWN is distinguishable from FAIL by hue, border AND wording. The wording
                  half is asserted on the TEXT ALONE, with the markup stripped, so the
                  distinction survives a monochrome screen and a reader who sees no colour.
    criterion 3   every verdict block carries each field, its value WITH ITS UNIT, and the call
                  it came from.
    criterion 8   a run that concluded nothing shows no count tiles. Four reassuring zeroes are
                  what v1 shipped, and finding F5 is what they cost.
    criterion 10  readiness per control per provider.

And one that is not a criterion but is the reason the others can be trusted: every value that
came from a provider is HTML-escaped. Guest names are in this data.
"""
import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from hotelcontrols.kernel import (NOT_APPLICABLE, EvidenceLine, Money, Outcome, Value, Verdict)
from hotelcontrols.runner import Run
from hotelcontrols.web import App, Response, handle, render

STYLESHEET = render.STYLESHEET


def text_of(html: str) -> str:
    """The page as a reader with no colour, no borders and no CSS would receive it.

    This is how criterion 2's "and wording" half is checked: strip every tag and every class
    name, and the distinction between "we found a violation" and "we could not tell" must still
    be there in words.
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def a_verdict(outcome, reason="because", evidence=None, record_id="007003199"):
    evidence = evidence or [EvidenceLine("folio.balance_due",
                                         Value.known(Money.parse("3262.50", "ILS"),
                                                     source="pms:x/y"))]
    return Verdict(outcome, reason, evidence, control_id="checkout_money_owed",
                   record_id=record_id)


def a_run(verdicts=(), blocked=None):
    return Run(control_id="checkout_money_owed", control_name="Checkout With Money Owed",
               natural_language="A reservation cannot be closed while the guest still owes "
                                "money.",
               tenant_id="sandbox", provider="minihotel", evidence_label="sandbox2026",
               evidence_is_synthetic=False, as_of="2026-07-08",
               created_at=datetime(2026, 7, 8, tzinfo=timezone.utc), calls=4,
               verdicts=tuple(verdicts), blocked=blocked, maximum_age="1h")


# ---------------------------------------------------------------------------------------
class TestHandleIsAPureFunctionOfThePath:

    def test_the_index_answers(self):
        status, content_type, body = handle("/")
        assert status == 200
        assert content_type.startswith("text/html")
        assert body

    def test_the_same_path_twice_gives_the_same_answer(self):
        """Routing depends on the path and nothing else - not on what was requested before it,
        and not on a socket having been opened."""
        assert handle("/")[:2] == handle("/")[:2]

    def test_a_response_unpacks_as_the_triple_the_architecture_declares(self):
        response = handle("/")
        assert isinstance(response, Response)
        status, content_type, body = response
        assert (status, content_type, body) == (response.status, response.content_type,
                                                response.body)

    def test_a_path_nobody_routed_is_a_page_and_not_an_exception(self):
        status, content_type, body = handle("/nowhere")
        assert status == 404
        assert content_type.startswith("text/html")
        assert "/nowhere" in body or "not" in body.lower()

    def test_an_unrouted_api_path_answers_in_json_rather_than_html(self):
        """A caller asking for JSON gets JSON even when the answer is no. An API that returns
        an HTML error page is an API that breaks its client's parser at the worst moment."""
        status, content_type, body = handle("/api/nowhere")
        assert status == 404
        assert content_type.startswith("application/json")
        assert "error" in json.loads(body)

    def test_a_control_id_that_tries_to_escape_the_spec_directory_is_refused(self):
        """The id arrives from a URL, and `../../etc/passwd` is a perfectly good control id as
        far as string formatting is concerned. The spec loader already refuses it; this asserts
        the refusal reaches the reader as a page rather than as a stack trace."""
        status, _content_type, body = handle("/run/..%2F..%2Fetc%2Fpasswd")
        assert status == 404
        assert "passwd" not in body or "no control" in body.lower()

    def test_an_unexpected_error_renders_as_a_page_never_a_dropped_connection(self):
        """`handle` is the last line before a socket. Whatever goes wrong below it, a reader
        gets a page saying so - a browser showing a connection reset tells nobody anything."""
        class Broken(App):
            def route(self, path, query):
                raise RuntimeError("the floor gave way")

        status, content_type, body = Broken().handle("/")
        assert status == 500
        assert content_type.startswith("text/html")
        assert "the floor gave way" in body

    def test_an_unexpected_error_on_an_api_path_is_still_json(self):
        class Broken(App):
            def route(self, path, query):
                raise RuntimeError("the floor gave way")

        status, content_type, body = Broken().handle("/api/run/checkout_money_owed")
        assert status == 500
        assert content_type.startswith("application/json")
        assert "the floor gave way" in json.loads(body)["error"]

    def test_the_stylesheet_is_served_from_the_engine_and_not_from_the_internet(self):
        """Criterion 11 on the page as well as in the code. A stylesheet fetched from a CDN
        would make the demo need a network to look right."""
        status, content_type, body = handle("/style.css")
        assert status == 200
        assert content_type.startswith("text/css")
        assert ".verdict" in body


# ---------------------------------------------------------------------------------------
class TestCriterion2UnknownIsNotAFailure:
    """"UNKNOWN is distinguishable from FAIL by hue, border **and** wording."

    Three signals because one is not enough: colour alone fails a monochrome screen and a
    colour-blind reader, and this distinction is the product's central commitment. A reader who
    cannot tell "we found a violation" from "we could not tell" has been told nothing useful.
    """

    def test_the_wording_alone_distinguishes_them_with_the_markup_stripped(self):
        failure = text_of(render.verdict_block(a_verdict(Outcome.FAIL)))
        unknown = text_of(render.verdict_block(a_verdict(Outcome.UNKNOWN)))

        assert "VIOLATION" in failure and "VIOLATION" not in unknown
        assert "NO ANSWER" in unknown and "NO ANSWER" not in failure
        assert "not a pass and not a failure" in unknown.lower()

    def test_excluded_is_worded_as_neither_checked_nor_passed(self):
        """EXCLUDED is separate from PASS on purpose. A run over a hundred records where ninety
        were out of scope must not read as "90 passed"."""
        excluded = text_of(render.verdict_block(a_verdict(Outcome.EXCLUDED)))
        assert "NOT APPLICABLE" in excluded
        assert "has not been checked" in excluded.lower()

    def test_the_border_style_differs_between_them(self):
        """The second signal. Solid against dashed survives a screenshot in greyscale."""
        styles = {name: _border_style(STYLESHEET, name) for name in ("FAIL", "UNKNOWN")}
        assert styles["FAIL"] and styles["UNKNOWN"]
        assert styles["FAIL"] != styles["UNKNOWN"], styles

    def test_the_hue_differs_between_them(self):
        hues = {name: _border_colour(STYLESHEET, name) for name in ("FAIL", "UNKNOWN")}
        assert hues["FAIL"] and hues["UNKNOWN"]
        assert hues["FAIL"] != hues["UNKNOWN"], hues

    def test_all_four_outcomes_are_styled_so_none_falls_back_to_looking_like_another(self):
        for outcome in Outcome:
            assert _border_style(STYLESHEET, outcome.value), outcome


def _rule(stylesheet: str, outcome: str) -> str:
    match = re.search(r"\.verdict\.%s\s*\{([^}]*)\}" % outcome, stylesheet)
    return match.group(1) if match else ""


def _border_style(stylesheet: str, outcome: str) -> str:
    match = re.search(r"border-left:\s*[\d.]+\w*\s+(\w+)", _rule(stylesheet, outcome))
    return match.group(1) if match else ""


def _border_colour(stylesheet: str, outcome: str) -> str:
    match = re.search(r"border-left:\s*[\d.]+\w*\s+\w+\s+(#[0-9a-fA-F]+)",
                      _rule(stylesheet, outcome))
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------------------
class TestCriterion3AVerdictTracesToItsFields:

    def test_every_evidence_line_carries_field_value_and_the_call_it_came_from(self):
        block = render.verdict_block(a_verdict(Outcome.FAIL))
        assert "folio.balance_due" in block
        assert "3262.50 ILS" in block, "a number without its currency is a criterion-3 failure"
        assert "pms:x/y" in block

    def test_an_unknown_value_shows_its_reason_rather_than_a_blank(self):
        """The reason is the entire commercial value of an UNKNOWN: what to go and fix."""
        line = EvidenceLine("folio.balance_due",
                            Value.unknown("the folio call failed", risk="R1", source="pms:x/y"))
        block = render.verdict_block(a_verdict(Outcome.UNKNOWN, evidence=[line]))
        assert "the folio call failed" in block
        assert "R1" in block

    def test_not_applicable_does_not_render_as_an_empty_cell(self):
        """R7. "there is no channel confirmation because there was no channel" is a fact, and
        an empty cell says the opposite."""
        line = EvidenceLine("reservation.channel_confirmation_id",
                            Value.known(NOT_APPLICABLE, source="pms:x/y"))
        block = render.verdict_block(a_verdict(Outcome.EXCLUDED, evidence=[line]))
        assert "not applicable" in block

    def test_a_verdict_names_the_record_it_is_about(self):
        assert "007003199" in render.verdict_block(a_verdict(Outcome.PASS))


class TestEverythingFromAProviderIsEscaped:
    """Guest names, remarks and free text are in this data, and a page that renders them raw is
    a page that executes whatever a booking channel put in a name field."""

    NASTY = '<script>alert("x")</script>'

    def test_a_value_is_escaped(self):
        line = EvidenceLine("reservation.guest.surname",
                            Value.known(self.NASTY, source="pms:x/y"))
        block = render.verdict_block(a_verdict(Outcome.FAIL, evidence=[line]))
        assert "<script>" not in block
        assert "&lt;script&gt;" in block

    def test_a_reason_is_escaped(self):
        block = render.verdict_block(a_verdict(Outcome.FAIL, reason=self.NASTY))
        assert "<script>" not in block

    def test_a_record_id_is_escaped(self):
        block = render.verdict_block(a_verdict(Outcome.FAIL, record_id=self.NASTY))
        assert "<script>" not in block

    def test_a_provenance_string_is_escaped(self):
        line = EvidenceLine("reservation.status",
                            Value.known("ok", source="pms:%s" % self.NASTY))
        block = render.verdict_block(a_verdict(Outcome.FAIL, evidence=[line]))
        assert "<script>" not in block

    def test_the_control_sentence_on_the_page_is_escaped(self):
        """The sentence is shown beside the verdict so the chain "rule as written -> answer
        -> evidence" is visible, and since slice 9 it can be a sentence somebody typed."""
        run = replace(a_run([a_verdict(Outcome.PASS)]), natural_language=self.NASTY)
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert "<script>" not in page
        assert "&lt;script&gt;" in page

    def test_a_blocked_reason_is_escaped(self):
        page = render.run_page(a_run(blocked=self.NASTY), plan=None, readiness=(), links={})
        assert "<script>" not in page
        assert "&lt;script&gt;" in page


# ---------------------------------------------------------------------------------------
class TestCriterion8ARunThatConcludedNothingSaysSo:

    def test_a_run_that_only_excluded_shows_no_count_tiles(self):
        """Finding F5, on screen. Four tiles with a zero under FAIL is exactly how v1 reported
        a control that never applied to anything, and it is indistinguishable from success."""
        run = a_run([a_verdict(Outcome.EXCLUDED, record_id="a"),
                     a_verdict(Outcome.EXCLUDED, record_id="b")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert "reached no conclusion" in text_of(page).lower()
        assert 'class="tiles"' not in page

    def test_a_run_that_concluded_something_does_show_tiles(self):
        run = a_run([a_verdict(Outcome.PASS, record_id="a"),
                     a_verdict(Outcome.FAIL, record_id="b")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert 'class="tiles"' in page

    def test_a_blocked_run_shows_no_tiles_and_says_why(self):
        page = render.run_page(a_run(blocked="this capture never held that window"),
                               plan=None, readiness=(), links={})
        assert 'class="tiles"' not in page
        assert "this capture never held that window" in page

    def test_an_empty_population_says_there_was_nothing_to_check(self):
        page = render.run_page(a_run([]), plan=None, readiness=(), links={})
        assert "nothing to check" in text_of(page).lower()
        assert 'class="tiles"' not in page


# ---------------------------------------------------------------------------------------
class TestTheJsonApiIsWellFormedInEveryState:
    """"Well-formed JSON for an empty population, a blocked run, and a run that concluded
    nothing." Each of those is a state where a naive serialiser reaches for a key that is not
    there."""

    def test_a_run_with_verdicts_serialises_with_its_evidence(self):
        payload = json.loads(render.run_json(a_run([a_verdict(Outcome.FAIL)]),
                                             plan=None, readiness=()))
        line = payload["verdicts"][0]["evidence"][0]
        assert line["field"] == "folio.balance_due"
        assert line["value"] == "3262.50 ILS"
        assert line["known"] is True
        assert line["source"] == "pms:x/y"

    def test_an_empty_population_serialises(self):
        payload = json.loads(render.run_json(a_run([]), plan=None, readiness=()))
        assert payload["verdicts"] == []
        assert payload["coverage"]["evaluated"] == 0
        assert payload["coverage"]["concluded"] is False

    def test_a_blocked_run_serialises_and_carries_no_counts(self):
        """A blocked run must not present counts at all. Zeroes in a JSON payload get charted
        by somebody, and a chart of a run that never happened is a chart of nothing."""
        payload = json.loads(render.run_json(a_run(blocked="no such window"),
                                             plan=None, readiness=()))
        assert payload["blocked"] == "no such window"
        assert payload.get("counts") in (None, {})

    def test_a_run_that_concluded_nothing_says_so_in_json_too(self):
        payload = json.loads(render.run_json(a_run([a_verdict(Outcome.EXCLUDED)]),
                                             plan=None, readiness=()))
        assert payload["coverage"]["concluded"] is False
        assert payload["coverage"]["headline"]

    def test_an_unknown_value_serialises_its_reason_and_risk_rather_than_null(self):
        line = EvidenceLine("folio.balance_due",
                            Value.unknown("no folio was captured", risk="R1", source="pms:x/y"))
        payload = json.loads(render.run_json(a_run([a_verdict(Outcome.UNKNOWN,
                                                              evidence=[line])]),
                                             plan=None, readiness=()))
        cell = payload["verdicts"][0]["evidence"][0]
        assert cell["known"] is False
        assert cell["reason"] == "no folio was captured"
        assert cell["risk"] == "R1"

    def test_money_keeps_its_currency_through_json(self):
        """R9 survives serialisation or it does not survive at all. A JSON number would be a
        bare amount, and a bare amount in this system is a reservation in USD meeting its own
        folio in ILS."""
        payload = json.loads(render.run_json(a_run([a_verdict(Outcome.FAIL)]),
                                             plan=None, readiness=()))
        assert payload["verdicts"][0]["evidence"][0]["value"].endswith(" ILS")


def test_a_decimal_does_not_break_the_serialiser():
    """`json.dumps` refuses a Decimal, and money is Decimal everywhere in this engine (F10)."""
    line = EvidenceLine("stay.amount", Value.known(Decimal("12.5"), unit="ILS"))
    payload = json.loads(render.run_json(a_run([a_verdict(Outcome.FAIL, evidence=[line])]),
                                         plan=None, readiness=()))
    assert payload["verdicts"][0]["evidence"][0]["value"] == "12.5 ILS"


# ---------------------------------------------------------------------------------------
class TestTheServerDecidesNothing:
    """`server.py` is the only file in the engine that knows a socket exists, and the ratio is
    the point: everything worth asserting is a pure function of a path, so the whole demo is
    tested without binding a port. These are the few lines that are not.

    No test here opens a socket. A suite that needs a listener is a suite that fails on a busy
    machine for reasons that have nothing to do with the code.
    """

    def test_a_response_is_bytes_with_its_length_and_type(self):
        from hotelcontrols.web import server

        status, headers, payload = server.respond(App(), "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert int(headers["Content-Length"]) == len(payload)
        assert payload.decode("utf-8").startswith("<meta charset")

    def test_a_page_with_non_ascii_evidence_is_length_counted_in_bytes(self):
        """The captures hold Hebrew free text and pseudonymised names with accents. A
        Content-Length counted in characters truncates the page in the reader's browser, which
        looks like a corrupted verdict rather than a header bug."""
        from hotelcontrols.web import server

        class Accented(App):
            def route(self, segments, query):
                return Response(200, "text/html; charset=utf-8", "מדיניות VIP")

        _status, headers, payload = server.respond(Accented(), "/")
        assert int(headers["Content-Length"]) == len(payload) > len("מדיניות VIP")

    def test_the_policy_header_forbids_everything_the_page_does_not_use(self):
        from hotelcontrols.web import server

        _status, headers, _payload = server.respond(App(), "/")
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "script" not in headers["Content-Security-Policy"]

    def test_a_refusal_still_carries_a_body_and_its_length(self):
        from hotelcontrols.web import server

        status, headers, payload = server.respond(App(), "/nowhere")
        assert status == 404
        assert int(headers["Content-Length"]) == len(payload) > 0

    def test_the_server_binds_the_loopback_interface_by_default(self):
        """This demo has no authentication - that is scoped out in `prd.md` §6 - and it renders
        pseudonymised guest data. A default of 0.0.0.0 would publish it to the network the
        machine happens to be on."""
        from hotelcontrols.web import server

        assert server.HOST == "127.0.0.1"

    def test_the_handler_writes_the_status_the_headers_and_the_body(self):
        """`do_GET` with the socket replaced by a list. Six lines that decide nothing, and this
        asserts they decide nothing: whatever `respond` returned is what goes out."""
        import io

        from hotelcontrols.web import server

        handler = server.Handler.__new__(server.Handler)
        handler.path = "/"
        written, headers = [], []
        handler.send_response = lambda status: written.append(status)
        handler.send_header = lambda name, value: headers.append((name, value))
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()

        handler.do_GET()
        assert written == [200]
        assert dict(headers)["Content-Type"].startswith("text/html")
        assert handler.wfile.getvalue().startswith(b"<meta charset")

    def test_the_access_log_never_records_a_query_string(self, capsys):
        """A log line is the easiest place for data to leak out of a system that was careful
        everywhere else. `?property=` and `?evidence=` are harmless today; the habit is not."""
        from hotelcontrols.web import server

        handler = server.Handler.__new__(server.Handler)
        handler.command = "GET"
        handler.path = "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026"
        handler.log_message("%s", "ignored")
        assert capsys.readouterr().out.strip() == "GET /run/checkout_money_owed"

    def test_the_server_is_serial_because_the_store_is_a_single_thread_connection(self):
        """Found by running the demo rather than by reading it.

        With `ThreadingHTTPServer` every request is handled on a new thread, and the run store
        is one `sqlite3` connection opened when the app was built - so the first page that
        saved a run answered `500 ProgrammingError: SQLite objects created in a thread can only
        be used in that same thread`. The whole suite was green: nothing in it had ever crossed
        a thread, because `handle(path)` is a pure function of a string and that is exactly
        what makes it so pleasant to test.

        A serial server is the right answer for a single-operator local demo, and it keeps the
        constraint visible instead of hiding it behind `check_same_thread=False`, which would
        make the failure a data race instead of an exception. If this ever becomes threaded,
        the store has to become thread-safe first - and this test is where that argument lands.
        """
        from http.server import HTTPServer

        from hotelcontrols.web import server

        assert server.SERVER is HTTPServer

    def test_an_app_built_inside_a_thread_serves_from_that_thread(self):
        """The constraint is the SHARED connection, not the engine: nothing in the layers below
        cares which thread it runs on."""
        import threading

        answers = []
        thread = threading.Thread(
            target=lambda: answers.append(
                App().handle("/run/checkout_money_owed"
                             "?property=sandbox&evidence=sandbox2026")))
        thread.start()
        thread.join()
        assert answers[0].status == 200, answers[0].body[:300]
