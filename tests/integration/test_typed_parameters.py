# -*- coding: utf-8 -*-
"""
Slice 21's exit test: typed hotel parameters, and "not decided" that is never read as "none".

docs/plan-v3.md §5, slice 21, and criterion V8 (§7):

  - Two properties, one IR, different parameters, correctly different verdicts, no second IR
    file (D1 §74). The IR count does not grow with the property count.
  - An undecided parameter yields UNKNOWN naming it, in a scope, an exception and an assertion,
    never EXCLUDED, never FAIL.
  - A string where a list is required, a bare number where Money is required, and a currency
    the property does not use are each refused by name.
  - And the one declared change: the sandbox's (and the demo's - the same hotel)
    `nominated_rate_codes` is `null`, because nobody can decide a vendor test property's rate
    codes (§3.2, #49). It moves no count and no outcome - only the reason on the 24 records
    whose scope it decides - and that is pinned here against the V1 baseline, so the diff the
    checkpoint showed is the diff that shipped.

HOW "NOT DECIDED" REACHES A VERDICT WITHOUT AN EVALUATOR CHANGE
---------------------------------------------------------------
`runner/run.py` hands the evaluator `tenant.settings`. An undecided parameter is declared by
the tenant but is not in that dict, so the evaluator's existing branch - "this property has not
supplied X, which this control needs" - answers. `evaluator/` and `runner/` are must-nots for
this slice; `test_the_runner_hands_the_evaluator_tenant_settings` pins the one line the
mechanism depends on.

The evidence for the two-property test is CONSTRUCTED, and labelled as such: `stay.rate_code`
is absent from every captured reservation (#49), so on captured evidence no rate-code list can
move a verdict - which the capture tests below show as well.
"""
import ast
import copy
import json
import pathlib
import shutil
import subprocess
from collections import Counter

import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import Bundle, CallBudget, gather
from hotelcontrols.kernel import FixedClock, Outcome, Value
from hotelcontrols.providers.demopms import DemoPmsAdapter, DemoSource
from hotelcontrols.providers.minihotel import FrozenSource as MiniHotelSource
from hotelcontrols.providers.minihotel import MiniHotelAdapter
from hotelcontrols.spec import Registry, TenantConfig, available, load, validate
from hotelcontrols.spec.ir import ControlIR
from hotelcontrols.spec.parameters import ParameterSchema
from hotelcontrols.spec.registry import SPEC_DIR
from tools import validate_spec

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTROL = "required_reservation_fields"            # control 15, the one shipped reader
SETTING = "nominated_rate_codes"
NOT_SUPPLIED = "this property has not supplied %r, which this control needs" % SETTING


# --------------------------------------------------------------------------- helpers
def _copy_spec(tmp_path) -> pathlib.Path:
    target = tmp_path / "spec"
    shutil.copytree(SPEC_DIR, target, symlinks=True, ignore=shutil.ignore_patterns("drafts"))
    return target


def _add_property(spec: pathlib.Path, tenant_id: str, codes) -> None:
    """A property on the same PMS as the sandbox, differing ONLY in its rate-code decision."""
    raw = json.loads((spec / "tenants" / "sandbox.json").read_text(encoding="utf-8"))
    raw["tenant_id"] = tenant_id
    raw["name"] = "A second hotel deciding %r" % (codes,)
    raw["settings"][SETTING] = codes
    (spec / "tenants" / ("%s.json" % tenant_id)).write_text(json.dumps(raw), encoding="utf-8")


def _record(record_id, status="confirmed", rate="CORP", email="guest@example.example"):
    """One reservation's evidence, constructed - see the module docstring for why."""
    return Bundle("reservation", record_id, {
        "reservation.status": Value.known(status),
        "stay.rate_code": Value.known(rate),
        "reservation.guest.email": Value.known(email),
        "reservation.guest.phone": Value.known("0500000000"),
        "reservation.guest.id_number": Value.known("000000000"),
    })


RECORDS = [
    _record("on-rate-complete"),
    _record("on-rate-missing-email", email=""),
    _record("other-rate", rate="RACK"),
    _record("cancelled", status="cancelled"),
]


