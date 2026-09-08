# -*- coding: utf-8 -*-
"""
Slice 8 gate: no wall clock is read anywhere in the engine except inside the clock module.

Finding F11, made mechanical - and the reason it needs a test rather than a convention is that
every violation of it LOOKS FINE. `datetime.now()` returns a perfectly good instant. It is just
the wrong one: a machine's opinion about what time it is at a hotel.

At 22:30 UTC on 7 July it is already 8 July in Jerusalem, so a control asking "who checked out
today" gets a DIFFERENT POPULATION depending on which clock answers - and a run executed from a
laptop in another timezone would silently evaluate a different question. Silently is the whole
problem: nothing raises, nothing is logged, and the verdicts are simply about the wrong day.

The second reason is reproducibility. A stored run is defensible six months later only if the
same evidence yields the same verdict, and a function reading a wall clock is a function whose
output depends on when you called it. `FixedClock` is what makes an audit trail an audit trail
rather than an anecdote - and it can only do that if there is nowhere else for time to come in.

Prose is exempt on purpose. `clock.py` and `run.py` both explain at length WHY `datetime.now()`
must not be called, and a check that cannot tell an explanation from a call would push us to
delete the best explanations in the repository to make a test pass.
"""
import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"

# The one module allowed to ask the operating system what time it is. Everything else receives
# a Clock.
ALLOWED = "kernel/clock.py"

# How a wall clock gets read in Python, as (object, attribute) pairs. Named rather than matched
# loosely, so `Decimal.now` or a variable called `today` cannot trip it.
WALL_CLOCK_CALLS = {
    ("datetime", "now"), ("datetime", "today"), ("datetime", "utcnow"),
    ("date", "today"), ("time", "time"), ("time", "monotonic"),
}


def engine_files():
    for path in sorted(ENGINE.rglob("*.py")):
        relative = path.relative_to(ENGINE).as_posix()
        if relative != ALLOWED:
            yield relative, path


def wall_clock_calls(tree):
    """Every `X.now()`-shaped call in one module, as (object, attribute, line)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        holder = node.func.value
        name = holder.id if isinstance(holder, ast.Name) else getattr(holder, "attr", None)
        if (name, node.func.attr) in WALL_CLOCK_CALLS:
            yield name, node.func.attr, node.lineno


def test_the_clock_module_itself_does_read_the_wall_clock():
    """A guard on the test below. If nothing anywhere reads a real clock, the engine cannot
    tell the time at all and this suite would be passing vacuously."""
    tree = ast.parse((ENGINE / ALLOWED).read_text(encoding="utf-8"))
    assert list(wall_clock_calls(tree)), (
        "%s is the one place allowed to read a wall clock, and it appears not to" % ALLOWED)


def test_there_are_files_to_check():
    assert len(list(engine_files())) >= 20


def test_no_module_outside_the_clock_reads_a_wall_clock():
    offenders = []
    for relative, path in engine_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for holder, attribute, line in wall_clock_calls(tree):
            offenders.append("%s line %d: %s.%s()" % (relative, line, holder, attribute))
    assert not offenders, (
        "time must arrive through an injected Clock, in the PROPERTY's timezone (F11). A "
        "machine's clock decides which records a control even looks at, and gets it wrong "
        "without saying anything: %s" % offenders)


@pytest.mark.parametrize("module", ["runner/run.py", "runner/scheduling.py"])
def test_the_modules_that_most_want_a_wall_clock_do_not_have_one(module):
    """Named explicitly because these two are where it would be most natural to reach for one -
    a run's own timestamp, and a scheduler's idea of "now" - and where it would do the most
    damage. `run()` did call `datetime.now()` until this slice."""
    tree = ast.parse((ENGINE / module).read_text(encoding="utf-8"))
    assert not list(wall_clock_calls(tree))
