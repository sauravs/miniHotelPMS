# spec/drafts/ — controls composed from prose, not yet reviewed

A control that arrived through the compose front end (`/compose`) lands here as a real IR file.
It is **runnable immediately** and badged `draft · unreviewed` everywhere it appears.

It is **not** one of the shipped controls:

- `tests/e2e/test_runs.py` measures `spec/ir/` only, so a draft cannot move the criterion-1
  number in `docs/plan.md`. That number is the most carefully-kept figure in this repository and
  a machine-drafted rule does not get to change it.
- `tools/validate_spec.py` gates `spec/ir/`. A draft has passed `spec.validate` — it could not
  have run otherwise — but not the 1,080 spec checks, and not a person.

**Promoting one** is deliberate and manual:

```bash
git mv spec/drafts/ir/<control_id>.json spec/ir/<control_id>.json
python3 -m tools.validate_spec          # now gates it like any shipped control
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

`canonical_fields.json` and `ir_schema.json` are symlinks to the parent directory, so this is a
valid spec root that `available()` and `load()` read with no change to the spec layer, and the
vocabulary can never drift from the real one.
