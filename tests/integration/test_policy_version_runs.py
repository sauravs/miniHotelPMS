# -*- coding: utf-8 -*-
"""
Slice 16 (G6b), end to end: every stored result says which version of the rule judged it.

A verdict without the rule that produced it is half an audit trail. Six months on, "this
reservation FAILED" invites "under which rule?" - and if the rule has been edited since, the
honest answer must be on the run, not reconstructed from git. So a run carries the rule's
`version` and the digest of its verdict-bearing content, the store keeps both, and both
surfaces say "judged under v2".

THE FRESHNESS RULE, APPLIED TO IDENTITY. A run stored before this slice cannot say which version
judged it. It reads back as "version not recorded" - never as the current version, which would
be a claim nobody established. That is asserted against a file database built with the old
schema, not against an in-memory one that never had a past.

Every test protects criterion V3 (plan-v3 §7) unless it names another.
"""
import json
import pathlib
import re
import shutil
import sqlite3
from datetime import datetime, timezone

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig, load
from hotelcontrols.spec import lock as spec_lock
from hotelcontrols.store import RunStore
from hotelcontrols.web import App, render

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"
CONTROL = "checkout_money_owed"
AS_OF = "2026-07-08T09:00"

# The `runs` table exactly as it stood on `main` before slice 16: freshness columns, no policy.
PRE_SLICE_16_RUNS = """
    CREATE TABLE runs (
        run_id TEXT PRIMARY KEY, control_id TEXT NOT NULL, control_name TEXT NOT NULL,
        natural_language TEXT NOT NULL, tenant_id TEXT NOT NULL, provider TEXT NOT NULL,
        evidence_label TEXT NOT NULL, evidence_is_synthetic INTEGER NOT NULL,
        as_of TEXT NOT NULL, created_at TEXT NOT NULL, calls INTEGER NOT NULL,
        blocked TEXT, observed_at TEXT, maximum_age TEXT);"""


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _run(control_id=CONTROL, spec_dir=None, as_of=AS_OF, created_at=None):
    tenant = TenantConfig.load("sandbox", spec_dir) if spec_dir else TenantConfig.load("sandbox")
    adapter, _source = providers.load(tenant.provider).build(tenant, "sandbox2026")
    return run(control_id, tenant, adapter, FixedClock.at(as_of, tenant.timezone),
               evidence_label="sandbox2026", spec_dir=spec_dir, created_at=created_at)


def _old_database(path: pathlib.Path) -> None:
    legacy = sqlite3.connect(path)
    legacy.executescript(PRE_SLICE_16_RUNS)
    legacy.execute(
        "INSERT INTO runs VALUES ('pre16', ?, 'Checkout With Money Owed', 'A reservation "
        "cannot be closed while the guest still owes money.', 'sandbox', 'minihotel', "
        "'sandbox2026', 0, '2026-07-08', '2026-07-08T00:00:00+03:00', 3, NULL, "
        "'2026-07-08T00:00:00+03:00', '1h')", (CONTROL,))
    legacy.commit()
    legacy.close()


