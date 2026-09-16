# -*- coding: utf-8 -*-
"""
L7 - the compose window, without a socket and without a model.

`handle(path)` is unchanged and still a pure function of a string. The two routes that WRITE
something get a second entry point, `handle_post(path, body)`, so the original signature and
every docstring about it stay true.

What this file protects:

    the default is OFF       `App()` wires no proposer, so the demo that has always existed
                             behaves exactly as it did. This is what keeps the other 1,501
                             tests meaningful.
    an absence is STATED     `/compose` with no proposer explains what is missing, and does not
                             404. Everywhere else in this system a thing that cannot happen
                             says which thing is missing; this must not be the exception.
    no JavaScript            the page is two forms and a re-render. The Content-Security-Policy
                             still forbids script entirely, and that is asserted on the header
                             AND on the markup.
    a draft is marked        runnable and unreviewed travel together, or the criterion-1 figure
                             in docs/plan.md stops meaning anything.
    the human is in the loop what compiles is the sentence in the BOX, not what the model said.
"""
import json
import pathlib
import re
import shutil

import pytest

from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.web import App, render
from hotelcontrols.web import server
from tools.proposers import ExplodingProposer, StubProposer


def text_of(markup: str) -> str:
    """The page as a reader with no CSS would receive it - the wording half of every claim."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()


@pytest.fixture
def drafts(tmp_path):
    """A drafts spec root, laid out exactly as `spec/drafts/` is."""
    directory = tmp_path / "drafts"
    (directory / "ir").mkdir(parents=True)
    for name in ("canonical_fields.json", "ir_schema.json"):
        shutil.copy(SPEC_DIR / name, directory / name)
    return directory


@pytest.fixture
def app(drafts):
    return App(proposer=StubProposer(), draft_dir=drafts)


EMAIL_RULE = ("sentence=every+reservation+where+reservation.status+is+%22checked_out%22"
              "+must+have+folio.balance_due+at+most+0"
              "&control_id=my_draft&name=My+Draft&template=checkout_money_owed"
              "&property=sandbox&evidence=sandbox2026")


# ---------------------------------------------------------------------------------------
class TestTheFeatureIsOffByDefault:

    def test_a_bare_app_wires_no_proposer(self):
        assert App().proposer is None
        assert App().draft_dir is None

    def test_the_index_does_not_advertise_a_feature_that_is_off(self):
        """An advertised link that answers "switched off" is worse than no link."""
        assert "/compose" not in App().handle("/")[2]

    def test_the_index_advertises_it_when_a_proposer_is_wired(self, app):
        body = app.handle("/")[2]
        assert "/compose" in body
        assert "stub" in text_of(body)

    def test_compose_explains_itself_rather_than_404ing(self):
        status, content_type, body = App().handle("/compose")
        assert status == 200
        assert content_type.startswith("text/html")
        readable = text_of(body)
        assert "No proposer is wired" in readable
        assert "tools.serve" in readable, "it must say how to turn it on"

    def test_posting_a_turn_with_no_proposer_is_refused_with_a_reason(self):
        status, _ct, body = App().handle_post("/compose", "prose=anything")
        assert status == 409
        assert "tools.serve" in text_of(body)

    def test_handle_is_still_a_pure_function_of_the_path(self, app):
        assert app.handle("/compose")[:2] == app.handle("/compose")[:2]


# ---------------------------------------------------------------------------------------
class TestATurn:

    def test_a_sentence_that_compiles_says_so_and_offers_to_file_it(self, app):
        status, _ct, body = app.handle_post(
            "/compose", "prose=every+reservation+must+record+a+guest+email")
        assert status == 200
        assert "THIS COMPILES" in text_of(body)
        assert 'action="/compose/accept"' in body

    def test_nothing_is_filed_by_asking(self, app, drafts):
        app.handle_post("/compose", "prose=every+reservation+must+record+a+guest+email")
        assert list((drafts / "ir").iterdir()) == [], "asking must not write anything"

    def test_the_sentence_arrives_in_an_editable_box(self, app):
        """The model's output is a suggestion. What runs is what a person committed to."""
        body = app.handle_post(
            "/compose", "prose=every+reservation+must+record+a+guest+email")[2]
        assert '<textarea id="sentence" name="sentence"' in body
        assert "reservation.guest.email" in body

    def test_a_refusal_names_the_missing_vocabulary_on_screen(self, app):
        body = app.handle_post("/compose", "prose=VIP+rooms+must+be+inspected")[2]
        readable = text_of(body)
        assert "REFUSED" in readable
        assert "room.inspection_status" in readable

    def test_a_refusal_offers_no_button_to_run_it(self, app):
        body = app.handle_post("/compose", "prose=VIP+rooms+must+be+inspected")[2]
        assert 'action="/compose/accept"' not in body

    def test_a_question_is_rendered_as_a_question_not_an_error(self, app):
        body = app.handle_post(
            "/compose", "prose=corporate+rates+must+belong+to+an+approved+company")[2]
        readable = text_of(body)
        assert "A QUESTION, NOT A RULE" in readable
        assert "REFUSED" not in readable
        assert "rate codes" in readable

    def test_a_question_offers_no_button_either(self, app):
        """§18 made structural: a proposer that declined to invent policy has produced no rule,
        and offering to run one anyway would undo the restraint worth having."""
        body = app.handle_post(
            "/compose", "prose=corporate+rates+must+belong+to+an+approved+company")[2]
        assert 'action="/compose/accept"' not in body

    def test_a_broken_proposer_renders_a_reason_not_a_traceback(self, drafts):
        broken = App(proposer=ExplodingProposer(), draft_dir=drafts)
        status, _ct, body = broken.handle_post("/compose", "prose=anything")
        assert status == 200
        assert "the proposer failed" in text_of(body)
        assert "Traceback" not in body

    def test_the_transcript_accumulates_across_turns(self, app):
        first = app.handle_post("/compose", "prose=VIP+rooms+must+be+inspected")[2]
        conversation = re.search(r'name="conversation" value="([^"]+)"', first).group(1)
        body = app.handle_post(
            "/compose", "conversation=%s&prose=every+reservation+must+record+a+guest+email"
                        % conversation)[2]
        readable = text_of(body)
        assert "This conversation" in readable
        assert "VIP rooms must be inspected" in readable

    def test_transcripts_are_capped(self, app):
        for index in range(80):
            app.handle_post("/compose", "conversation=c%d&prose=anything" % index)
        assert len(app.conversations) <= 64


