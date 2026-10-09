# -*- coding: utf-8 -*-
"""
Write spec/ir.lock.json - each reviewed control's version and the digest of what it says.

    python3 -m tools.lock_spec               regenerate the lock
    python3 -m tools.lock_spec --check       exit 1 if the lock is not current
    python3 -m tools.lock_spec --spec DIR    against another spec root (tests use a copy)

Run it AFTER bumping a control's `version`, never instead of bumping it. It refuses to record a
rule whose content changed under an unchanged version, because that would write the edited rule
down under the reviewed rule's number - the lie the lock exists to stop (slice 16, G6b). The
suite checks the shipped lock is current, so a bump that was never locked cannot merge.

Generated, never edited, like fixtures/demopms/ and fixtures/api/.
"""
from __future__ import annotations

import pathlib
import sys

from hotelcontrols.spec import SpecError
from hotelcontrols.spec import lock as spec_lock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    spec = pathlib.Path(argv[argv.index("--spec") + 1]) if "--spec" in argv else SPEC
    target = spec / spec_lock.LOCK_FILE

    try:
        content = spec_lock.render_lock(spec_lock.build_lock(spec))
    except SpecError as exc:
        print("REFUSED - %s" % exc)
        return 1

    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if current == content:
        print("%s %s - current" % ("checked" if check else "unchanged", _shown(target)))
        return 0
    if check:
        pending = spec_lock.unlocked(spec)
        print("STALE - %s does not match the rules on disk%s. Run: python3 -m tools.lock_spec"
              % (_shown(target), " (not yet locked: %s)" % ", ".join(pending) if pending else ""))
        return 1
    target.write_text(content, encoding="utf-8")
    print("wrote %s" % _shown(target))
    return 0


def _shown(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
