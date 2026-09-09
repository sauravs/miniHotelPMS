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
from ..runner import Run

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


def _e(value: Any) -> str:
    """Escape anything on its way into a page. Never skipped, never conditional."""
    return html.escape("" if value is None else str(value), quote=True)


# --------------------------------------------------------------------------- documents
def page(title: str, subtitle: str, body: str) -> str:
    """The shell every page shares. No JavaScript, no external resource, one stylesheet."""
    return (
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%s</title>"
        '<link rel="stylesheet" href="/style.css">'
        '<header class="masthead"><div>'
        '<h1><a href="/">Hotel control engine</a></h1>'
        "<p>%s</p>"
        "</div></header>"
        "<main>%s</main>" % (_e(title), _e(subtitle), body))


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
               current: tuple[str, str]) -> str:
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
            chooser.append('<a class="%s" href="/?property=%s&amp;evidence=%s">%s</a>'
                           % ("current" if selected else "", _e(name), _e(one), _e(one)))
        chooser.append("</p>")
    chooser.append('<p class="meta">%s</p></div>' % _e(
        "A run is asked about the instant its evidence describes, unless a date is given as "
        "?as_of=. Asking a capture about a window it never covered is refused rather than "
        "answered with an empty population."))

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
        cards.append('<p class="meta"><a href="/history/%s">history</a> &middot; '
                     '<a href="/api/readiness/%s">readiness JSON</a></p></div>'
                     % (_e(ir.control_id), _e(ir.control_id)))

    return page("Controls", "Every control the specification defines, and what each PMS could "
                            "answer about it.", "".join(chooser) + "".join(cards))


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
                     'body of evidence.</strong></p><p>%s</p></div>' % _e(run.blocked))
        return page(run.control_name, "%s · %s" % (run.tenant_id, run.evidence_label),
                    "".join(parts))

    if coverage.concluded:
        counts = run.counts
        parts.append('<ul class="tiles">')
        for outcome in TILE_ORDER:
            parts.append('<li><span class="n">%d</span><span class="k">%s</span></li>'
                         % (counts[outcome.value], _e(WORDING[outcome][0])))
        parts.append("</ul>")
        parts.append('<p class="meta">%s</p>' % _e(coverage.headline))
    else:
        parts.append('<div class="no-conclusion"><p><strong>%s</strong></p>%s</div>'
                     % (_e(coverage.headline), _reasons(coverage)))

    parts.append("<h2>Verdicts</h2>" if run.verdicts else "")
    parts.extend(verdict_block(verdict) for verdict in run.verdicts)
    return page(run.control_name, "%s · %s" % (run.tenant_id, run.evidence_label),
                "".join(parts))


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
    return ('<table class="listing"><tr><th>records</th><th>reason</th></tr>%s</table>' % rows)


def verdict_block(verdict: Verdict) -> str:
    """One record's answer, and the table that explains it.

    The class name carries hue and border; `WORDING` carries the words. All three are needed -
    see criterion 2 - and the words are the only one that survives being read aloud.
    """
    badge, means = WORDING[verdict.outcome]
    rows = "".join(_evidence_row(line) for line in verdict.evidence)
    return (
        '<article class="verdict %s">'
        '<span class="badge">%s</span><span class="record">%s</span>'
        '<p class="says">%s</p><p class="means">%s</p>'
        '<table class="evidence"><tr><th>field</th><th>value</th><th>from</th></tr>%s</table>'
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
def history_page(control_id: str, rows: Iterable[dict]) -> str:
    """Past runs of one control, newest first.

    Re-read from SQLite, so looking at what a control said last week costs nothing. That is not
    a convenience: a folio takes one call per reservation and there is no bulk journal endpoint
    (R1), so re-running a control to answer "what did it say?" is the expensive mistake.
    """
    rows = list(rows)
    if not rows:
        body = ('<div class="card"><p>This control has not been run in this session yet.</p>'
                '<p class="meta"><a href="/run/%s">Run it</a></p></div>' % _e(control_id))
        return page("History", control_id, body)

    cells = []
    for row in rows:
        summary = ("blocked" if row["blocked"] else
                   "%s pass &middot; %s violation &middot; %s no answer &middot; "
                   "%s not applicable"
                   % (row["passes"] or 0, row["fails"] or 0, row["unknowns"] or 0,
                      row["excluded"] or 0))
        cells.append(
            '<tr data-created="%s"><td class="mono"><a href="/api/runs/%s">%s</a></td>'
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (_e(row["created_at"]), _e(row["run_id"]), _e(row["run_id"]),
               _e(row["created_at"]), _e(row.get("evidence_label")), _e(row["as_of"]),
               _e(row["calls"]), summary))

    body = ('<div class="card"><table class="listing">'
            "<tr><th>run</th><th>made</th><th>evidence</th><th>as of</th><th>calls</th>"
            "<th>outcome</th></tr>%s</table>"
            '<p class="meta">Re-reading any of these costs no provider call (R1).</p></div>'
            % "".join(cells))
    return page("History", control_id, body)


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
