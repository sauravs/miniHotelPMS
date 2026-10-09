# spec/drafts/ — controls composed from prose, not yet reviewed

A control that arrived through the compose front end (`/compose`) lands here as a real IR file,
under the property it was composed for: `spec/drafts/<property>/ir/<control_id>.json`. It is
**runnable immediately for that property**, and badged `draft · unreviewed` everywhere it appears.

Drafts are per property since v3 slice 17. Two hotels composing `late_checkout_policy` file two
drafts, not one overwriting the other, and one property never lists, reads or runs another's.
Reviewed controls in `spec/ir/` stay one shared library.

It is **not** one of the shipped controls:

- `tests/e2e/test_runs.py` measures `spec/ir/` only, so a draft cannot move the criterion-1
  number in `docs/plan.md`. That number is the most carefully-kept figure in this repository and
  a machine-drafted rule does not get to change it.
- `tools/validate_spec.py` gates `spec/ir/`. A draft has passed `spec.validate` — it could not
  have run otherwise — but not the full spec checks, not the spec lock, and not a person.

**Promoting one** is deliberate and manual:

```bash
git mv spec/drafts/<property>/ir/<control_id>.json spec/ir/<control_id>.json
python3 -m tools.lock_spec              # record its version and digest in spec/ir.lock.json
python3 -m tools.validate_spec          # now gates it like any shipped control
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

The lock step is since v3 slice 16. A promoted control is a reviewed rule, so its version is
recorded beside the digest of what it says. An edit after that needs a version bump, or
`validate_spec` refuses it. Skip the step and the suite's lock check fails, naming this command.

`canonical_fields.json` and `ir_schema.json` are symlinks to the parent directory, so the
vocabulary can never drift from the real one. Each `spec/drafts/<property>/` is a spec root that
`available()` and `load()` read with no change to the spec layer. `spec/drafts/ir/` is where drafts
were filed before slice 17, and the app no longer reads it.