# ---------------------------------------------------------------------------------------
class TestFilingADraft:

    def test_a_draft_is_written_and_the_reader_is_redirected_to_its_run(self, app, drafts):
        status, _ct, body = app.handle_post("/compose/accept", EMAIL_RULE)
        assert status == 303
        assert "/run/my_draft" in body
        assert (drafts / "ir" / "my_draft.json").exists()

    def test_the_draft_is_a_real_validated_ir(self, app, drafts):
        app.handle_post("/compose/accept", EMAIL_RULE)
        ir = json.loads((drafts / "ir" / "my_draft.json").read_text(encoding="utf-8"))
        assert ir["control_id"] == "my_draft"
        assert ir["source_control"] == "composed"
        assert ir["restricted_language"].startswith("every reservation where")
        assert ir["population"], "it borrowed a bounded population, or it could not run"

    def test_the_draft_says_in_its_own_file_that_it_is_unreviewed(self, app, drafts):
        """The provenance has to survive being read six months later by somebody who never saw
        the compose screen."""
        app.handle_post("/compose/accept", EMAIL_RULE)
        ir = json.loads((drafts / "ir" / "my_draft.json").read_text(encoding="utf-8"))
        caveats = " ".join(ir["caveats"])
        assert "DRAFT" in caveats and "criterion-1" in caveats

    def test_what_compiles_is_the_edited_sentence(self, app, drafts):
        """The box wins over whatever the model said. That is where the human is in the loop."""
        app.handle_post("/compose/accept", EMAIL_RULE.replace("at+most+0", "at+least+0"))
        ir = json.loads((drafts / "ir" / "my_draft.json").read_text(encoding="utf-8"))
        assert ir["assertion"]["predicates"][0]["operator"] == "gte"

    def test_a_draft_runs_end_to_end(self, app):
        app.handle_post("/compose/accept", EMAIL_RULE)
        status, _ct, body = app.handle("/run/my_draft?property=sandbox&evidence=sandbox2026")
        assert status == 200
        assert "My Draft" in body

    def test_a_draft_may_not_shadow_a_reviewed_control(self, app):
        """Two rules under one id would make a stored run ambiguous about which one produced
        it, and a run that cannot be attributed is not an audit trail."""
        status, _ct, body = app.handle_post(
            "/compose/accept", EMAIL_RULE.replace("control_id=my_draft",
                                                  "control_id=checkout_money_owed"))
        assert status == 409
        assert "already a reviewed control" in text_of(body)

    def test_an_id_from_a_text_box_cannot_escape_the_directory(self, app, drafts):
        status, _ct, _body = app.handle_post(
            "/compose/accept",
            EMAIL_RULE.replace("control_id=my_draft", "control_id=..%2F..%2Fetc%2Fpasswd"))
        assert status in (303, 400)
        assert not list(drafts.parent.glob("**/passwd*"))
        for path in (drafts / "ir").iterdir():
            assert path.name.endswith(".json") and "/" not in path.stem

    def test_a_sentence_that_does_not_compile_is_not_filed(self, app, drafts):
        status, _ct, body = app.handle_post(
            "/compose/accept",
            "sentence=every+reservation+must+have+room.inspection_status+exists"
            "&control_id=bad&template=checkout_money_owed")
        assert status == 200
        assert "REFUSED" in text_of(body)
        assert list((drafts / "ir").iterdir()) == []

    def test_an_empty_sentence_is_refused(self, app):
        assert app.handle_post("/compose/accept", "sentence=&control_id=x")[0] == 400

    def test_an_id_that_slugs_to_nothing_is_refused(self, app):
        status, _ct, body = app.handle_post(
            "/compose/accept", EMAIL_RULE.replace("control_id=my_draft", "control_id=---"))
        assert status == 400
        assert "needs an id" in text_of(body)

    def test_an_app_with_no_drafts_directory_refuses_to_file(self):
        status, _ct, body = App(proposer=StubProposer()).handle_post(
            "/compose/accept", EMAIL_RULE)
        assert status == 409
        assert "nowhere to file" in text_of(body)


