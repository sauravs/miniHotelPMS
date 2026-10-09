# -*- coding: utf-8 -*-
"""
RENDERING - a verdict, on screen, with its working shown.

Pure functions from objects to strings. No I/O, no routing, no state: a page is a value, which
is what lets the whole demo be asserted without a socket.

THE THREE THINGS THIS FILE IS ACCOUNTABLE FOR
----------------------------------------------
**Criterion 2.** UNKNOWN is distinguishable from FAIL by hue, border AND wording. The first two
live in `assets/style.css`; the third lives here, in `WORDING`, and it is the one that survives
a monochrome screen, a printout, a colour-blind reader and a text-only scrape. "VIOLATION" and
"NO ANSWER" are different words, and the sentence under each says which of the four things
happened in full. A reader who cannot tell "we found a problem" from "we could not tell" has
been told nothing useful, and that reader is the entire audience for this product.

**Criterion 3.** Every verdict block carries each field, its value WITH ITS UNIT, and the call
the value came from. A balance rendered as `3262.50` rather than `3262.50 ILS` is a criterion-3
failure however correct the arithmetic behind it was - the folio is in ILS while the
reservation is in USD and no exchange rate exists anywhere in the API (R9), so the currency on
screen is the only thing stopping a reader from doing the subtraction in their head.

**Criterion 8, which is really finding F5.** A run that concluded nothing shows NO COUNT TILES.
v1 rendered `28 EXCLUDED / 0 FAIL` for a control on a property where the mechanism had never
been observed working, and on screen it was indistinguishable from a clean bill of health. Four
zeroes are not a result. So the tiles are rendered only when `coverage.concluded` is true, and
otherwise the space they would have occupied says what actually happened.

EVERYTHING FROM A PROVIDER IS ESCAPED
--------------------------------------
Guest names, surnames, free-text remarks and channel confirmation ids are in this data, and
they arrive from booking channels. `_e` is not optional anywhere a value, reason, id or
provenance string is interpolated.
"""
from __future__ import annotations

import html
import json
import pathlib
from typing import Any, Iterable

from ..kernel import Outcome, Verdict
from ..runner import Coverage, Run

ASSETS = pathlib.Path(__file__).resolve().parent / "assets"
STYLESHEET = (ASSETS / "style.css").read_text(encoding="utf-8")

# Criterion 2's third signal. A badge and a sentence per outcome, so the four are told apart by
# WORDS and not only by colour. EXCLUDED gets the longest sentence on purpose: it is the one a
# reader is most likely to file mentally under "fine", and it means the opposite of checked.
WORDING = {
    Outcome.PASS: ("PASS", "The rule holds for this record."),
    Outcome.FAIL: ("VIOLATION", "This record breaks the rule."),
    Outcome.UNKNOWN: ("NO ANSWER",
                      "The evidence needed to decide this was not available, so it is not a "
                      "pass and not a failure. The gaps are named in the table below."),
    Outcome.EXCLUDED: ("NOT APPLICABLE",
                       "The control does not apply to this record, so it has not been "
                       "checked. This is not a pass."),
}

# The order tiles are read in: what we concluded first, what we could not conclude after.
TILE_ORDER = (Outcome.PASS, Outcome.FAIL, Outcome.UNKNOWN, Outcome.EXCLUDED)

# The order the VERDICT GROUPS are read in, which is a different question from the tile row.
# Tiles are a scoreboard and read best as "concluded, then not concluded". A list of a hundred
# records is a WORK QUEUE, and a queue is ordered by what it asks of the reader: a violation is
# something to act on, an UNKNOWN is something to connect, a pass is something to confirm, and
# a record the control never applied to asks nothing at all.
#
# Found by running the demo rather than by reading it: `inactive_room_future_stay` answers about
# 111 stays, 71 of them NOT APPLICABLE because the reservation was cancelled, so in population
# order the thirteen records that could not be answered were eighty screens down.
GROUP_ORDER = (Outcome.FAIL, Outcome.UNKNOWN, Outcome.PASS, Outcome.EXCLUDED)

# Which groups are expanded without a click. The first two are the queue; the other two are a
# `<details>` away - present in the markup, counted in the tile row, never hidden from a text
# scrape, and one keypress from open. Collapsing is not the same as omitting, and criterion 8
# is about OMITTING a count: the counts are all still there.
OPEN_GROUPS = (Outcome.FAIL, Outcome.UNKNOWN)

# WORDING describes ONE record ("this record breaks the rule"). A group heading describes many,
# and the plural needs its own sentence rather than a grammatical patch on the singular one.
# Both halves of criterion 2's wording signal survive here: "not passes and not failures" for
# UNKNOWN, "not been checked" and "not a pass" for EXCLUDED.
GROUP_MEANING = {
    Outcome.FAIL: "These records break the rule. This is the queue to act on.",
    Outcome.UNKNOWN: "The evidence needed to decide these was not available, so they are not "
                     "passes and not failures. Each one names the gap it ran into, and that "
                     "gap is the thing to go and connect.",
    Outcome.PASS: "The rule holds for these records, and the evidence behind each one is here.",
    Outcome.EXCLUDED: "The control does not apply to these records, so they have not been "
                      "checked. This is not a pass.",
}


def _e(value: Any) -> str:
    """Escape anything on its way into a page. Never skipped, never conditional."""
    return html.escape("" if value is None else str(value), quote=True)


# --------------------------------------------------------------------------- documents
def page(title: str, subtitle: str, body: str, explainer: str = "", head: str = "") -> str:
    """The shell every page shares. No JavaScript, no external resource, one stylesheet.

    A WHOLE DOCUMENT, since slice 14. This used to begin at `<meta charset>` with no doctype,
    no `<html lang>` and no `<body>` - so every browser rendered the demo in quirks mode and
    every screen reader had to guess which language to pronounce it in. Neither is cosmetic
    and both were one line. The charset is still the first thing inside `<head>`, which is the
    part that ever mattered: a charset declared after the first kilobyte is one the browser has
    already guessed past, and these captures hold Hebrew free text.

    `explainer` is the page explanation bar and it goes ABOVE the content, because a reader who
    does not yet know what EXCLUDED means cannot use anything below it. `head` exists for the
    redirect body's meta refresh, which is the one piece of markup that has to be in the head.
    """
    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%s</title>"
        '<link rel="stylesheet" href="/style.css">'
        "%s"
        "</head>"
        "<body>"
        '<a class="skip" href="#main">Skip to the content</a>'
        '<header class="masthead"><div>'
        '<h1><a href="/">Hotel control engine</a></h1>'
        "<p>%s</p>"
        "</div></header>"
        '<main id="main">%s%s</main>'
        "</body></html>"
        % (_e(title), head, _e(subtitle), explainer, body))


def explanation_bar(lede: str, *paragraphs: str) -> str:
    """The page explanation bar: one visible line, and the depth one click away.

    `<details><summary>`, AND THAT IS A REQUIREMENT RATHER THAN A PREFERENCE. The obvious
    alternative - `title="..."` - puts the explanation INSIDE a tag, where three different
    readers lose it at once: `text_of` strips it, so the no-CSS text scrape that proves
    criterion 2's wording signal cannot see it; a touch screen has no hover, so half the
    readers can never summon it; and screen readers announce it inconsistently or not at all.
    A `<details>` is plain HTML, needs no script, is reachable by keyboard, and its text
    survives every tag being stripped. Visible inline help beats hover-only help everywhere
    in this project.

    The LEDE is always visible and the detail is folded, which is the right split for a page
    somebody reads twice: the one-liner is orientation, and the rest is a glossary nobody
    needs on the second visit.

    Prose only. Every value from a provider is escaped by its own caller before it reaches
    here; nothing in this function escapes anything, because what it receives is this file's
    own literal sentences.
    """
    detail = "".join("<p>%s</p>" % text for text in paragraphs)
    return ('<section class="explainer" aria-label="About this page">'
            '<p class="lede">%s</p>'
            "<details><summary>How to read this page</summary>"
            '<div class="folded">%s</div></details></section>' % (lede, detail))


