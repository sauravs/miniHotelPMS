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
        # CHANGED DELIBERATELY IN SLICE 14. This asserted the body STARTED with
        # `<meta charset`, which it did because the page had no `<!doctype html>` and no
        # `<html>` element at all - so every browser rendered the demo in quirks mode and
        # every screen reader had to guess its language. What the assertion was protecting is
        # that the charset is declared before a browser can start guessing the encoding, and
        # that is still true: it is the first thing inside `<head>`. See
        # `TestThePageIsAWellFormedDocument`, which pins both halves.
        assert payload.decode("utf-8").startswith('<!doctype html><html lang="en"><head>'
                                                  '<meta charset="utf-8">')

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
        # Changed deliberately in slice 14, for the same reason and with the same guarantee as
        # the assertion in `test_a_response_is_bytes_with_its_length_and_type` above: whatever
        # `respond` returned is what goes out, and what it returns is now a whole document.
        assert handler.wfile.getvalue().startswith(b"<!doctype html>")

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


# ---------------------------------------------------------------------------------------
class TestThePageIsAWellFormedDocument:
    """Slice 14. The scaffold, which until now started at `<meta charset>`.

    Not a cosmetic point. With no `<!doctype html>` a browser renders in quirks mode, and with
    no `lang` a screen reader has nothing to pick a voice from - so the page that exists to
    make a verdict believable was being read in the wrong accent and laid out under 1990s box
    rules. Both are one line to fix and neither costs a byte of JavaScript.

    `tests/unit/test_web_routing.py` used to assert the body STARTED with `<meta charset`, in
    two places. Both are updated deliberately in the same commit: the charset declaration is
    still the first thing inside `<head>`, which is the part that mattered.
    """

    def test_it_declares_a_doctype_so_a_browser_is_not_in_quirks_mode(self):
        assert handle("/").body.lower().startswith("<!doctype html>")

    def test_it_declares_its_language_so_assistive_technology_can_read_it(self):
        assert '<html lang="en">' in handle("/").body

    def test_the_charset_is_still_the_first_thing_in_the_head(self):
        """Still first, and it has to be: a charset declared after the first 1024 bytes is a
        charset a browser has already guessed past, and these captures hold Hebrew free text."""
        head = re.search(r"<head>(.*?)</head>", handle("/").body, re.S).group(1)
        assert head.lstrip().startswith('<meta charset="utf-8">')

    def test_the_content_lives_in_a_body_element(self):
        body = handle("/").body
        assert "<body>" in body and body.rstrip().endswith("</html>")

    def test_every_page_is_the_same_document_shape(self):
        """The shell is one function, so this holds for a refusal as much as for a run."""
        for path in ("/", "/nowhere", "/history/checkout_money_owed",
                     "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026"):
            markup = handle(path).body
            assert markup.lower().startswith("<!doctype html>"), path
            assert '<html lang="en">' in markup, path
            assert "<body>" in markup and "</body>" in markup, path

    def test_there_is_still_exactly_one_stylesheet_and_no_other_resource(self):
        """Criterion 11 for the page: `default-src 'none'` forbids a webfont as surely as it
        forbids a CDN, so a scaffold change must not smuggle one in."""
        markup = handle("/").body
        assert markup.count("<link") == 1
        assert markup.count('href="/style.css"') == 1
        assert "http://" not in markup and "https://" not in markup