# --------------------------------------------------------------------------- a run names it
class TestARunNamesItsPolicy:

    def test_a_run_carries_the_version_and_digest_of_the_rule_that_judged_it(self):
        result = _run()
        ir = load(CONTROL)
        assert result.policy_version == 2
        assert result.policy_digest == ir.digest
        assert spec_lock.read_lock(SPEC)[CONTROL] == (2, result.policy_digest), (
            "the shipped run was judged by the reviewed, locked rule")

    def test_a_blocked_run_still_names_the_rule_it_could_not_apply(self):
        """A refusal is an answer about a rule too: "v2 could not run here" is a different
        fact from "v3 could not run here"."""
        result = _run("resource_occupancy_consistency")
        assert result.is_blocked
        assert result.policy_version == 2 and result.policy_digest

    def test_both_survive_the_store_in_memory_and_on_disk(self, tmp_path):
        result = _run()
        for store in (RunStore(), RunStore(tmp_path / "runs.sqlite3")):
            with store:
                again = store.load(store.save(result))
                assert (again.policy_version, again.policy_digest) == (
                    result.policy_version, result.policy_digest)

    def test_the_json_names_it_with_two_keys(self):
        """The declared contract change: run payloads gain exactly `policy_version` and
        `policy_digest`."""
        payload = json.loads(App().handle("/api/run/%s?property=sandbox" % CONTROL).body)
        assert payload["policy_version"] == 2
        assert payload["policy_digest"] == load(CONTROL).digest

    def test_every_golden_run_names_the_locked_rule_that_judged_it(self):
        """The 88 run goldens and 11 history goldens are the API a second client is built on.
        Each names exactly the version and digest the lock holds for its control."""
        golden = SPEC.parent / "fixtures" / "api"
        locked = spec_lock.read_lock(SPEC)
        runs = sorted((golden / "run").glob("*.json")) + sorted((golden / "runs").glob("*.json"))
        assert len(runs) == 88
        for path in runs:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert (payload["policy_version"], payload["policy_digest"]) == locked[
                payload["control_id"]], path.name
        for path in sorted((golden / "history").glob("*.json")):
            history = json.loads(path.read_text(encoding="utf-8"))
            for row in history["runs"]:
                assert (row["policy_version"], row["policy_digest"]) == locked[
                    history["control_id"]], path.name

    def test_the_page_says_which_version_judged_it(self):
        body = App().handle("/run/%s?property=sandbox" % CONTROL).body
        text = text_of(body).lower()
        assert "judged under v2" in text
        assert load(CONTROL).digest.split(":")[1][:12] in text


# --------------------------------------------------------------------------- a pre-v3 run
class TestARunStoredBeforeThisSliceSaysVersionNotRecorded:
    """plan-v3 §5, slice 16, exit test 1 - against a FILE database with the old schema."""

    def test_it_reads_back_with_no_version_rather_than_the_current_one(self, tmp_path):
        path = tmp_path / "old.sqlite3"
        _old_database(path)
        with RunStore(path) as store:
            old = store.load("pre16")
            assert old is not None
            assert old.policy_version is None and old.policy_digest is None, (
                "a run from before rules were versioned cannot claim today's version")

    def test_the_json_says_null_and_the_page_says_not_recorded(self, tmp_path):
        path = tmp_path / "old.sqlite3"
        _old_database(path)
        app = App(store=RunStore(path))
        payload = json.loads(app.handle("/api/runs/pre16").body)
        assert payload["policy_version"] is None and payload["policy_digest"] is None
        old = app.store.load("pre16")
        assert "version not recorded" in text_of(render.run_page(old)).lower()

    def test_the_history_says_not_recorded_for_it_and_names_the_version_for_a_new_one(
            self, tmp_path):
        path = tmp_path / "old.sqlite3"
        _old_database(path)
        app = App(store=RunStore(path))
        app.handle("/api/run/%s?property=sandbox" % CONTROL)       # a new, versioned run
        rows = {row["run_id"]: row for row in
                json.loads(app.handle("/api/history/%s" % CONTROL).body)["runs"]}
        assert rows["pre16"]["policy_version"] is None and rows["pre16"]["policy_digest"] is None
        (new,) = [row for run_id, row in rows.items() if run_id != "pre16"]
        assert new["policy_version"] == 2 and new["policy_digest"] == load(CONTROL).digest
        text = text_of(app.handle("/history/%s" % CONTROL).body).lower()
        assert "version not recorded" in text and "judged under v2" in text

    def test_the_migrated_database_keeps_accepting_runs(self, tmp_path):
        path = tmp_path / "old.sqlite3"
        _old_database(path)
        with RunStore(path) as store:
            run_id = store.save(_run())
            assert store.load(run_id).policy_version == 2
        with RunStore(path) as reopened:                     # and migrating twice is harmless
            assert reopened.load("pre16").policy_version is None