def outcome_glossary() -> str:
    """The four answers, with the badge a reader actually sees beside each meaning.

    Built FROM `WORDING` rather than restating it, so criterion 2's third signal has exactly
    one source. A glossary that drifted from the badges would be worse than none: it would
    teach a reader the wrong word for the thing in front of them.
    """
    rows = []
    for outcome in TILE_ORDER:
        badge, means = WORDING[outcome]
        rows.append('<dt><span class="chip %s">%s</span></dt><dd>%s</dd>'
                    % (_e(outcome.value), _e(badge), _e(means)))
    return ('<details class="glossary"><summary>What the four answers mean</summary>'
            '<dl>%s</dl>'
            '<p class="meta">Two of these are the ones that get read wrong. NO ANSWER is not a '
            "failure - nothing was established either way. NOT APPLICABLE is not a pass - the "
            "control never looked. Folding either one into a compliance number is how a report "
            "comes to say ninety passed about ninety records nobody checked.</p></details>"
            % "".join(rows))


def error_page(status: int, message: str) -> str:
    """A refusal is still a page.

    `handle` is the last thing before a socket, so whatever went wrong below it, a reader gets
    a sentence. A browser showing a connection reset tells nobody anything, and a stack trace
    on screen tells them something they cannot act on.
    """
    return page("%d" % status, "This request could not be answered.",
                '<div class="card"><p class="sentence">%d</p><p>%s</p>'
                '<p class="meta"><a href="/">Back to the controls</a></p></div>'
                % (status, _e(message)))


def error_json(status: int, message: str) -> str:
    return json.dumps({"status": status, "error": message}, indent=2)


# --------------------------------------------------------------------------- index
def index_page(entries: Iterable[tuple], properties: Iterable[tuple],
               current: tuple[str, str], compose: str = "",
               drafts: Iterable = ()) -> str:
    """Every control the spec defines, with what each provider could answer about it.

    Criterion 10, and finding F8 behind it. v1 had every ingredient - `required_evidence[]
    .source`, `resolvable` flags, provider coverage - and surfaced none of it, so nothing told
    a customer which controls their PMS could actually answer. That is the difference between
    UNKNOWN as a limitation and UNKNOWN as a product path: "connect your housekeeping system to
    enable this control" is a sentence somebody can act on.
    """
    tenant_id, capture = current
    chooser = ['<h2>Bodies of evidence</h2><div class="card">']
    for name, provider, captures, label in properties:
        chooser.append('<p class="meta"><strong>%s</strong> &middot; %s</p>'
                       '<p class="evidence-picker">' % (_e(name), _e(provider)))
        for one in captures:
            selected = (name == tenant_id and one == capture)
            # `aria-current` so a screen reader announces WHICH capture is selected. Bold text
            # is a visual-only signal, and this page is read by more than one kind of reader.
            chooser.append('<a class="%s"%s href="/?property=%s&amp;evidence=%s">%s</a>'
                           % ("current" if selected else "",
                              ' aria-current="page"' if selected else "",
                              _e(name), _e(one), _e(one)))
        chooser.append("</p>")
    chooser.append('<p class="meta">%s</p></div>' % _e(
        "A run is asked about the instant its evidence describes, unless a date is given as "
        "?as_of=. Asking a capture about a window it never covered is refused rather than "
        "answered with an empty population."))

    # The findings queue (slice 18), for the selected property. Always offered: it is a read of
    # our own store, and an empty one explains itself rather than reading as an all-clear.
    chooser.append(
        '<div class="card"><p class="sentence"><a href="/queue?property=%s">Findings queue</a>'
        '</p><p class="meta">Every VIOLATION a reviewed control found, as a task a person marks '
        "done or dismisses - beside what each control last concluded, because an empty queue "
        "is not an all-clear.</p></div>" % _e(tenant_id))

    # The compose entry point, and only when a proposer is actually wired. An advertised
    # feature that answers "switched off" is worse than one that is not advertised.
    if compose:
        chooser.append(
            '<div class="card"><p class="sentence"><a href="/compose">Compose a control from '
            'prose</a></p><p class="meta">Describe a rule in your own words and the '
            '<strong>%s</strong> proposer rewrites it as a restricted sentence, which the same '
            'deterministic grammar and the same validator then turn into a rule. Composed '
            'rules are filed as drafts.</p></div>' % _e(compose))

    cards = ["<h2>Controls</h2>"]
    for ir, reports in entries:
        cards.append(
            '<div class="card">'
            '<p class="sentence"><a href="/run/%s?property=%s&amp;evidence=%s">%s</a></p>'
            '<p class="meta">%s</p>'
            '<p class="meta"><code>%s</code> &middot; one record is one %s</p>'
            % (_e(ir.control_id), _e(tenant_id), _e(capture), _e(ir.name),
               _e(ir.natural_language), _e(ir.control_id), _e(ir["entity"])))
        for report in reports:
            short = "" if report.is_executable else " short"
            cards.append('<p class="readiness%s">%s</p>' % (short, _e(report.headline)))
        cards.append('<p class="meta"><a href="/history/%s?property=%s">history</a> &middot; '
                     '<a href="/api/readiness/%s">readiness JSON</a></p></div>'
                     % (_e(ir.control_id), _e(tenant_id), _e(ir.control_id)))

    # Drafts last and visibly separated. They are runnable and unreviewed, and mixing them in
    # with the eleven would blur exactly the line docs/plan.md's criterion-1 figure depends on.
    for ir in drafts:
        cards.append(
            '<div class="card"><p class="sentence">'
            '<a href="/run/%s?property=%s&amp;evidence=%s">%s</a> '
            '<span class="draft-badge">draft &middot; unreviewed</span></p>'
            '<p class="meta">%s</p>'
            '<p class="meta"><code>%s</code> &middot; one record is one %s &middot; '
            "not counted in the criterion-1 figure</p></div>"
            % (_e(ir.control_id), _e(tenant_id), _e(capture), _e(ir.name),
               _e(ir.natural_language), _e(ir.control_id), _e(ir["entity"])))

    return page("Controls", "Every control the specification defines, and what each PMS could "
                            "answer about it.", "".join(chooser) + "".join(cards),
                explainer=_index_explainer())


def _index_explainer() -> str:
    """What a first-time reader needs before any of the cards below mean anything.

    Four terms on this page cannot be guessed from it: the SENTENCE is the rule rather than a
    description of one, READINESS is a ratio of fields and not a health score, a BODY OF
    EVIDENCE is a frozen capture rather than a live connection, and a DRAFT is runnable without
    being reviewed. Each one is a sentence, and it belongs on the screen rather than in a
    README nobody opens next to the thing it explains.
    """
    return explanation_bar(
        "Each card below is one governance rule. Pick one to run it against a body of "
        "captured evidence and see the fields behind every answer.",
        "<strong>The sentence</strong> at the top of a card is the rule itself, not a "
        "description of it. It compiles to something that runs, and nothing on the page is "
        "derived from anything else.",
        "<strong>Readiness</strong> - <code>5 of 5 fields available</code> - counts the "
        "fields the rule needs against the fields this property's system can actually "
        "supply, reported for each system separately. When it is short the line names what "
        "to <em>connect a source</em> for, and until that is connected the control answers "
        "NO ANSWER rather than guessing.",
        "<strong>A body of evidence</strong> is a frozen set of real responses, captured "
        "once from a live system and pseudonymised. A run replays it, so the same question "
        "always gets the same answer and nothing here ever touches a live system.",
        "<strong>Asked as of</strong> defaults to the instant the evidence describes rather "
        "than to today, because a capture of July can only answer honestly about July. Add "
        "<code>?as_of=YYYY-MM-DD</code> to a run's address to ask about another date.",
        "<strong>A draft</strong> is a rule composed from prose and filed but not reviewed. "
        "It is runnable but unreviewed, badged everywhere it appears, and deliberately not "
        "counted in the figure that reports how many controls reach an answer.")