# ---------------------------------------------------------------------------------------
class TestThePageExplainsItself:
    """Slice 14. A first-time reader must be able to learn what a component MEANS on screen.

    The vocabulary this product rests on is not guessable: EXCLUDED is not PASS, UNKNOWN is not
    FAIL, "4 of 5 fields" is a readiness ratio, `as_of` defaults to the instant the EVIDENCE
    describes rather than to today. A page that assumes the reader knows all four has told them
    nothing, which is criterion 2's failure mode wearing a different hat.

    THE MECHANISM IS `<details><summary>`, AND THAT IS A REQUIREMENT RATHER THAN A PREFERENCE.
    `title="..."` would put the explanation INSIDE a tag, where `text_of` strips it and where a
    touch user can never reach it. Visible, keyboard-reachable, strip-surviving help, or none.
    """

    PAGES = ("/", "/history/checkout_money_owed",
             "/run/checkout_money_owed?property=sandbox&evidence=sandbox2026",
             "/run/ooo_room_protection?property=sandbox&evidence=sandbox2026")

    def test_no_help_is_hidden_in_a_title_attribute(self):
        """The constraint, asserted rather than trusted. A `title=` tooltip does not survive
        `text_of`, does not exist on a touch screen, and is read inconsistently by screen
        readers - so it is the one tooltip mechanism this project may not use."""
        for path in self.PAGES:
            assert not re.search(r"\stitle=", handle(path).body), path

    def test_every_page_carries_an_explanation_bar(self):
        for path in self.PAGES:
            markup = handle(path).body
            assert 'class="explainer"' in markup, path
            assert "<summary>" in markup, path

    def test_the_explanation_survives_having_every_tag_stripped(self):
        """Help that only exists while CSS and JavaScript are working is help for the demo,
        not for the reader."""
        for path in self.PAGES:
            assert "how to read this page" in text_of(handle(path).body).lower(), path

    def test_the_run_page_explains_all_four_outcomes_in_one_place(self):
        """The four words on screen are PASS, VIOLATION, NO ANSWER and NOT APPLICABLE, and the
        two that a reader will get wrong are the last two. So the page says, in prose, that one
        is not a failure and the other is not a pass."""
        text = text_of(handle("/run/inactive_room_future_stay"
                              "?property=sandbox&evidence=sandbox2026").body).lower()
        assert "what the four answers mean" in text
        for badge in ("pass", "violation", "no answer", "not applicable"):
            assert badge in text, badge
        assert "not a pass and not a failure" in text
        assert "has not been checked" in text

    def test_the_run_page_explains_the_date_it_asked_about(self):
        """`as_of` defaults to the instant the EVIDENCE describes, not to today - which is the
        single most surprising thing about this demo and was nowhere on the page."""
        text = text_of(handle("/run/checkout_money_owed"
                              "?property=sandbox&evidence=sandbox2026").body).lower()
        assert "asked as of" in text
        assert "?as_of=" in text

    def test_the_run_page_explains_what_a_provider_call_costs(self):
        """R1 and criterion 4, in a sentence: the number beside "provider call(s)" is the
        reason every control declares a bounded population."""
        text = text_of(handle("/run/checkout_money_owed"
                              "?property=sandbox&evidence=sandbox2026").body).lower()
        assert "one call per record" in text

    def test_the_run_page_explains_the_three_evidence_columns(self):
        """Criterion 3's columns are `field`, `value` and `from`, and "from" is the one nobody
        guesses: it is the call the value came from, which is what makes the trail auditable."""
        text = text_of(handle("/run/checkout_money_owed"
                              "?property=sandbox&evidence=sandbox2026").body).lower()
        assert "which call produced it" in text

    def test_a_run_with_no_tiles_explains_why_there_are_none(self):
        """Criterion 8 is the most easily mistaken-for-a-bug thing on the screen. A reader who
        thinks the tiles failed to render learns nothing; a reader told that four zeroes would
        have read as a clean bill of health learns the product's whole argument."""
        text = text_of(handle("/run/ooo_room_protection"
                              "?property=sandbox&evidence=sandbox2026").body).lower()
        assert 'class="tiles"' not in handle("/run/ooo_room_protection"
                                            "?property=sandbox&evidence=sandbox2026").body
        assert "no counts are shown" in text

    def test_a_blocked_run_is_not_told_it_concluded_nothing(self):
        """Two different absences, and they must not share one sentence. A run that CONCLUDED
        NOTHING looked at records and could not decide about any of them. A BLOCKED run never
        got the evidence to look at all. Telling a reader the second one "concluded nothing"
        describes a run that did not happen, and the distinction between "we looked and could
        not tell" and "we could not look" is the same distinction as UNKNOWN against FAIL."""
        blocked = text_of(render.run_page(a_run(blocked="this capture never held that window"),
                                          plan=None, readiness=(), links={})).lower()
        nothing = text_of(render.run_page(
            a_run([a_verdict(Outcome.EXCLUDED, record_id="a")]),
            plan=None, readiness=(), links={})).lower()
        assert "no counts are shown" in blocked and "no counts are shown" in nothing
        assert "never ran" in blocked
        assert "never ran" not in nothing

    def test_the_run_explainer_points_at_the_glossary_rather_than_repeating_it(self):
        """The four answers are defined once, beside the badges, where a puzzled reader is
        looking. Two copies of a glossary is two things to keep in step, and criterion 2's
        wording signal has exactly one source - `WORDING`."""
        page = handle("/run/checkout_money_owed"
                      "?property=sandbox&evidence=sandbox2026").body
        folded = re.search(r'<div class="folded">(.*?)</div>', page, re.S).group(1)
        assert "What the four answers mean" in text_of(page)
        assert "not a pass and not a failure" not in text_of(folded), \
            "the glossary is the one place the four answers are defined"

    def test_the_index_explains_the_readiness_ratio(self):
        """Criterion 10's number, in words. "5 of 5 fields available" is meaningless until
        somebody says what a field is and what to do when one is missing."""
        text = text_of(handle("/").body).lower()
        assert "fields the rule needs" in text
        assert "connect a source" in text

    def test_the_index_explains_what_a_body_of_evidence_is(self):
        """A "body of evidence" is this project's own term for a frozen set of real API
        responses. Nobody arrives knowing it, and the whole page is organised around it."""
        text = text_of(handle("/").body).lower()
        assert "frozen set of real responses" in text


