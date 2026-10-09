# -*- coding: utf-8 -*-
"""
Slice 15: what the React UI must never do, checked by the REQUIRED Python suite.

`ui/` has its own suite, in its own CI job, deliberately not required - a broken `npm` must
never block an engine fix. These rules are too important to live only there, so they are
checked here, over the UI's source, by the suite that does block a merge. Each one is a trap from
`docs/slice-15-react-ui-brief.md` that would otherwise fail silently: the page would look fine.

    trap 2   money is a string carrying its currency. Parsing it keeps the number and drops the
             currency, and a bare amount invites arithmetic across currencies with no rate (R9).
    trap 3   provenance is opaque. The UI never spells out its prefix, so it cannot branch on it.
    trap 4   `GET /api/run/` spends provider calls and writes the store. Every request goes
             through one module, and no client component may reach it.
    trap 7   React escaping is now the only lock on guest names and free text, so the one API
             that disables it is banned outright; help is never a `title=` tooltip; and every
             dependency is pinned exactly with its lockfile committed.
"""
import json
import pathlib
import re
import subprocess

import pytest

UI = pathlib.Path(__file__).resolve().parents[2] / "ui"
SKIP = ("node_modules", ".next", "test-results", "playwright-report")


def _walk(root, skip):
    """Every file under `root`, PRUNING the skipped directories rather than filtering after -
    `node_modules` alone is hundreds of megabytes, and `rglob` would read every name in it."""
    import os
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = sorted(d for d in subdirectories if d not in skip)
        for name in sorted(names):
            yield pathlib.Path(directory) / name


def source(*suffixes, tests=True):
    """The UI's own source files. `tests=False` leaves out the two test directories."""
    for path in _walk(UI, SKIP):
        relative = path.relative_to(UI)
        if path.suffix not in suffixes:
            continue
        if any(part in SKIP for part in relative.parts):
            continue
        if not tests and relative.parts[0] in ("test", "e2e"):
            continue
        yield relative.as_posix(), path.read_text(encoding="utf-8")


CODE = (".ts", ".tsx", ".js", ".jsx", ".mjs")


def offenders(pattern, files):
    return ["%s line %d" % (name, number)
            for name, text in files
            for number, line in enumerate(text.splitlines(), 1) if re.search(pattern, line)]


def test_there_is_a_ui_to_check():
    assert len(list(source(".tsx", tests=False))) >= 5


@pytest.mark.parametrize("pattern", [r"\bparseFloat\b", r"\bparseInt\b", r"\.toFixed\(",
                                     r"NumberFormat", r"\.toLocaleString\("])
def test_trap_2_no_value_is_ever_parsed_or_reformatted(pattern):
    """`parseFloat("-490.75 ILS")` is -490.75, and the ILS is gone."""
    assert not offenders(pattern, source(*CODE)), offenders(pattern, source(*CODE))


def test_trap_3_the_ui_never_spells_out_the_provenance_prefix():
    """`source` is displayed whole. Code that knows the prefix is code that can split on it.
    Tests may assert it is on the page; components may not mention it."""
    found = offenders(r"pms:", source(*CODE, tests=False))
    assert not found, found


def test_trap_4_only_the_api_module_makes_a_request():
    found = [hit for hit in offenders(r"\bfetch\(|XMLHttpRequest|\baxios\b", source(*CODE))
             if not hit.startswith("lib/api.ts ")]
    assert not found, found


def test_trap_4_no_client_component_can_reach_the_engine():
    """A client component that imported the API module would run in the browser, where a
    re-firing effect, a focus refetch or StrictMode can turn one run into several."""
    found = [name for name, text in source(*CODE, tests=False)
             if re.match(r"""\s*["']use client["']""", text)
             and re.search(r"""(from|import)\s*\(?\s*["'][^"']*lib/api["']""", text)]
    assert not found, found


def test_trap_7_html_is_never_injected():
    found = offenders(r"dangerouslySetInnerHTML|\.innerHTML\s*=", source(*CODE))
    assert not found, found


def test_help_is_never_a_title_attribute():
    """Invisible on a touch screen, stripped by a text extraction, unreliable for a screen
    reader. The engine's surface banned it in slice 14; this one never starts."""
    # An ATTRIBUTE - `title=` followed by a quote or a brace - so prose explaining the ban is not
    # itself banned.
    found = offenders(r"""\btitle=["'{]""", source(".tsx", ".jsx"))
    assert not found, found


def test_trap_7_every_dependency_is_pinned_exactly_and_the_lockfile_is_committed():
    package = json.loads((UI / "package.json").read_text(encoding="utf-8"))
    loose = {name: version
             for group in ("dependencies", "devDependencies")
             for name, version in package.get(group, {}).items()
             if not re.fullmatch(r"\d+\.\d+\.\d+", version)}
    assert not loose, "pin exactly - a range is a version somebody else picks later: %s" % loose
    assert (UI / "package-lock.json").is_file()


def test_trap_7_the_runtime_dependency_list_stays_short():
    """Every runtime package is one an auditor has to account for. Raising this number is a
    decision, so it is a test edit somebody has to make on purpose."""
    package = json.loads((UI / "package.json").read_text(encoding="utf-8"))
    assert sorted(package["dependencies"]) == ["next", "react", "react-dom"]


def test_the_engine_is_never_imported_from_the_ui_or_the_ui_from_the_engine():
    """`ui/` can be deleted and the engine still ships, audits and demos (brief section 4)."""
    engine = UI.parent / "hotelcontrols"
    found = [p.name for p in engine.rglob("*.py")
             if re.search(r"^\s*(from|import)\s+ui\b", p.read_text(encoding="utf-8"), re.M)]
    assert not found, found
    found = offenders(r"hotelcontrols/(?!web/assets/style\.css)", source(*CODE))
    assert not found, ("the UI reads the engine's stylesheet and golden payloads, never its "
                       "code: %s" % found)


def test_no_ui_source_file_is_ignored_by_git():
    """The root `.gitignore` ignores `runs/` for the run store, and that rule swallowed the UI's
    `app/runs/[runId]/` route on its first commit. Nothing failed: the app built, the suite
    passed, and every Run button would have redirected to a 404 on any other machine.
    `--no-index`, so a file that is already staged is still judged by the rules."""
    # `next-env.d.ts` is written by Next on every build and ignored on purpose (ui/.gitignore).
    names = ["ui/" + name for name, _ in source(*CODE, ".css", ".json", ".md")
             if name != "next-env.d.ts"]
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"],
                             input="\n".join(names), cwd=UI.parent,
                             capture_output=True, text=True).stdout.split()
    assert not ignored, "git would not commit these UI files: %s" % ignored


def test_no_inline_style_attribute_which_the_csp_refuses():
    """`style-src` carries a nonce and no 'unsafe-inline', so a `style=` attribute is blocked in
    the browser and the element renders unstyled. Next's own default 404 did exactly that until
    `app/not-found.tsx` replaced it. Styling lives in the engine's stylesheet, by class."""
    found = offenders(r"""\bstyle=\{""", source(".tsx", ".jsx", tests=False))
    assert not found, found