# --------------------------------------------------------------------------- run
def run_page(run: Run, plan=None, readiness: Iterable = (), links: dict | None = None) -> str:
    """One run, with every verdict and the evidence behind it."""
    coverage = run.coverage
    parts = [
        '<div class="card">',
        '<p class="sentence">%s</p>' % _e(run.natural_language),
        '<p class="meta"><strong>%s</strong> &middot; <code>%s</code></p>'
        % (_e(run.control_name), _e(run.control_id)),
        '<p class="meta">Property <strong>%s</strong> &middot; provider <strong>%s</strong> '
        '&middot; evidence <strong>%s</strong>%s &middot; asked as of <strong>%s</strong> '
        '&middot; %d provider call(s)</p>'
        % (_e(run.tenant_id), _e(run.provider), _e(run.evidence_label),
           " (synthetic)" if run.evidence_is_synthetic else "", _e(run.as_of), run.calls),
        '<p class="meta policy">%s</p>' % policy_html(run.policy_version, run.policy_digest),
        _what_this_line_means(),
        '<p class="meta %s">%s</p>' % ("stale" if run.freshness.is_stale else "",
                                       _e(run.freshness.headline)),
    ]
    if plan is not None:
        parts.append('<p class="meta">%s</p>' % _e(plan.headline))
    for report in readiness:
        parts.append('<p class="readiness%s">%s</p>'
                     % ("" if report.is_executable else " short", _e(report.headline)))
    if links:
        parts.append('<p class="evidence-picker">')
        for label, href in links.items():
            parts.append('<a href="%s">%s</a>' % (_e(href), _e(label)))
        parts.append("</p>")
    parts.append("</div>")

    if run.is_blocked:
        # No tiles. A run that never happened has no counts, and rendering four zeroes for it
        # would be finding F5 with an extra step.
        parts.append('<div class="blocked"><p><strong>This control could not run against this '
                     'body of evidence.</strong></p><p>%s</p>%s</div>'
                     % (_e(run.blocked), _why_no_counts(True)))
        return page(run.control_name, "%s · %s" % (run.tenant_id, run.evidence_label),
                    "".join(parts), explainer=_run_explainer())

    if coverage.concluded:
        parts.append(_tiles(run.counts))
        parts.append('<p class="meta">%s</p>' % _e(coverage.headline))
    else:
        parts.append('<div class="no-conclusion"><p><strong>%s</strong></p>%s%s</div>'
                     % (_e(coverage.headline), _reasons(coverage), _why_no_counts(False)))

    if run.verdicts:
        parts.append(outcome_glossary())
        parts.append('<h2>Answers, record by record <span class="count">%d record%s</span></h2>'
                     % (len(run.verdicts), "" if len(run.verdicts) == 1 else "s"))
        parts.append(verdict_groups(run.verdicts))
    return page(run.control_name, "%s · %s" % (run.tenant_id, run.evidence_label),
                "".join(parts), explainer=_run_explainer())


def _run_explainer() -> str:
    """One run, explained. The highest-value four sentences on the whole demo.

    Every term here was unguessable from the screen before slice 14: the three evidence
    columns, the date the run asked about, the call count, and the four answers.
    """
    return explanation_bar(
        "One rule, run once over one body of captured evidence. Every answer below names "
        "the exact fields it was computed from.",
        "<strong>The four answers</strong> are PASS, VIOLATION, NO ANSWER and NOT "
        "APPLICABLE, and each one is defined beside the badges themselves under <em>What the "
        "four answers mean</em> - one glossary, next to the thing it explains. Each answer "
        "carries its own colour, its own border style and its own words, so the distinction "
        "survives a greyscale screen, a printout and a reader who sees no colour.",
        "<strong>The count tiles</strong> are a table of contents as well as a scoreboard: "
        "each one links to the records it counts. They are shown only when the run concluded "
        "something about at least one record - four zeroes with one of them under VIOLATION "
        "reads as a clean bill of health, and that is exactly what it would not be.",
        "<strong>The evidence table</strong> under each answer has three columns. "
        "<em>field</em> is the canonical name the rule asked for; <em>value</em> is what came "
        "back, always with its unit or its currency, because an amount without its currency "
        "is not an amount; <em>from</em> is which call produced it, which is the part that "
        "makes the trail auditable rather than anecdotal.",
        "<strong>Asked as of</strong> is the instant this run asked about. It defaults to the "
        "instant the body of evidence describes rather than to today, because a capture of "
        "July can only answer honestly about July. Add <code>?as_of=YYYY-MM-DD</code> to this "
        "address to ask about a different date; a date the engine cannot read is refused "
        "rather than guessed at.",
        "<strong>Provider call(s)</strong> is what this run cost. Some evidence is one call "
        "per record with no bulk endpoint behind it, so every rule declares a bounded "
        "population up front - and when a population would exceed the budget the budget is "
        "raised deliberately rather than the population being quietly truncated.")


def _what_this_line_means() -> str:
    """A note attached to the run's own facts line, rather than to the page.

    Separate from the explanation bar on purpose: this one sits beside the numbers it is
    about, which is where somebody puzzled by `asked as of 2026-07-08` is actually looking.
    """
    return ('<details class="aside"><summary>What do these say?</summary>'
            "<p><strong>Provider</strong> is which system answered. <strong>Evidence</strong> "
            "is which capture was replayed; a synthetic one is re-encoded from a real capture "
            "to prove the same rule runs on a second system. <strong>Asked as of</strong> is "
            "the instant the run asked about, which defaults to the instant that capture "
            "describes and not to today - override it with <code>?as_of=YYYY-MM-DD</code>. "
            "<strong>Provider call(s)</strong> is what the run cost: for some evidence that is "
            "one call per record, which is why every rule bounds its population first.</p>"
            "</details>")


def _why_no_counts(blocked: bool) -> str:
    """Why the tile row is absent, said where its absence is visible.

    Criterion 8 is the single most mistakable thing on this screen. A reader who concludes the
    tiles failed to render has learned nothing; a reader told that four zeroes would have read
    as a clean bill of health has been handed the product's entire argument.

    TWO DIFFERENT ABSENCES, AND THEY DO NOT SHARE A SENTENCE. A run that concluded nothing
    looked at records and could not decide about a single one. A BLOCKED run never obtained the
    evidence to look at all. Telling a reader the second one "concluded nothing" describes a
    run that did not happen - and "we looked and could not tell" against "we could not look"
    is the same distinction as UNKNOWN against FAIL, one level up.
    """
    what = ("a run that <strong>never ran</strong>: the evidence it needs was not in this "
            "body of responses, so there was nothing to reach a conclusion about"
            if blocked else
            "a run that looked at records and <strong>could not decide about a single "
            "one</strong>")
    return ('<details class="aside"><summary>Why are there no counts?</summary>'
            "<p>Deliberately. <strong>No counts are shown</strong> for %s, because four "
            "zeroes - one of them under VIOLATION - read as a clean bill of health. This "
            "control has not found the property compliant, and the reason is above.</p>"
            "</details>" % what)