# ---------------------------------------------------------------------------------------
class TestVerdictsAreGroupedByWhatTheyAskOfTheReader:
    """Slice 14, and it came from running the demo rather than from reading it.

    `/run/inactive_room_future_stay` renders 111 verdict blocks in population order, 71 of them
    NOT APPLICABLE because the reservation was cancelled. The one thing a reader came for - is
    anything wrong? - is somewhere in the middle of eighty screens of "this does not apply".

    So the verdicts are grouped by outcome and the groups are ordered by what they ask of the
    reader: VIOLATION first, then NO ANSWER (the product path), then PASS, then NOT APPLICABLE.
    The first two are OPEN, because they are the queue. The last two are `<details>` a click
    away - present in the markup, counted on the page, never hidden from a text scrape.
    """

    def test_the_groups_are_ordered_by_what_they_ask_of_the_reader(self):
        run = a_run([a_verdict(Outcome.EXCLUDED, record_id="x"),
                     a_verdict(Outcome.PASS, record_id="p"),
                     a_verdict(Outcome.UNKNOWN, record_id="u"),
                     a_verdict(Outcome.FAIL, record_id="f")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        order = [m for m in re.findall(r'id="verdicts-(\w+)"', page)]
        assert order == ["FAIL", "UNKNOWN", "PASS", "EXCLUDED"], order

    def test_a_violation_is_open_without_a_click(self):
        """A queue nobody can see is not a queue."""
        page = render.run_page(a_run([a_verdict(Outcome.FAIL)]), plan=None, readiness=(),
                               links={})
        group = re.search(r'<details[^>]*id="verdicts-FAIL"[^>]*>', page)
        assert group and "open" in group.group(0), group

    def test_an_unknown_is_open_too_because_it_is_the_product_path(self):
        page = render.run_page(a_run([a_verdict(Outcome.UNKNOWN)]), plan=None, readiness=(),
                               links={})
        group = re.search(r'<details[^>]*id="verdicts-UNKNOWN"[^>]*>', page)
        assert group and "open" in group.group(0), group

    def test_the_records_a_control_did_not_apply_to_are_one_click_away_not_gone(self):
        run = a_run([a_verdict(Outcome.FAIL, record_id="f"),
                     a_verdict(Outcome.EXCLUDED, record_id="007003917")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        group = re.search(r'<details[^>]*id="verdicts-EXCLUDED"[^>]*>', page)
        assert group and "open" not in group.group(0), group
        assert "007003917" in page, "a collapsed group is still in the markup"
        assert "NOT APPLICABLE" in text_of(page)

    def test_every_group_names_its_count_and_what_it_means(self):
        run = a_run([a_verdict(Outcome.EXCLUDED, record_id="a"),
                     a_verdict(Outcome.EXCLUDED, record_id="b")])
        text = text_of(render.run_page(run, plan=None, readiness=(), links={}))
        assert "2 records" in text
        assert "has not been checked" in text.lower()

    def test_an_outcome_with_no_records_gets_no_group(self):
        """An empty "0 violations" section is the tile-row failure in another costume."""
        page = render.run_page(a_run([a_verdict(Outcome.PASS)]), plan=None, readiness=(),
                               links={})
        assert 'id="verdicts-FAIL"' not in page
        assert 'id="verdicts-PASS"' in page

    def test_every_verdict_is_still_on_the_page_exactly_once(self):
        """Grouping must not drop or duplicate a record. 111 verdicts in, 111 out."""
        verdicts = [a_verdict(Outcome.EXCLUDED, record_id="x%d" % i) for i in range(7)]
        verdicts += [a_verdict(Outcome.PASS, record_id="p%d" % i) for i in range(5)]
        verdicts += [a_verdict(Outcome.UNKNOWN, record_id="u%d" % i) for i in range(3)]
        page = render.run_page(a_run(verdicts), plan=None, readiness=(), links={})
        assert page.count('<article class="verdict') == 15
        for verdict in verdicts:
            assert page.count(">%s<" % verdict.record_id) == 1, verdict.record_id

    def test_within_a_group_the_population_order_is_kept(self):
        """The order the evidence came in is itself evidence. Grouping regroups; it never
        sorts."""
        run = a_run([a_verdict(Outcome.PASS, record_id="third"),
                     a_verdict(Outcome.PASS, record_id="first"),
                     a_verdict(Outcome.PASS, record_id="second")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert re.findall(r'class="record">([^<]+)<', page) == ["third", "first", "second"]

    def test_a_count_tile_links_to_the_records_it_counts(self):
        """The tile row stops being a scoreboard and becomes the table of contents for a page
        that can be a hundred records long. A pure fragment link - no JavaScript."""
        run = a_run([a_verdict(Outcome.FAIL, record_id="f"),
                     a_verdict(Outcome.PASS, record_id="p")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert 'href="#verdicts-FAIL"' in page
        assert 'href="#verdicts-PASS"' in page

    def test_a_tile_for_an_outcome_with_no_records_is_not_a_link_to_nowhere(self):
        run = a_run([a_verdict(Outcome.PASS, record_id="p")])
        page = render.run_page(run, plan=None, readiness=(), links={})
        assert 'href="#verdicts-FAIL"' not in page
        assert "0" in page and "VIOLATION" in page, "the zero is still counted and shown"


# ---------------------------------------------------------------------------------------
class TestTheStylesheetCarriesTheSignalsItClaimsTo:
    """Criterion 2 lives in this file as much as in the markup, so slice 14's beautification
    has to be asserted rather than eyeballed."""

    def test_the_tile_row_carries_the_same_two_signals_as_a_verdict(self):
        """The tiles are the first thing a reader looks at and they used to be four identical
        grey boxes, so the distinction the whole product rests on was absent from the one
        component everybody reads. Same rule as a verdict block: own hue, own border style."""
        styles = {name: _tile_border_style(STYLESHEET, name) for name in ("FAIL", "UNKNOWN")}
        hues = {name: _tile_border_colour(STYLESHEET, name) for name in ("FAIL", "UNKNOWN")}
        assert all(styles.values()) and all(hues.values()), (styles, hues)
        assert styles["FAIL"] != styles["UNKNOWN"], styles
        assert hues["FAIL"] != hues["UNKNOWN"], hues

    def test_all_four_outcomes_have_a_styled_tile(self):
        for outcome in Outcome:
            assert _tile_border_style(STYLESHEET, outcome.value), outcome

    def test_the_four_verdict_border_styles_are_still_four_different_styles(self):
        """The existing tests only compare FAIL against UNKNOWN. A "harmonise the borders"
        beautification would pass those two and still destroy the distinction for the other
        pair, so the whole set is pinned here."""
        styles = {o.value: _border_style(STYLESHEET, o.value) for o in Outcome}
        assert len(set(styles.values())) == 4, styles

    def test_a_short_readiness_line_is_actually_coloured(self):
        """A real bug, found by reading the stylesheet against the markup. `render` emits
        `class="readiness short"` and the stylesheet said `.readiness .short` - a DESCENDANT
        selector, so the amber that marks a control the PMS cannot answer has never once been
        applied. Criterion 10's warning colour was silently off.

        Asserted over the RULES and not the file: this stylesheet carries long comments by
        design, and a comment that names the broken selector in order to explain it is the
        opposite of a regression."""
        rules = _rules_only(STYLESHEET)
        assert ".readiness.short" in rules
        assert ".readiness .short" not in rules
        assert render.run_page(a_run([]), plan=None, readiness=(), links={})

    def test_keyboard_focus_is_visible(self):
        """Everything added in this slice - the explanation bars, the verdict groups, the tile
        links - is operated by keyboard. A focus ring the browser default would have drawn and
        a custom one that forgets to are not the same page."""
        assert ":focus-visible" in STYLESHEET

    def test_the_explanation_affordance_is_styled_as_something_clickable(self):
        assert "summary" in STYLESHEET
        assert "cursor: pointer" in STYLESHEET

    def test_a_wide_table_scrolls_in_its_own_box_rather_than_the_page(self):
        """The evidence table holds an UNKNOWN's whole reason sentence, which is long. A page
        that scrolls sideways puts the verdict badge off screen, so the table gets its own
        scroll box and the page body never scrolls horizontally."""
        assert re.search(r"\.scroller\s*\{[^}]*overflow-x:\s*auto", STYLESHEET), \
            "the evidence table needs its own horizontal scroll container"
        assert '<div class="scroller">' in render.verdict_block(a_verdict(Outcome.FAIL))

    def test_the_page_still_prints(self):
        """Criterion 2 names a printout explicitly as one of the readers the border styles are
        for, so the stylesheet has to have an opinion about paper."""
        assert "@media print" in STYLESHEET


def _rules_only(stylesheet: str) -> str:
    """The stylesheet with its comments removed, for assertions about SELECTORS.

    This file is heavily commented on purpose - it is where a success criterion is written
    down - so a test that greps the raw text cannot tell a rule from the prose explaining it.
    """
    return re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.S)


def _tile_rule(stylesheet: str, outcome: str) -> str:
    match = re.search(r"\.tiles li\.%s\s*\{([^}]*)\}" % outcome, _rules_only(stylesheet))
    return match.group(1) if match else ""


def _tile_border_style(stylesheet: str, outcome: str) -> str:
    match = re.search(r"border-left:\s*[\d.]+\w*\s+(\w+)", _tile_rule(stylesheet, outcome))
    return match.group(1) if match else ""


def _tile_border_colour(stylesheet: str, outcome: str) -> str:
    match = re.search(r"border-left:\s*[\d.]+\w*\s+\w+\s+(#[0-9a-fA-F]+)",
                      _tile_rule(stylesheet, outcome))
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------------------
# Slice 15: the read-only JSON a second client needs. The React UI cannot build its index or its
# history page from the three routes that existed, so these four are the only Python the slice
# adds. Every one is a GET, a pure function of the path, and costs no provider call.
def _json(app, path):
    status, content_type, body = app.handle(path)
    assert content_type.startswith("application/json"), (path, body[:200])
    return status, json.loads(body)


def _no_run_may_happen(monkeypatch):
    """Make any attempt to execute a control fail loudly. Re-reading the spec is free; running
    a control spends provider calls, one per reservation for a folio (R1)."""
    import hotelcontrols.web.app as module

    def refuse(*_args, **_kwargs):
        raise AssertionError("a read-only route executed a control")
    monkeypatch.setattr(module, "run", refuse)


class TestIssue35HistoryKeepsCriterion8:
    """The history row is a run seen from further away, and keeps the run page's rules: counts
    only for a run that concluded something, a sentence instead for one that did not."""

    @staticmethod
    def row(passes=0, fails=0, unknowns=0, excluded=0, blocked=None):
        return {"run_id": "abc", "created_at": "2026-07-08T00:00:00+03:00",
                "evidence_label": "sandbox2026", "as_of": "2026-07-08", "calls": 2,
                "blocked": blocked, "passes": passes, "fails": fails, "unknowns": unknowns,
                "excluded": excluded, "total": passes + fails + unknowns + excluded}

    def _cell(self, row):
        return text_of(render.history_page("ooo_room_protection", [row])).lower()

    def test_all_excluded_is_no_conclusion_not_four_counts(self):
        text = self._cell(self.row(excluded=28))
        assert "reached no conclusion" in text and "28 record" in text
        assert "0 violation" not in text and "0 pass" not in text

    def test_all_unknown_is_no_conclusion_too(self):
        """UNKNOWN is not an answer either: thirteen gaps are not thirteen passes."""
        text = self._cell(self.row(unknowns=13))
        assert "reached no conclusion" in text and "0 violation" not in text

    def test_an_empty_population_says_there_was_nothing_to_check(self):
        text = self._cell(self.row())
        assert "nothing to check" in text and "0 violation" not in text

    def test_a_blocked_run_still_says_blocked(self):
        text = self._cell(self.row(blocked="no such window"))
        assert "blocked" in text and "0 violation" not in text

    def test_a_run_with_one_answer_shows_all_four_counts(self):
        """One PASS among exclusions is a conclusion; the counts, EXCLUDED included, are true."""
        text = self._cell(self.row(passes=1, excluded=27))
        assert "1 pass" in text and "0 violation" in text and "27 not applicable" in text


class TestSlice15TheControlsListIsOneRequest:
    """Criterion 10 for a second client: readiness per control per provider, in ONE request.

    One request rather than eleven because the server is serial (trap 6): eleven parallel
    readiness fetches from a browser are served one at a time, and the fix for that is never
    a threaded server - the store is a single-thread connection."""

    def test_every_reviewed_control_is_listed_with_what_the_index_shows(self):
        from hotelcontrols.spec import available, load
        status, payload = _json(App(), "/api/controls")
        assert status == 200
        assert [c["control_id"] for c in payload["controls"]] == list(available())
        for entry in payload["controls"]:
            ir = load(entry["control_id"])
            assert entry["name"] == ir.name
            assert entry["natural_language"] == ir.natural_language
            assert entry["entity"] == ir["entity"]
            assert entry["reviewed"] is True

    def test_readiness_is_the_same_object_the_readiness_route_serves(self):
        """One serialiser per object. A second hand-rolled shape for readiness is how two
        surfaces drift apart, and the drift would show up as a ratio that disagrees."""
        app = App()
        _status, payload = _json(app, "/api/controls")
        for entry in payload["controls"]:
            _s, single = _json(app, "/api/readiness/%s" % entry["control_id"])
            assert entry["readiness"] == single["providers"]

    def test_readiness_names_every_provider(self):
        from hotelcontrols.providers.registry import names
        _status, payload = _json(App(), "/api/controls")
        for entry in payload["controls"]:
            assert {r["provider"] for r in entry["readiness"]} == set(names())

    def test_it_costs_no_provider_call_and_writes_no_run(self, monkeypatch):
        """Brief §6: answerable from the spec alone. Asserted three ways - the function that
        executes a control refuses, the call counter does not move, and the history is empty."""
        _no_run_may_happen(monkeypatch)
        app = App()
        status, _payload = _json(app, "/api/controls")
        assert status == 200
        assert app.provider_calls == 0
        assert app.store.history() == []


class TestSlice15ThePropertiesListPowersTheEvidencePicker:

    def test_every_property_names_its_provider_and_its_captures(self):
        from hotelcontrols.spec import available_tenants
        app = App()
        status, payload = _json(app, "/api/properties")
        assert status == 200
        assert [p["id"] for p in payload["properties"]] == list(available_tenants())
        for entry in payload["properties"]:
            assert entry["name"]
            assert entry["provider"]
            assert entry["captures"] == list(app.captures_for(entry["id"]))
            assert entry["default_capture"] in entry["captures"]

    def test_it_says_which_property_and_evidence_a_run_uses_when_none_is_asked_for(self):
        """The HTML index states the selection it used rather than guessing silently. A client
        that guessed its own default could ask a different question than the page it mirrors."""
        app = App()
        _status, payload = _json(app, "/api/properties")
        assert (payload["default"]["property"], payload["default"]["evidence"]) == \
            app._selection({})

    def test_it_costs_no_provider_call(self, monkeypatch):
        _no_run_may_happen(monkeypatch)
        app = App()
        assert _json(app, "/api/properties")[0] == 200
        assert app.provider_calls == 0 and app.store.history() == []


class TestSlice15HistoryAsData:
    """The rows `/history/<id>` renders, as JSON - with the two gates a chart needs."""

    def test_an_unknown_control_is_the_same_404_the_page_gives(self):
        app = App()
        page_status = app.handle("/history/no_such_control").status
        status, payload = _json(app, "/api/history/no_such_control")
        assert status == page_status == 404
        assert "error" in payload

    def test_a_control_never_run_has_an_empty_history_not_a_refusal(self):
        status, payload = _json(App(), "/api/history/checkout_money_owed")
        assert status == 200
        assert payload == {"control_id": "checkout_money_owed", "runs": []}

    def test_a_run_appears_with_its_evidence_and_counts(self):
        app = App()
        live = json.loads(app.handle(
            "/api/run/checkout_money_owed?property=sandbox&evidence=sandbox2026").body)
        _status, payload = _json(app, "/api/history/checkout_money_owed")
        (row,) = payload["runs"]
        assert row["run_id"] == live["run_id"]
        assert row["evidence_label"] == "sandbox2026"
        assert row["provider"] == live["provider"]
        assert row["as_of"] == live["as_of"]
        assert row["calls"] == live["calls"]
        assert row["counts"] == live["counts"]
        assert row["concluded"] is live["coverage"]["concluded"] is True

    def test_a_run_that_concluded_nothing_is_flagged_even_though_it_has_counts(self):
        """Trap 1, pinned on the history route as well. `ooo_room_protection` excludes all 28
        rooms: its counts are four numbers, one of them a zero under FAIL, and a client that
        renders counts whenever they exist reproduces finding F5. `concluded` is the gate."""
        app = App()
        app.handle("/api/run/ooo_room_protection?property=sandbox&evidence=sandbox2026")
        (row,) = _json(app, "/api/history/ooo_room_protection")[1]["runs"]
        assert row["concluded"] is False
        assert row["counts"]["EXCLUDED"] == row["counts"]["total"] == 28

    def test_a_blocked_run_carries_its_reason_and_no_counts(self):
        """The same rule `run_json` keeps: zeroes in a payload get charted by somebody, and a
        chart of a run that never happened is a chart of nothing (F5)."""
        app = App()
        app.handle("/api/run/resource_occupancy_consistency?property=sandbox"
                   "&evidence=sandbox2026")
        (row,) = _json(app, "/api/history/resource_occupancy_consistency")[1]["runs"]
        assert row["blocked"]
        assert "counts" not in row
        assert row["concluded"] is False

    def test_it_is_newest_first_like_the_page(self):
        app = App()
        for capture in ("sandbox2024", "sandbox2026"):
            app.handle("/api/run/checkout_money_owed?property=sandbox&evidence=%s" % capture)
        rows = _json(app, "/api/history/checkout_money_owed")[1]["runs"]
        stamps = [row["created_at"] for row in rows]
        assert stamps == sorted(stamps, reverse=True)
        assert len(rows) == 2

    def test_reading_history_costs_no_provider_call(self):
        """R1: the history exists so that "what did it say?" is never answered by re-running."""
        app = App()
        app.handle("/api/run/checkout_money_owed?property=sandbox&evidence=sandbox2026")
        before = app.provider_calls
        _json(app, "/api/history/checkout_money_owed")
        assert app.provider_calls == before


class TestSlice15TheNewRoutesAreReadOnly:

    @pytest.mark.parametrize("path", ["/api/controls", "/api/properties",
                                      "/api/history/checkout_money_owed", "/api/drafts"])
    def test_none_of_them_accepts_a_post(self, path):
        """`handle(path)` stays a pure function of the path, and writes go through
        `handle_post` - which has exactly two routes, both compose. Nothing new writes."""
        status, content_type, _body = App().handle_post(path, "")
        assert status == 405
        assert content_type.startswith("application/json")

    @pytest.mark.parametrize("path", ["/api/controls", "/api/properties",
                                      "/api/history/checkout_money_owed", "/api/drafts"])
    def test_the_same_path_twice_gives_the_same_answer(self, path):
        app = App()
        assert app.handle(path) == app.handle(path)