# ---------------------------------------------------------------------------------------
class TestADraftIsMarkedEverywhereItAppears:

    def test_the_index_badges_it_and_says_it_is_uncounted(self, app):
        app.handle_post("/compose/accept", EMAIL_RULE)
        readable = text_of(app.handle("/")[2])
        assert "draft" in readable and "unreviewed" in readable
        assert "not counted in the criterion-1 figure" in readable

    def test_a_draft_is_not_one_of_the_reviewed_controls(self, app):
        app.handle_post("/compose/accept", EMAIL_RULE)
        assert "my_draft" not in app._controls()
        assert "my_draft" in app._drafts()
        assert app.is_draft("my_draft")

    def test_a_draft_cannot_be_borrowed_as_a_population_template(self, app):
        """Only reviewed controls are offered, so a draft's population cannot propagate into
        another draft without a person having looked at it once."""
        app.handle_post("/compose/accept", EMAIL_RULE)
        assert "my_draft" not in [control_id for control_id, _entity in app._templates()]


# ---------------------------------------------------------------------------------------
class TestStillNoJavaScript:

    def test_the_policy_header_is_unchanged_on_a_compose_page(self, app):
        _status, headers, _payload = server.respond(app, "/compose")
        assert headers["Content-Security-Policy"] == "default-src 'none'; style-src 'self'; " \
                                                     "img-src 'self'"

    def test_the_compose_page_loads_no_script(self, app):
        body = app.handle("/compose")[2]
        assert "<script" not in body.lower()
        assert "onclick" not in body.lower() and "javascript:" not in body.lower()

    def test_a_post_response_carries_the_policy_and_a_location(self, app):
        status, headers, _payload = server.respond(app, "/compose/accept", EMAIL_RULE)
        assert status == 303
        assert headers["Location"].startswith("/run/my_draft")
        assert headers["Content-Security-Policy"]

    def test_content_length_counts_bytes_not_characters(self, app):
        """The captures hold Hebrew free text; a length counted in characters truncates the
        page in the reader's browser, which looks like a corrupted verdict."""
        _status, headers, payload = server.respond(app, "/compose")
        assert int(headers["Content-Length"]) == len(payload)