def _outcomes(ir, tenant, records=RECORDS):
    # Exactly the call runner/run.py makes: the evaluator receives `tenant.settings`.
    return {v.record_id: v for v in evaluate_population(ir, records, tenant.settings)}


# --------------------------------------------------------------------------- the mechanism
def test_the_runner_hands_the_evaluator_tenant_settings():
    """The whole of "no evaluator change" rests on this line: an undecided parameter is left
    out of `tenant.settings`, and THIS is the dict the evaluator is given. If the runner ever
    passes something else, an undecided parameter could reach a predicate as a value."""
    tree = ast.parse((ROOT / "hotelcontrols" / "runner" / "run.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, "id", None) == "evaluate_population"]
    assert len(calls) == 1
    assert ast.unparse(calls[0].args[2]) == "tenant.settings"


# --------------------------------------------------------------------------- one IR, many hotels
class TestOneRuleManyProperties:
    """D1 §74 and plan-v3 §6 concern 7: parameters must not fork verdicts into IR files."""

    @pytest.fixture
    def spec(self, tmp_path):
        spec = _copy_spec(tmp_path)
        _add_property(spec, "hotel_corp", ["CORP"])
        _add_property(spec, "hotel_none", [])
        return spec

    def test_the_ir_count_does_not_grow_with_the_property_count(self, spec):
        assert len(list((spec / "tenants").glob("*.json"))) == len(
            list((SPEC_DIR / "tenants").glob("*.json"))) + 2
        assert available(spec) == available(SPEC_DIR)
        assert sorted(p.name for p in (spec / "ir").glob("*.json")) == sorted(
            p.name for p in (SPEC_DIR / "ir").glob("*.json"))

    def test_every_property_validates_against_the_same_rule(self, spec, capsys):
        assert validate_spec.main(["--spec", str(spec)]) == 0, capsys.readouterr().out

    def test_one_rule_three_decisions_three_correct_answers(self, spec):
        """The same IR object, the same four records, three properties:

            hotel_corp  ["CORP"]   on-rate records are judged: PASS, and FAIL for the missing
                                   email; the RACK record is out of scope
            hotel_none  []         decided none: every record is out of scope, honestly
            sandbox     null       not decided: whether the rule applies cannot be said, so
                                   UNKNOWN naming the parameter - and the cancelled record is
                                   still EXCLUDED, because THAT was established by evidence
        """
        ir = load(CONTROL, spec)
        corp, none, sandbox = (TenantConfig.load(t, spec)
                               for t in ("hotel_corp", "hotel_none", "sandbox"))

        assert {k: v.outcome for k, v in _outcomes(ir, corp).items()} == {
            "on-rate-complete": Outcome.PASS, "on-rate-missing-email": Outcome.FAIL,
            "other-rate": Outcome.EXCLUDED, "cancelled": Outcome.EXCLUDED}
        assert {k: v.outcome for k, v in _outcomes(ir, none).items()} == {
            "on-rate-complete": Outcome.EXCLUDED, "on-rate-missing-email": Outcome.EXCLUDED,
            "other-rate": Outcome.EXCLUDED, "cancelled": Outcome.EXCLUDED}

        undecided = _outcomes(ir, sandbox)
        assert {k: v.outcome for k, v in undecided.items()} == {
            "on-rate-complete": Outcome.UNKNOWN, "on-rate-missing-email": Outcome.UNKNOWN,
            "other-rate": Outcome.UNKNOWN, "cancelled": Outcome.EXCLUDED}
        for record_id in ("on-rate-complete", "on-rate-missing-email", "other-rate"):
            assert NOT_SUPPLIED in undecided[record_id].reason
        assert SETTING not in undecided["cancelled"].reason


# --------------------------------------------------------------------------- V8, every clause
def _with(ir, **clauses):
    raw = copy.deepcopy(ir.raw)
    raw.update(clauses)
    return raw


IN_RATE = {"field": "stay.rate_code", "operator": "in", "tenant_setting": SETTING}
NOT_IN_RATE = {"field": "stay.rate_code", "operator": "not_in", "tenant_setting": SETTING}
NOT_CANCELLED = {"field": "reservation.status", "operator": "not_equals", "value": "cancelled"}


def _placements(ir):
    """The undecided parameter in each of the three places a predicate can stand."""
    return {
        "scope": _with(ir, scope=[NOT_CANCELLED, IN_RATE]),
        # The comp-exception shape plan-v3 §5 warns about: "[] exempts nobody, so every
        # complimentary stay would FAIL". With `null` nobody is accused.
        "exception": _with(ir, scope=[NOT_CANCELLED], exceptions=[IN_RATE]),
        "assertion (all)": _with(ir, scope=[NOT_CANCELLED],
                                 assertion={"mode": "all", "predicates": [NOT_IN_RATE]}),
        "assertion (none)": _with(ir, scope=[NOT_CANCELLED],
                                  assertion={"mode": "none", "predicates": [IN_RATE]}),
        "assertion (any)": _with(ir, scope=[NOT_CANCELLED],
                                 assertion={"mode": "any", "predicates": [IN_RATE]}),
    }


@pytest.fixture(scope="module")
def sandbox():
    return TenantConfig.load("sandbox")


@pytest.fixture(scope="module")
def placements():
    return _placements(load(CONTROL))


class TestAnUndecidedParameterIsUnknownNamingIt:
    """V8: "An undecided hotel parameter is UNKNOWN naming it, never 'none'"."""

    def test_every_placement_is_a_valid_rule(self, placements, sandbox):
        registry = Registry.load()
        for where, raw in placements.items():
            assert validate(raw, registry, tenant=sandbox) == [], where

    @pytest.mark.parametrize("where", ["scope", "exception", "assertion (all)",
                                       "assertion (none)", "assertion (any)"])
    def test_unknown_naming_it_never_excluded_never_fail(self, where, placements, sandbox):
        verdicts = _outcomes(ControlIR(placements[where]), sandbox)
        for record_id in ("on-rate-complete", "on-rate-missing-email", "other-rate"):
            verdict = verdicts[record_id]
            assert verdict.outcome is Outcome.UNKNOWN, (where, record_id, verdict.reason)
            assert NOT_SUPPLIED in verdict.reason, (where, verdict.reason)

    def test_the_comp_exception_hazard_with_and_without_a_decision(self, placements):
        """Why null and [] must differ. Decided none: nobody is exempt, so the missing email
        is a FAIL, which is CORRECT for a hotel that decided it. Not decided: the same record
        cannot be accused, because whether it is exempt is a question nobody has answered."""
        ir = ControlIR(placements["exception"])
        decided_none = TenantConfig(tenant_id="t", provider="minihotel",
                                    timezone="Asia/Jerusalem", settings={SETTING: []})
        undecided = TenantConfig(tenant_id="t", provider="minihotel",
                                 timezone="Asia/Jerusalem", settings={SETTING: None})
        record = [_record("on-rate-missing-email", email="")]
        assert _outcomes(ir, decided_none, record)["on-rate-missing-email"].outcome \
            is Outcome.FAIL
        assert _outcomes(ir, undecided, record)["on-rate-missing-email"].outcome \
            is Outcome.UNKNOWN

    def test_undecided_only_ever_moves_an_answer_towards_unknown(self, placements):
        """A property over every placement, record and decision: where `null` gives anything
        but UNKNOWN, that answer was settled by evidence - every decided value gives the same
        one - and it does not cite the parameter. Not deciding can withhold an answer; it can
        never produce one."""
        decisions = ([], ["CORP"], ["RACK"], ["CORP", "RACK"])
        records = [_record("r-%s-%s-%d" % (status, rate, bool(email)), status=status,
                           rate=rate, email=email)
                   for status in ("confirmed", "checked_in", "cancelled")
                   for rate in ("CORP", "RACK", "BB")
                   for email in ("guest@example.example", "")]
        checked = Counter()
        for where, raw in placements.items():
            ir = ControlIR(raw)
            undecided = _outcomes(ir, TenantConfig(
                tenant_id="t", provider="minihotel", timezone="Asia/Jerusalem",
                settings={SETTING: None}), records)
            decided = [_outcomes(ir, TenantConfig(
                tenant_id="t", provider="minihotel", timezone="Asia/Jerusalem",
                settings={SETTING: codes}), records) for codes in decisions]
            for record in records:
                verdict = undecided[record.record_id]
                checked[verdict.outcome] += 1
                if verdict.outcome is Outcome.UNKNOWN:
                    assert NOT_SUPPLIED in verdict.reason
                    continue
                assert {d[record.record_id].outcome for d in decided} == {verdict.outcome}
                assert SETTING not in verdict.reason
        # Not vacuous: both branches were exercised.
        assert checked[Outcome.UNKNOWN] and checked[Outcome.EXCLUDED]


# --------------------------------------------------------------------------- refused by name
class TestValidateSpecRefusesAWrongValueByName:
    """The third bullet of the exit test, through the tool an onboarding person runs."""

    @pytest.fixture
    def spec(self, tmp_path):
        spec = _copy_spec(tmp_path)
        # A money parameter exists only in this copy: no shipped control reads one until
        # slice 22's template, and the refusal is a property of the type, not of a control.
        schema = json.loads((spec / "parameters.json").read_text(encoding="utf-8"))
        schema["parameters"]["late_fee"] = {"type": "money", "required": False,
                                            "description": "a test-only money parameter"}
        (spec / "parameters.json").write_text(json.dumps(schema), encoding="utf-8")
        return spec

    def _state(self, spec, name, value):
        path = spec / "tenants" / "sandbox.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["settings"][name] = value
        path.write_text(json.dumps(raw), encoding="utf-8")

    def _validate(self, spec, capsys):
        code = validate_spec.main(["--spec", str(spec)])
        return code, capsys.readouterr().out

    def test_the_copy_with_a_money_parameter_still_validates(self, spec, capsys):
        code, out = self._validate(spec, capsys)
        assert code == 0, out

    def test_a_correctly_typed_fee_validates(self, spec, capsys):
        self._state(spec, "late_fee", {"amount": "25.00", "currency": "USD"})
        code, out = self._validate(spec, capsys)
        assert code == 0, out

    @pytest.mark.parametrize("name, value, named", [
        (SETTING, "Tourist-BB", ["nominated_rate_codes", "'Tourist-BB'"]),
        ("late_fee", 25, ["late_fee", "currency"]),
        ("late_fee", {"amount": "25.00", "currency": "GBP"}, ["late_fee", "GBP"]),
    ], ids=["a string where a list is required", "a bare number where Money is required",
            "a currency the property does not use"])
    def test_each_is_refused_naming_the_parameter(self, spec, capsys, name, value, named):
        self._state(spec, name, value)
        code, out = self._validate(spec, capsys)
        assert code != 0
        for word in named:
            assert word in out, out


# --------------------------------------------------------------------------- on the captures
class TestOnTheCaptures:
    """The declared change, measured on real records through both providers."""

    PROVIDERS = {"sandbox": (MiniHotelAdapter, MiniHotelSource, "sandbox2026"),
                 "demo": (DemoPmsAdapter, DemoSource, "demo2026")}

    def _verdicts(self, tenant_id, tenant=None):
        adapter_class, source_class, capture = self.PROVIDERS[tenant_id]
        tenant = tenant or TenantConfig.load(tenant_id)
        adapter = adapter_class(tenant, source_class(capture))
        ir = load(CONTROL)
        evidence = gather(ir, adapter, tenant, FixedClock.at("2026-07-08T09:00",
                                                             tenant.timezone), CallBudget(400))
        return evaluate_population(ir, evidence.bundles, tenant.settings)

    @pytest.mark.parametrize("tenant_id", ["sandbox", "demo"])
    def test_undecided_rate_codes_name_the_parameter_on_24_records(self, tenant_id):
        verdicts = self._verdicts(tenant_id)
        assert Counter(v.outcome for v in verdicts) == {
            Outcome.UNKNOWN: 37, Outcome.EXCLUDED: 71}
        assert sum(NOT_SUPPLIED in v.reason for v in verdicts) == 24

    @pytest.mark.parametrize("tenant_id", ["sandbox", "demo"])
    def test_a_decided_list_would_move_nothing_either_because_rate_codes_are_absent(
            self, tenant_id):
        """#49, kept true: a list alone changes no count, because `stay.rate_code` is absent
        from every capture. Deciding only changes WHICH gap the 24 records name. This is why
        nobody should "fix" the sandbox by supplying a list - it would invent a hotel's policy
        and move nothing."""
        raw = json.loads((SPEC_DIR / "tenants" / ("%s.json" % tenant_id)).read_text(
            encoding="utf-8"))
        raw["settings"][SETTING] = ["Tourist-BB"]
        decided = TenantConfig.from_dict(raw, parameters=ParameterSchema.load())
        verdicts = self._verdicts(tenant_id, decided)
        assert Counter(v.outcome for v in verdicts) == {
            Outcome.UNKNOWN: 37, Outcome.EXCLUDED: 71}
        assert sum("stay.rate_code is unknown" in v.reason for v in verdicts) == 24
        assert not any(NOT_SUPPLIED in v.reason for v in verdicts)


# --------------------------------------------------------------------------- the declared diff
BASELINE = "7f384c4"
DECLARED_GOLDENS = (
    "run/required_reservation_fields.sandbox.sandbox2026.json",
    "run/required_reservation_fields.demo.demo2026.json",
    "runs/c7be275548a09e40.json",                  # the sandbox run, re-read from the store
    "runs/4270ab5ef6c1068c.json",                  # the demo run, re-read from the store
)
RATE_CODE_ABSENT = ("whether this control applies could not be established: stay.rate_code is "
                    "unknown (stay.rate_code is absent from the provider response)")
NOW_NAMED = "whether this control applies could not be established: " + NOT_SUPPLIED


def _baseline(name: str) -> dict:
    try:
        shown = subprocess.run(("git", "show", "%s:fixtures/api/%s" % (BASELINE, name)),
                               cwd=ROOT, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as exc:
        pytest.fail("cannot read %s at %s (%s). In CI the checkout needs fetch-depth: 0."
                    % (name, BASELINE, exc.stderr.strip()))
    return json.loads(shown)


@pytest.mark.parametrize("name", DECLARED_GOLDENS)
def test_the_declared_change_is_exactly_what_the_checkpoint_showed(name):
    """V1 lets a declared golden differ; this says HOW it may differ. Same counts, same headline,
    same outcome and evidence for every record - and the only reasons that changed are the 24
    that said the rate code was absent and now name the undecided parameter."""
    then = _baseline(name)
    now = json.loads((ROOT / "fixtures" / "api" / name).read_text(encoding="utf-8"))

    assert now["counts"] == then["counts"] == {
        "PASS": 0, "FAIL": 0, "UNKNOWN": 37, "EXCLUDED": 71, "total": 108}
    assert now["coverage"]["headline"] == then["coverage"]["headline"]
    assert now["coverage"]["concluded"] is then["coverage"]["concluded"] is False
    assert [(v["record_id"], v["outcome"], v["evidence"]) for v in now["verdicts"]] == [
        (v["record_id"], v["outcome"], v["evidence"]) for v in then["verdicts"]]

    moved = [(a["reason"], b["reason"]) for a, b in zip(then["verdicts"], now["verdicts"])
             if a["reason"] != b["reason"]]
    assert moved == [(RATE_CODE_ABSENT, NOW_NAMED)] * 24
    assert [r for r in then["coverage"]["reasons"] if r["reason"] == RATE_CODE_ABSENT] == [
        {"reason": RATE_CODE_ABSENT, "records": 24}]
    assert [r for r in now["coverage"]["reasons"] if r["reason"] == NOW_NAMED] == [
        {"reason": NOW_NAMED, "records": 24}]
    assert len(now["coverage"]["reasons"]) == len(then["coverage"]["reasons"])