# --------------------------------------------------------------------------- v2 beside v3
class TestTwoVersionsOfOneRuleAreDistinguishableInHistory:
    """plan-v3 §5, slice 16, exit test 3."""

    def _spec_with_v3(self, tmp_path) -> pathlib.Path:
        spec = tmp_path / "spec"
        shutil.copytree(SPEC, spec, symlinks=True, ignore=shutil.ignore_patterns("drafts"))
        return spec

    def _bump_to_v3(self, spec: pathlib.Path) -> None:
        path = spec / "ir" / ("%s.json" % CONTROL)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["assertion"]["predicates"][0]["value"] = 10
        raw["restricted_language"] = raw["restricted_language"].replace("at most 0",
                                                                        "at most 10")
        raw["version"] = 3
        path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def test_history_names_each_run_s_version_and_groups_by_it(self, tmp_path):
        spec = self._spec_with_v3(tmp_path)
        store = RunStore()
        earlier = datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc)
        later = datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)
        v2 = _run(spec_dir=spec, created_at=earlier)
        self._bump_to_v3(spec)
        v3 = _run(spec_dir=spec, created_at=later)
        assert (v2.policy_version, v3.policy_version) == (2, 3)
        assert v2.policy_digest != v3.policy_digest
        store.save(v2)
        store.save(v3)

        app = App(spec_dir=spec, store=store)
        rows = json.loads(app.handle("/api/history/%s" % CONTROL).body)["runs"]
        assert [(r["policy_version"], r["policy_digest"]) for r in rows] == [
            (3, v3.policy_digest), (2, v2.policy_digest)]

        text = text_of(app.handle("/history/%s" % CONTROL).body).lower()
        assert text.index("judged under v3") < text.index("judged under v2"), (
            "grouped, newest version first")

    def test_one_digest_with_two_versions_or_one_version_with_two_digests_is_two_groups(
            self, tmp_path):
        """A rule edited without its bump (a local edit that never passed validate_spec)
        still judges records. The digest is what tells those runs apart, so grouping is by
        version AND digest, and the page shows both."""
        spec = self._spec_with_v3(tmp_path)
        store = RunStore()
        store.save(_run(spec_dir=spec, created_at=datetime(2026, 7, 8, 9, tzinfo=timezone.utc)))
        path = spec / "ir" / ("%s.json" % CONTROL)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["assertion"]["predicates"][0]["value"] = 10
        raw["restricted_language"] = raw["restricted_language"].replace("at most 0",
                                                                        "at most 10")
        path.write_text(json.dumps(raw), encoding="utf-8")            # NOT bumped
        store.save(_run(spec_dir=spec, created_at=datetime(2026, 7, 8, 10, tzinfo=timezone.utc)))

        app = App(spec_dir=spec, store=store)
        body = app.handle("/history/%s" % CONTROL).body
        assert text_of(body).lower().count("judged under v2") == 2

    def test_a_rerun_of_the_same_question_is_always_labelled_with_the_rule_that_judged_it(
            self, tmp_path):
        """`make_run_id` is untouched (plan-v3 §6.6), so the same question at the same instant
        keeps one identity. If the rule changed in between, the row that replaces it carries
        the new rule's verdicts AND the new rule's version, together - never one rule's answers
        under the other's name."""
        spec = self._spec_with_v3(tmp_path)
        app = App(spec_dir=spec)
        first = json.loads(app.handle("/api/run/%s?property=sandbox" % CONTROL).body)
        self._bump_to_v3(spec)
        second = json.loads(app.handle("/api/run/%s?property=sandbox" % CONTROL).body)
        assert first["run_id"] == second["run_id"]
        stored = json.loads(app.handle("/api/runs/%s" % second["run_id"]).body)
        assert stored["policy_version"] == 3
        assert stored["verdicts"] == second["verdicts"]
