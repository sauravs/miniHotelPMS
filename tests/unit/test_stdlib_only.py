# -*- coding: utf-8 -*-
"""
Success criterion 11 - the engine imports nothing outside the standard library.

This is not a stylistic preference. It is what lets the demo run on any machine with a Python
interpreter and no install step, and it is what makes "no test can reach the network"
enforceable: there is no HTTP client in the tree to reach it with.

`pytest` and `coverage` are development dependencies. They may be imported from `tests/`.
They may never be imported from `hotelcontrols/`.

The check walks the source with `ast` rather than importing it, so a module that would fail
on import is still checked - and so the test cannot be defeated by a lazy import inside a
function, which it also sees.
"""
import ast
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"

# Modules that are ours. Everything else must be in sys.stdlib_module_names.
OURS = {"hotelcontrols"}


def _imported_roots(tree: ast.AST) -> set[str]:
    """Every top-level module name this file imports, wherever the import appears."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` and `from .kernel import y` are relative: level > 0, ours.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_the_engine_imports_only_the_standard_library():
    offenders: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in sorted(_imported_roots(tree)):
            if root in OURS or root in sys.stdlib_module_names:
                continue
            offenders.append(f"{path.relative_to(ENGINE.parent)} imports {root!r}")
    assert not offenders, (
        "the engine must import only the standard library (criterion 11):\n  "
        + "\n  ".join(offenders))


def test_the_engine_contains_no_http_client():
    """Belt and braces on R8 and criterion 11.

    MiniHotel asks integrators not to query wide date ranges without agreement. The strongest
    possible guarantee that a test never hits their sandbox is that the code a test can reach
    has nothing to hit it WITH. The opt-in transport (slice 11) is the single exception and
    will be exempted here explicitly, by path, when it lands.
    """
    forbidden = {"http.client", "urllib.request", "socket", "ssl", "requests", "httpx"}
    offenders: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        # The web server is allowed to open a LISTENING socket. It never makes an outbound
        # call, which the grep test over provider identifiers backstops.
        if path.parts[-2:] in (("web", "server.py"), ("transport", "http.py")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name in forbidden or name.split(".")[0] in forbidden:
                    offenders.append(f"{path.relative_to(ENGINE.parent)} imports {name!r}")
    assert not offenders, (
        "no outbound HTTP client may exist in the engine (R8, criterion 11):\n  "
        + "\n  ".join(offenders))