def _tiles(counts: dict) -> str:
    """The count tiles: a scoreboard that is also the page's table of contents.

    Each tile carries its outcome's own hue and border style, the same two signals the verdict
    blocks carry (criterion 2) - they used to be four identical grey boxes, so the distinction
    the whole product rests on was missing from the one component every reader looks at first.

    A tile with records behind it is a FRAGMENT LINK to them. On a page that can be a hundred
    and eleven records long that is the difference between a number and a way in, and it costs
    no JavaScript: `href="#verdicts-FAIL"` is a 1993 feature. A tile with a zero is not a link,
    because a link to an absent section is a promise the page cannot keep - but the zero is
    still rendered, because an outcome nobody reached is a fact worth stating.
    """
    cells = []
    for outcome in TILE_ORDER:
        count = counts[outcome.value]
        inner = ('<span class="n">%d</span><span class="k">%s</span>'
                 % (count, _e(WORDING[outcome][0])))
        if count:
            cells.append('<li class="%s"><a href="#verdicts-%s">%s</a></li>'
                         % (_e(outcome.value), _e(outcome.value), inner))
        else:
            cells.append('<li class="%s"><span class="box">%s</span></li>'
                         % (_e(outcome.value), inner))
    return ('<ul class="tiles" aria-label="How many records reached each answer">%s</ul>'
            % "".join(cells))


def verdict_groups(verdicts: Iterable[Verdict]) -> str:
    """Every verdict, grouped by its answer, ordered by what the group asks of the reader.

    WHY THIS EXISTS. In population order, `inactive_room_future_stay` renders 111 verdicts of
    which 71 say "the reservation was cancelled, so this control does not apply" - and the
    thirteen records it could not answer, which are the entire product path, were interleaved
    somewhere in the middle of them. The reader's question is "what needs doing?", and the page
    answered "here is everything, in the order the hotel's database happened to return it".

    WHAT IS AND IS NOT HIDDEN. The groups that ask something - VIOLATION and NO ANSWER - are
    open. PASS and NOT APPLICABLE are a `<details>` away, and `<details>` is the right
    mechanism precisely because a closed one is still in the document: criterion 3's trail is
    intact, a text scrape sees every record, the counts are all still in the tile row, and one
    keypress opens it. Collapsing is not omitting.

    ORDER IS PRESERVED WITHIN A GROUP. The sequence the evidence arrived in is itself evidence,
    so this regroups and never sorts.
    """
    grouped: dict[Outcome, list[Verdict]] = {outcome: [] for outcome in GROUP_ORDER}
    for verdict in verdicts:
        grouped[verdict.outcome].append(verdict)

    sections = []
    for outcome in GROUP_ORDER:
        members = grouped[outcome]
        if not members:
            # No empty section, for the same reason there is no tile row on a run that
            # concluded nothing: a heading reading "0 violations" is a reassurance nobody
            # earned. The tile row already states the zero, where a zero belongs.
            continue
        badge = WORDING[outcome][0]
        sections.append(
            '<details class="group %s" id="verdicts-%s"%s>'
            '<summary><span class="chip %s">%s</span>'
            '<strong class="tally">%d record%s</strong>'
            '<span class="gist">%s</span></summary>'
            '<div class="group-body">%s</div></details>'
            % (_e(outcome.value), _e(outcome.value),
               " open" if outcome in OPEN_GROUPS else "",
               _e(outcome.value), _e(badge), len(members),
               "" if len(members) == 1 else "s", _e(GROUP_MEANING[outcome]),
               "".join(verdict_block(verdict) for verdict in members)))
    return "".join(sections)


def _reasons(coverage) -> str:
    """Why a run concluded nothing, in full rather than as one line.

    The commonest reason is usually the least informative: 71 of 111 stays are cancelled, which
    is a correct exclusion and tells a hotel nothing, while the 40 that mattered went unanswered
    for want of a configured room capacity. Showing the distribution lets a reader see both.
    """
    if not coverage.reasons:
        return ""
    rows = "".join("<tr><td>%d</td><td>%s</td></tr>" % (count, _e(reason))
                   for reason, count in coverage.reasons)
    return ('<div class="scroller"><table class="listing">'
            '<caption>Why this run concluded nothing, by number of records</caption>'
            '<tr><th scope="col">records</th><th scope="col">reason</th></tr>%s</table></div>'
            % rows)


def verdict_block(verdict: Verdict) -> str:
    """One record's answer, and the table that explains it.

    The class name carries hue and border; `WORDING` carries the words. All three are needed -
    see criterion 2 - and the words are the only one that survives being read aloud.
    """
    badge, means = WORDING[verdict.outcome]
    rows = "".join(_evidence_row(line) for line in verdict.evidence)
    # `scope="col"` and a `<caption>` so a screen reader announces what the table is and which
    # column a cell belongs to. The caption is visually quiet in CSS and fully present in the
    # markup, which is the whole reason it is a caption and not a `title=`: with no stylesheet
    # at all it simply becomes visible, and the meaning never depended on the stylesheet.
    #
    # The scroller is around the table rather than on it. An UNKNOWN's reason is a whole
    # sentence, and a page that scrolls sideways puts the verdict badge off the screen.
    return (
        '<article class="verdict %s">'
        '<span class="badge">%s</span><span class="record">%s</span>'
        '<p class="says">%s</p><p class="means">%s</p>'
        '<div class="scroller"><table class="evidence">'
        "<caption>Evidence behind this answer</caption>"
        '<tr><th scope="col">field</th><th scope="col">value</th>'
        '<th scope="col">from</th></tr>%s</table></div>'
        "</article>"
        % (_e(verdict.outcome.value), _e(badge), _e(verdict.record_id or "(no record id)"),
           _e(verdict.reason), _e(means), rows))


def _evidence_row(line) -> str:
    """One field, its value with its unit, and the call it came from. Criterion 3, literally."""
    value = line.value
    if value.is_known:
        cell = '<td>%s</td>' % _e(value)
    else:
        # An UNKNOWN's reason is its entire product value: not "we don't know" but "connect
        # this and we will". The risk id goes beside it so a reader can find the finding.
        cell = '<td class="gap">%s%s</td>' % (
            _e(value), ' <span class="mono">%s</span>' % _e(value.risk) if value.risk else "")
    return ('<tr><td><code>%s</code></td>%s<td class="from mono">%s</td></tr>'
            % (_e(line.field), cell, _e(line.source or "—")))


# --------------------------------------------------------------------------- history
def policy_html(version: int | None, digest: str | None) -> str:
    """Which rule judged a run - or, honestly, that nobody recorded it (slice 16, G6b).

    The version alone is a number a person keeps, so the digest of what that version says is
    shown beside it, shortened: two runs that both claim v2 but carry different digests were
    judged by two different rules, and a reader comparing them should be able to see that.
    """
    if version is None:
        return ("<strong>Version not recorded</strong> &middot; this run was stored before "
                "rules carried a version, so which version of the rule judged it cannot be "
                "said")
    return ("Judged under <strong>v%d</strong> of this rule%s"
            % (version, " &middot; digest <code>%s</code>" % _e(short_digest(digest))
               if digest else ""))


def short_digest(digest: str | None) -> str:
    """The first twelve hex characters - enough to tell two rules apart on a screen."""
    return (digest or "").split(":", 1)[-1][:12]