class TestRoutingRefusals:

    def test_a_form_posted_somewhere_that_takes_none_is_refused(self, app):
        status, _ct, body = app.handle_post("/run/checkout_money_owed", "prose=x")
        assert status == 405
        assert "accepts a form" in text_of(body)

    def test_an_oversized_body_is_never_parsed(self, app):
        """Asserted at the server, because the point is that it is refused BEFORE being read."""
        assert server.MAX_BODY == 64 * 1024

    def test_everything_from_a_proposer_is_escaped(self, drafts):
        """A proposer's output reaches a page. It is text from a model, and it is escaped like
        every other value that came from outside this engine."""
        class Injecting:
            name = "injecting"

            def propose(self, prose, history=()):
                return "<script>alert(1)</script> not a rule"

        body = App(proposer=Injecting(), draft_dir=drafts).handle_post(
            "/compose", "prose=anything")[2]
        assert "<script>" not in body
        assert "&lt;script&gt;" in body


# ---------------------------------------------------------------------------------------
class TestTheComposePageShowsWhatIsAlreadyFiled:

    def test_existing_drafts_are_listed_with_their_sentences(self, app):
        """So a second visit is a place to work from rather than a blank box. The sentence is
        shown because it is the reviewable artefact - the thing a person promotes or deletes."""
        app.handle_post("/compose/accept", EMAIL_RULE)
        readable = text_of(app.handle("/compose")[2])
        assert "Drafts" in readable
        assert "My Draft" in readable
        assert "folio.balance_due at most 0" in readable
        assert "spec/drafts/README.md" in readable, "promotion must say where it is documented"

    def test_a_proposer_with_no_name_attribute_still_renders(self, drafts):
        """A proposer is somebody else's object. `name` is a label this engine asks for, not a
        capability it may assume - and a missing one must not take the page down."""
        class Nameless:
            def propose(self, prose, history=()):
                return "every reservation must have folio.balance_due at most 0"

        page = App(proposer=Nameless(), draft_dir=drafts).handle("/compose")
        assert page[0] == 200
        assert "Nameless" in page[2]


class TestAnEmptySpecDirectoryHasNothingToBorrow:
    """A population cannot be invented, so with no reviewed control to borrow one from, filing
    a draft is refused rather than attempted. R1/R8: an unbounded control is an unbounded
    number of calls against somebody else's server."""

    @pytest.fixture
    def bare(self, tmp_path):
        spec = tmp_path / "spec"
        (spec / "ir").mkdir(parents=True)
        (spec / "tenants").mkdir()
        (spec / "providers").mkdir()
        for name in ("canonical_fields.json", "ir_schema.json"):
            shutil.copy(SPEC_DIR / name, spec / name)
        for name in ("minihotel.json", "demopms.json"):
            shutil.copy(SPEC_DIR / "providers" / name, spec / "providers" / name)
        shutil.copy(SPEC_DIR / "tenants" / "sandbox.json", spec / "tenants" / "sandbox.json")
        drafts = tmp_path / "drafts"
        (drafts / "ir").mkdir(parents=True)
        for name in ("canonical_fields.json", "ir_schema.json"):
            shutil.copy(SPEC_DIR / name, drafts / name)
        return spec, drafts

    def test_filing_is_refused_with_a_reason(self, bare):
        spec, drafts = bare
        app = App(spec_dir=spec, proposer=StubProposer(), draft_dir=drafts)
        status, _ct, body = app.handle_post("/compose/accept", EMAIL_RULE)
        assert status == 400
        assert "needs a population" in text_of(body)

    def test_nothing_is_written(self, bare):
        spec, drafts = bare
        app = App(spec_dir=spec, proposer=StubProposer(), draft_dir=drafts)
        app.handle_post("/compose/accept", EMAIL_RULE)
        assert list((drafts / "ir").iterdir()) == []