def policy_groups(rows: Iterable[dict]) -> list[tuple[tuple, list[dict]]]:
    """History rows grouped by `(policy_version, policy_digest)`, keeping their order.

    Groups appear in the order of their newest run, and runs keep their newest-first order
    inside a group - this regroups and never sorts. By version AND digest, so a rule edited
    without its bump still forms its own group rather than hiding inside the reviewed one.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row.get("policy_version"), row.get("policy_digest"))
        groups.setdefault(key, []).append(row)
    return list(groups.items())


def history_page(control_id: str, rows: Iterable[dict], tenant_id: str | None = None) -> str:
    """One property's past runs of one control, newest first.

    Every link carries `?property=` (slice 17): a stored run is read FOR a property, and a link
    without one would ask for the default property's copy and get a 404.

    Re-read from SQLite, so looking at what a control said last week costs nothing. That is not
    a convenience: a folio takes one call per reservation and there is no bulk journal endpoint
    (R1), so re-running a control to answer "what did it say?" is the expensive mistake.
    """
    rows = list(rows)
    if not rows:
        body = ('<div class="card"><p>This control has not been run in this session yet.</p>'
                '<p class="meta"><a href="/run/%s%s">Run it</a></p></div>'
                % (_e(control_id), "?property=%s" % _e(tenant_id) if tenant_id else ""))
        # The same explanation bar as the populated page. An empty history is the FIRST page
        # some readers will see, and it is the one where "why does this exist?" needs an answer.
        return page("History", control_id, body, explainer=_history_explainer())

    property_query = "?property=%s" % _e(tenant_id) if tenant_id else ""
    groups = []
    for (version, digest), members in policy_groups(rows):
        cells = ['<tbody><tr class="policy"><th colspan="6" scope="rowgroup">%s</th></tr>'
                 % policy_html(version, digest)]
        for row in members:
            cells.append(
                '<tr data-created="%s"><td class="mono"><a href="/api/runs/%s%s">%s</a></td>'
                "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (_e(row["created_at"]), _e(row["run_id"]), property_query, _e(row["run_id"]),
                   _e(row["created_at"]), _e(row.get("evidence_label")), _e(row["as_of"]),
                   _e(row["calls"]), _history_outcome(row)))
        groups.append("".join(cells) + "</tbody>")

    body = ('<div class="card"><div class="scroller"><table class="listing">'
            "<caption>Every run of this control in this session, newest first, grouped by "
            "the version of the rule that judged it</caption>"
            '<thead><tr><th scope="col">run</th><th scope="col">made</th>'
            '<th scope="col">evidence</th><th scope="col">as of</th>'
            '<th scope="col">calls</th><th scope="col">outcome</th></tr></thead>%s</table></div>'
            '<p class="meta">Re-reading any of these costs no provider call (R1).</p></div>'
            % "".join(groups))
    return page("History", "%s · %s" % (control_id, tenant_id) if tenant_id else control_id,
                body, explainer=_history_explainer())


def _history_outcome(row: dict) -> str:
    """One history row's outcome cell, under the run page's rules (criterion 8, issue #35).

    This cell used to gate on `blocked` alone, so a run that concluded nothing was listed as
    "0 pass - 0 violation - 0 no answer - 28 not applicable" on the very page an auditor reads
    as the summary - finding F5, one click away from the run page that had it right. Counts
    are shown only for a run that concluded something; otherwise the coverage headline is, and
    it comes from the engine's own `Coverage`, so the two pages cannot word it differently.
    """
    if row["blocked"]:
        return "blocked"
    evaluated = sum(row[_HISTORY_COLUMN[outcome]] or 0
                    for outcome in Outcome if outcome.is_answer)
    coverage = Coverage(evaluated=evaluated, total=row["total"] or 0)
    if not coverage.concluded:
        return _e(coverage.headline)
    return ("%s pass &middot; %s violation &middot; %s no answer &middot; %s not applicable"
            % tuple(row[_HISTORY_COLUMN[outcome]] or 0 for outcome in TILE_ORDER))


# Which column of a `RunStore.history` summary row counts which outcome.
_HISTORY_COLUMN = {Outcome.PASS: "passes", Outcome.FAIL: "fails",
                   Outcome.UNKNOWN: "unknowns", Outcome.EXCLUDED: "excluded"}


def _history_explainer() -> str:
    return explanation_bar(
        "Every run of this control in this session, newest first - what it was asked, what "
        "it answered, and what the answer cost.",
        "<strong>Re-reading a past run costs no provider call.</strong> That is not a "
        "convenience. Some evidence is one call per record on somebody else's server with no "
        "bulk endpoint behind it, so re-running a control just to answer <em>what did it "
        "say?</em> is the expensive mistake this page exists to prevent.",
        "<strong>The run id</strong> links to that run as data - the same verdicts and the "
        "same evidence trail, as JSON.",
        "<strong>Runs are grouped by the version of the rule that judged them</strong>, with "
        "the digest of what that version says. Two runs under v2 and v3 answered two different "
        "rules. A run stored before rules carried a version says <em>version not recorded</em> "
        "rather than borrowing today's.",
        "<strong>As of</strong> is the instant each run asked about, and <strong>evidence"
        "</strong> is which capture it replayed. Two runs that disagree usually asked "
        "different questions rather than got different answers.",
        "A run is identified by the question it asked, so reloading a run page replaces its "
        "entry rather than adding one. This history records distinct questions, not page "
        "loads.")


# --------------------------------------------------------------------------- json
def run_json(run: Run, plan=None, readiness: Iterable = ()) -> str:
    """The same run as data. Same content, same commitments, no counts for a blocked run."""
    coverage = run.coverage
    payload: dict[str, Any] = {
        "control_id": run.control_id,
        "control_name": run.control_name,
        "natural_language": run.natural_language,
        "tenant_id": run.tenant_id,
        "provider": run.provider,
        "evidence": {"label": run.evidence_label, "synthetic": run.evidence_is_synthetic},
        "as_of": run.as_of,
        "created_at": run.created_at.isoformat(),
        "calls": run.calls,
        "run_id": run.run_id,
        # Slice 16's declared contract change: which rule judged this run. Null on a run stored
        # before rules carried a version - never filled in with today's version.
        "policy_version": run.policy_version,
        "policy_digest": run.policy_digest,
        "blocked": run.blocked,
        "coverage": {
            "evaluated": coverage.evaluated,
            "total": coverage.total,
            "concluded": coverage.concluded,
            "headline": coverage.headline,
            "reasons": [{"reason": reason, "records": count}
                        for reason, count in coverage.reasons],
        },
        "freshness": {"stale": run.freshness.is_stale, "headline": run.freshness.headline},
        "readiness": [_readiness_json(report) for report in readiness],
        "verdicts": [_verdict_json(v) for v in run.verdicts],
    }
    if not run.is_blocked:
        # Present only when there was a run to count. Zeroes in a payload get charted by
        # somebody, and a chart of a run that never happened is a chart of nothing (F5).
        payload["counts"] = run.counts
    if plan is not None:
        payload["execution"] = {"mode": plan.mode, "declared_mode": plan.declared_mode,
                                "fell_back": plan.fell_back, "headline": plan.headline}
    return json.dumps(payload, indent=2)


def _verdict_json(verdict: Verdict) -> dict[str, Any]:
    return {
        "record_id": verdict.record_id,
        "outcome": verdict.outcome.value,
        "means": WORDING[verdict.outcome][1],
        "reason": verdict.reason,
        "evidence": [_line_json(line) for line in verdict.evidence],
    }


def _line_json(line) -> dict[str, Any]:
    """One evidence line as data, with money still carrying its currency.

    `str(Value)` rather than the raw payload, deliberately. A JSON number would be a bare
    amount, and a bare amount in this engine is a reservation in USD meeting its own folio in
    ILS with no exchange rate anywhere (R9). It is also how a Decimal survives `json.dumps`,
    which refuses one outright.
    """
    value = line.value
    return {
        "field": line.field,
        "known": value.is_known,
        "value": str(value) if value.is_known else None,
        "unit": value.unit,
        "reason": None if value.is_known else value.reason,
        "risk": value.risk,
        "source": line.source,
    }


def readiness_json(control_id: str, reports: Iterable) -> str:
    return json.dumps({"control_id": control_id,
                       "providers": [_readiness_json(r) for r in reports]}, indent=2)


def _readiness_json(report) -> dict[str, Any]:
    return {
        "provider": report.provider,
        "available": report.available,
        "total": report.total,
        "executable": report.is_executable,
        "headline": report.headline,
        "sources": [{"name": s.name, "available": s.available, "total": s.total,
                     "missing": list(s.missing)} for s in report.sources],
        "unresolvable": list(report.unresolvable),
        "tenant_supplied": list(report.tenant_supplied),
    }


# --------------------------------------------------------------------------- compose
def redirect(location: str, title: str = "Filed", subtitle: str = "The draft was written.",
             sentence: str = "Draft filed", onward: str = "the run") -> str:
    """A 303 body. Browsers follow the header; this is for everything that reads the body.

    The compose flow ends in a redirect so that filing a draft and then viewing its run are two
    different requests. Re-reading the run page must not re-file the draft, and a reload after a
    POST that answered with a page would do exactly that. Moving a task in the queue (slice 18)
    ends in one for the same reason, with its own words; compose's are the defaults.
    """
    # A meta refresh as well as the header, and it is not belt-and-braces: it is what the
    # location is READ BACK OUT OF by `server._location`. An `href` would not do - the page
    # shell already carries one for the stylesheet, and parsing "the first href" sent a reader
    # to /style.css. This attribute appears exactly once and only in a redirect.
    return page(title, subtitle,
                '<div class="card"><p class="sentence">%s</p>'
                '<p>Continue to <a href="%s">%s</a>.</p></div>'
                % (_e(sentence), _e(location), _e(onward)),
                head='<meta http-equiv="refresh" content="0; url=%s">' % _e(location))


def compose_page(proposer: str, conversation: str, transcript: Iterable,
                 templates: Iterable[tuple[str, str]], selection: tuple[str, str],
                 template: str = "", drafts: Iterable = (), result=None, compilation=None,
                 sentence: str | None = None) -> str:
    """The chat window: prose in, a restricted sentence out, a draft filed only on request.

    THE SENTENCE IS EDITABLE, AND THAT IS THE DESIGN. What the model returns is a suggestion in
    a text box. What compiles is whatever is in that box when the button is pressed, so the
    rule that runs is one a person committed to. Decision D10 rests on this: the model drafts,
    the deterministic grammar decides, and a human is between them.
    """
    tenant_id, capture = selection

    if not proposer:
        return page("Compose", "This front end is switched off.", _off_page(),
                    explainer=_compose_explainer(""))

    body = [
        '<div class="card">',
        '<p class="sentence">Compose a control</p>',
        # The proposer's NAME, which is the one thing here the explanation bar above cannot
        # say: it names how the page works, and this names what is actually wired into it.
        '<p class="meta">Drafting with the <strong>%s</strong> proposer. What compiles is the '
        'sentence you leave in the box, and you can edit it before anything runs.</p>'
        % _e(proposer),
        "</div>",
        _transcript(transcript),
    ]

    if result is not None:
        body.append(_proposal(result, templates, template, conversation, tenant_id, capture))
    if compilation is not None:
        # Reached when a person edited the sentence and pressed the button on something the
        # grammar refuses. The reasons are the same ones a hand-written IR would get.
        body.append(_refusal(compilation, sentence or ""))

    body.append(_ask_form(conversation, templates, template))
    body.append(_drafts_card(drafts, tenant_id, capture))

    return page("Compose", "Prose in, a restricted sentence out, and the same validator as "
                           "every hand-written rule.", "".join(body),
                explainer=_compose_explainer(proposer))


def _compose_explainer(proposer: str) -> str:
    """The three things on this screen that a reader cannot infer from it.

    This is the one page that asks somebody to type, and the one where a misunderstanding has
    consequences: a reader who believes their prose is what runs has misunderstood decision
    D10 in the direction that matters.
    """
    if not proposer:
        return explanation_bar(
            "This page turns a rule described in your own words into a rule that runs. It is "
            "switched off here, because it is the only part of this system that talks to a "
            "model at all.",
            "<strong>Nothing is missing and nothing is broken.</strong> The engine imports "
            "nothing outside the standard library and holds no HTTP client; every model "
            "backend lives outside the engine and is handed in at startup, so this front end "
            "exists only when somebody deliberately starts it. The commands are below.",
            "<strong>Even switched on, a model never decides a rule.</strong> It drafts one "
            "restricted sentence; the same deterministic grammar that compiles every "
            "hand-written rule compiles that sentence, and a person presses the button.")
    return explanation_bar(
        "Describe a rule in your own words. A model rewrites it as one restricted sentence, "
        "and the same deterministic grammar that compiles every hand-written rule compiles "
        "that sentence.",
        "<strong>What runs is the sentence in the box, not your prose.</strong> The model's "
        "suggestion arrives in a text box you can edit, and what compiles is whatever is in "
        "that box when you press the button - so a person is always between the model and the "
        "rule, and no answer anywhere in this system depends on a model call.",
        "<strong>Records to check</strong> borrows an existing control's bounded population. A "
        "sentence may not name an endpoint or a date window - that would tie the rule to one "
        "particular system and it would stop being portable - so that half of the document "
        "arrives as data, and the page says which control it was borrowed from.",
        "<strong>A filed draft is runnable but unreviewed.</strong> It is badged wherever it "
        "appears and is deliberately not counted in the figure that reports how many controls "
        "reach an answer. Promoting one to a reviewed control is a separate, manual act.",
        "<strong>A question is a valid answer.</strong> If the proposer will not invent hotel "
        "policy it asks you instead, and you get no button to run anything - a question is a "
        "better answer than a rule the hotel never asked for.")


def _off_page() -> str:
    return (
        '<div class="card blocked">'
        '<p class="sentence">No proposer is wired</p>'
        "<p>The compose front end is opt-in, because it is the only part of this system that "
        "talks to a model at all. The engine itself imports nothing outside the standard "
        "library and contains no HTTP client; every model backend lives under "
        "<code>tools/</code> and is handed in at startup.</p>"
        "<p class=\"meta\">Start it with one of:</p>"
        "<pre>HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub    "
        "# no model, fixed replies, nothing to install\n"
        "HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm local   "
        "# a model on this machine, free\n"
        "HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm claude  "
        "# the hosted API, paid</pre>"
        '<p class="meta"><a href="/">Back to the controls</a></p></div>')


def _transcript(transcript: Iterable) -> str:
    turns = list(transcript)
    if not turns:
        return ""
    rows = ['<div class="card"><p class="meta"><strong>This conversation</strong></p>']
    for turn in turns:
        rows.append('<p class="says"><span class="who">you</span> %s</p>' % _e(turn.prose))
        if turn.sentence:
            rows.append('<p class="proposed"><code>%s</code></p>' % _e(turn.sentence))
        if turn.question:
            rows.append('<p class="asked"><span class="who">asked</span> %s</p>'
                        % _e(turn.question))
        for problem in turn.problems:
            rows.append('<p class="refused">refused &middot; %s</p>' % _e(problem))
    rows.append("</div>")
    return "".join(rows)


def _proposal(result, templates, template: str, conversation: str, tenant_id: str,
              capture: str) -> str:
    """The latest turn, and the button that files it.

    A question gets no button. That is section 18 made structural: a proposer that declined to
    invent hotel policy has not produced a rule, and offering to run one anyway would undo the
    restraint that makes the answer worth having.
    """
    if result.is_question and not result.sentence:
        return (
            '<div class="card verdict UNKNOWN">'
            '<p><span class="badge">A QUESTION, NOT A RULE</span></p>'
            "<p class=\"says\">%s</p>"
            '<p class="means">The proposer declined to guess at hotel policy. Answer it below '
            "and it will try again - a question is a better answer than a rule the hotel did "
            "not ask for.</p></div>" % _e(result.question))

    if not result.ok:
        return _refusal(result.compilation, result.sentence, extra=result.problems)

    ir = result.compilation.ir
    fields = ir.get("required_evidence", [])
    return "".join([
        '<div class="card verdict PASS">',
        '<p><span class="badge">THIS COMPILES</span></p>',
        '<p class="means">The grammar parsed it and the validator accepted it. Nothing has '
        "been filed or run yet.</p>",
        '<form method="post" action="/compose/accept">',
        '<input type="hidden" name="conversation" value="%s">' % _e(conversation),
        '<input type="hidden" name="property" value="%s">' % _e(tenant_id),
        '<input type="hidden" name="evidence" value="%s">' % _e(capture),
        '<label for="sentence">The rule, as it will be compiled</label>',
        '<textarea id="sentence" name="sentence" rows="4">%s</textarea>' % _e(result.sentence),
        '<p class="meta">Edit this freely. What runs is what is in the box.</p>',
        '<p class="meta">Reads %d field(s): %s</p>'
        % (len(fields), _e(", ".join(entry["field"] for entry in fields))),
        '<label for="control_id">File it as</label>',
        '<input id="control_id" name="control_id" value="" placeholder="guest_email_on_file">',
        '<label for="name">Shown as</label>',
        '<input id="name" name="name" value="" placeholder="Guest Email On File">',
        _template_picker(templates, "template", template),
        '<button type="submit">File as draft and run it</button>',
        "</form></div>",
    ])


def _refusal(compilation, sentence: str, extra: Iterable = ()) -> str:
    """Why a sentence is not a rule, in the validator's own words.

    The sentence is shown even though it failed. An author cannot correct something they were
    never shown, and "the model said something wrong" is far less useful than seeing what.
    """
    reasons = [str(problem) for problem in extra]
    if compilation is not None:
        reasons += [str(problem) for problem in compilation.problems]
        reasons += ["Ambiguous, and it will not be guessed at: %s" % a
                    for a in compilation.ambiguities]

    rows = [
        '<div class="card verdict FAIL">',
        '<p><span class="badge">REFUSED</span></p>',
    ]
    if sentence:
        rows.append('<p class="proposed"><code>%s</code></p>' % _e(sentence))
    rows.append("<ul>")
    for reason in reasons or ["No reason was recorded, which is itself a defect."]:
        rows.append("<li>%s</li>" % _e(reason))
    rows.append("</ul>")
    rows.append('<p class="means">This is the same gate a hand-written rule goes through, and '
                "it names what is missing rather than guessing. Rephrase below, or edit the "
                "sentence and try again.</p>")
    rows.append("</div>")
    return "".join(rows)


def _ask_form(conversation: str, templates, template: str = "") -> str:
    return "".join([
        '<div class="card"><form method="post" action="/compose">',
        '<input type="hidden" name="conversation" value="%s">' % _e(conversation),
        '<label for="prose">Describe the rule</label>',
        '<textarea id="prose" name="prose" rows="3" '
        'placeholder="a reservation cannot be closed while the guest still owes money">'
        "</textarea>",
        _template_picker(templates, "template", template),
        '<button type="submit">Ask</button>',
        "</form></div>",
    ])


def _template_picker(templates, name: str, current: str = "") -> str:
    """Which existing control's bounded population a draft borrows.

    A sentence cannot name an endpoint without breaking criterion 5, so this half of the
    document arrives as data - and the honest source is a control that already runs over the
    records the new rule is about. `population` is also what bounds the call count to `1 + R +
    N`, so a draft without one is not runnable at any price (R1, R8).
    """
    options = []
    for control_id, entity in templates:
        options.append('<option value="%s"%s>%s &middot; one record is one %s</option>'
                       % (_e(control_id), " selected" if control_id == current else "",
                          _e(control_id), _e(entity)))
    return ('<label for="%s">Records to check</label>'
            '<select id="%s" name="%s">%s</select>'
            '<p class="meta">Borrowed from an existing control, because a sentence may not '
            "name an endpoint or a date window.</p>"
            % (_e(name), _e(name), _e(name), "".join(options)))


def _drafts_card(drafts, tenant_id: str, capture: str) -> str:
    irs = list(drafts)
    if not irs:
        return ""
    rows = ['<div class="card"><p class="meta"><strong>Drafts</strong> &middot; runnable, '
            "not reviewed, and not counted in the criterion-1 figure</p>"]
    for ir in irs:
        rows.append(
            '<p class="sentence"><a href="/run/%s?property=%s&amp;evidence=%s">%s</a> '
            '<span class="draft-badge">draft &middot; unreviewed</span></p>'
            '<p class="meta"><code>%s</code></p>'
            % (_e(ir.control_id), _e(tenant_id), _e(capture), _e(ir.name),
               _e(ir["restricted_language"] or ir.natural_language)))
    rows.append('<p class="meta">Promoting one is deliberate and manual - see '
                "<code>spec/drafts/README.md</code>.</p></div>")
    return "".join(rows)


# --------------------------------------------------------------------------- findings queue
# Slice 18. A FAIL becomes a task a person can see, mark done or dismiss. Two commitments carry
# over from the run page unchanged: everything a provider supplied is escaped, and an absence
# of tasks is never allowed to read as an absence of problems (criterion 8).

def persistence_sentence(persistent: bool) -> str:
    """Whether this queue survives a restart, said where the queue is (brief §8.8)."""
    if persistent:
        return "This queue is kept in a file store, with the run history, and survives a restart."
    return ("This queue is held in memory and is lost on restart, with the run history. Start "
            "the server with --store PATH to keep both in a file.")


def action_json(record) -> dict[str, Any]:
    """One task as data. One shape, used by the listing, the single read and every move."""
    def instant(value):
        return value.isoformat() if value is not None else None

    return {
        "action_id": record.action_id,
        "property": record.tenant_id,
        "control_id": record.control_id,
        "control_name": record.control_name,
        "record_id": record.record_id,
        # From the IR's own `action` block, copied when the task was raised. `audience` is
        # null when the rule names none - never a default somebody would then route by.
        "severity": record.severity,
        "audience": record.audience,
        "type": record.kind,
        # The FAIL verdict's own sentence, so the amount travels with its currency (R9).
        "reason": record.reason,
        "policy_version": record.policy_version,
        "policy_digest": record.policy_digest,
        "state": record.state,
        "state_changed_at": instant(record.state_changed_at),
        "state_changed_by": record.state_changed_by,
        "raised": {"run_id": record.raised_by_run, "at": instant(record.raised_at),
                   "as_of": record.as_of, "provider": record.provider,
                   "evidence": record.evidence_label},
        "last_failing": {"run_id": record.last_failing_run,
                         "at": instant(record.last_failing_at)},
        "cleared": (None if record.cleared_by_run is None else
                    {"run_id": record.cleared_by_run, "at": instant(record.cleared_at),
                     "as_of": record.cleared_as_of}),
        "annotation": record.annotation,
    }


# How each control's latest run is labelled in the queue's coverage table. Words, not only a
# style, for the same reason a verdict carries wording: it has to survive a greyscale screen.
STATUS_WORDS = {
    "concluded": "concluded",
    "no_conclusion": "reached no conclusion",
    "blocked": "blocked",
    "not_run": "not run here",
}


def queue_page(tenant_id: str, properties: Iterable[str], records: Iterable, controls: list,
               persistent: bool) -> str:
    """One property's findings queue: what is still to do, what was closed, and - beside it -
    what each control last concluded, so an empty queue cannot pass for an all-clear."""
    records = list(records)
    pending = [r for r in records if r.is_pending]
    closed = [r for r in records if not r.is_pending]
    query = "?property=%s" % _e(tenant_id)

    parts = ['<div class="card">',
             '<p class="sentence">Findings queue &middot; property <strong>%s</strong></p>'
             % _e(tenant_id),
             '<p class="evidence-picker">']
    for name in properties:
        current = name == tenant_id
        parts.append('<a class="%s"%s href="/queue?property=%s">%s</a>'
                     % ("current" if current else "", ' aria-current="page"' if current else "",
                        _e(name), _e(name)))
    parts.append("</p>")
    parts.append('<p class="meta%s">%s</p>' % ("" if persistent else " stale",
                                               _e(persistence_sentence(persistent))))
    parts.append("</div>")

    parts.append('<h2>To do <span class="count">%d task%s</span></h2>'
                 % (len(pending), "" if len(pending) == 1 else "s"))
    if not pending:
        parts.append(
            '<div class="no-conclusion"><p><strong>Nothing is waiting in this queue - and that '
            "is not an all-clear.</strong></p><p>A task is raised only by a VIOLATION, only by "
            "a reviewed control, and only from a run made against this store. NO ANSWER raises "
            "none, because whether it should is an open question for the hotel. The table "
            "below says, control by control, whether its latest run reached a conclusion at "
            "all.</p></div>")
    parts.extend(_task(record, tenant_id) for record in pending)

    if closed:
        parts.append('<details class="group EXCLUDED"><summary><strong class="tally">%d closed '
                     'task%s</strong><span class="gist">Marked done or dismissed by a person. '
                     "A run never closes a task.</span></summary>"
                     '<div class="group-body">%s</div></details>'
                     % (len(closed), "" if len(closed) == 1 else "s",
                        "".join(_task(record, tenant_id) for record in closed)))

    parts.append("<h2>What each control last concluded</h2>")
    rows = []
    for control in controls:
        latest = control["latest_run"]
        run_cell = ("&mdash;" if latest is None else
                    '<a class="mono" href="/api/runs/%s%s">%s</a><br>'
                    '<span class="meta">%s &middot; as of %s</span>'
                    % (_e(latest["run_id"]), query, _e(latest["run_id"]),
                       _e(latest["evidence_label"]), _e(latest["as_of"])))
        rows.append(
            "<tr><td><a href=\"/history/%s%s\">%s</a><br><code>%s</code></td>"
            "<td>%s &middot; %s</td><td>%s</td><td><strong>%s</strong> &middot; %s</td>"
            "<td>%d</td></tr>"
            % (_e(control["control_id"]), query, _e(control["name"]), _e(control["control_id"]),
               _e(control["severity"]), _e(control["audience"] or "no audience declared"),
               run_cell, _e(control["label"]), _e(control["headline"]),
               control["pending"]))
    parts.append(
        '<div class="card"><div class="scroller"><table class="listing">'
        "<caption>Each reviewed control's latest run against this store. Only a run that "
        "concluded something can raise a task; the others have not looked.</caption>"
        '<thead><tr><th scope="col">control</th><th scope="col">severity &middot; audience'
        '</th><th scope="col">latest run</th><th scope="col">what it says</th>'
        '<th scope="col">pending</th></tr></thead><tbody>%s</tbody></table></div></div>'
        % "".join(rows))

    return page("Findings queue", "%s · tasks raised by violations, and what each control "
                                  "last concluded" % tenant_id,
                "".join(parts), explainer=_queue_explainer())


def _task(record, tenant_id: str) -> str:
    """One task: what failed, why, under which rule, from which run - and the two moves.

    Styled as a VIOLATION, with the VIOLATION wording, because that is exactly what raised it.
    Each move is its own form: a page with no JavaScript cannot make one form post two states.
    """
    query = "?property=%s" % _e(tenant_id)
    lines = [
        '<article class="verdict FAIL task" id="task-%s">' % _e(record.action_id),
        '<span class="badge">%s</span><span class="record">%s</span>'
        % (_e(WORDING[Outcome.FAIL][0]), _e(record.record_id)),
        '<p class="says">%s</p>' % _e(record.reason),
        '<p class="meta"><strong>%s</strong> &middot; <code>%s</code> &middot; severity '
        "<strong>%s</strong> &middot; for <strong>%s</strong></p>"
        % (_e(record.control_name), _e(record.control_id), _e(record.severity),
           _e(record.audience or "no audience declared")),
        '<p class="meta">Raised by run <a class="mono" href="/api/runs/%s%s">%s</a>, asked as '
        "of %s, over %s &middot; last found failing by run <span class=\"mono\">%s</span></p>"
        % (_e(record.raised_by_run), query, _e(record.raised_by_run), _e(record.as_of),
           _e(record.evidence_label), _e(record.last_failing_run)),
        '<p class="meta policy">%s</p>' % policy_html(record.policy_version,
                                                       record.policy_digest),
    ]
    if record.annotation:
        lines.append('<p class="means">%s</p>' % _e(record.annotation))
    if record.is_pending:
        lines.append('<div class="moves">')
        for state, label in (("done", "Mark done"), ("dismissed", "Dismiss")):
            lines.append('<form method="post" action="/queue/%s">'
                         '<input type="hidden" name="property" value="%s">'
                         '<input type="hidden" name="state" value="%s">'
                         '<button type="submit">%s</button></form>'
                         % (_e(record.action_id), _e(tenant_id), state, label))
        lines.append("</div>")
    else:
        lines.append('<p class="meta"><strong>%s</strong> by %s at %s</p>'
                     % ("Marked done" if record.state == "done" else "Dismissed",
                        _e(record.state_changed_by), _e(record.state_changed_at.isoformat())))
    lines.append("</article>")
    return "".join(lines)


def _queue_explainer() -> str:
    return explanation_bar(
        "Every VIOLATION a reviewed control found becomes one task here. A person marks it "
        "done or dismisses it; running the control again never adds it twice.",
        "<strong>Only a VIOLATION raises a task.</strong> NO ANSWER does not: whether records "
        "nobody could check should become a review queue is an open question for the hotel, "
        "and this page does not answer it by accident. NOT APPLICABLE does not either, and "
        "nor does a run that concluded nothing or could not run at all.",
        "<strong>One task per record, per rule.</strong> Re-running a control finds the same "
        "task and updates which run last found it failing. A new version of the rule judges "
        "afresh, and the old task stays linked to the version that raised it.",
        "<strong>A run never closes a task.</strong> If a later run finds the record passing, "
        "the task says so - <em>no longer failing as of run X</em> - and stays pending, "
        "because the evidence only says the problem stopped showing, not that anybody dealt "
        "with it.",
        "<strong>Severity and audience</strong> come from the rule itself, word for word. A "
        "rule that names no audience says so rather than borrowing one.",
        "<strong>An empty queue is not an all-clear.</strong> The table at the bottom says "
        "what each control's latest run concluded. A control that was never run, could not "
        "run, or reached no conclusion has not looked - and has raised nothing for that "
        "reason alone.")
