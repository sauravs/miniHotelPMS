# -*- coding: utf-8 -*-
"""
Slice 22 exit test, V10's second half: no model is reachable from `hotelcontrols/guest/`.

D12: the guest's request is STRUCTURED. A model reading "can I stay till 3?" could misread the
3, and a misread time prices a fee - so the decision path takes a reservation id and an HH:MM,
and nothing that could talk to a model is anywhere on it. D10 says the same for verdicts; this
says it for decisions.

The compiler's own guard (`test_compiler_grammar.py`) checks the DIRECT imports of one package.
This one follows the engine's imports TRANSITIVELY from every module in `guest/`, because a
model would not be imported by the decision module itself - it would arrive two hops away,
through some helper that seemed harmless. The proposer seam lives in `hotelcontrols.compiler`
(it takes an injected proposer from `tools/proposers/`), so the whole compiler package is out
of bounds, as is anything under `tools/` and every module that can open a connection.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE = ROOT / "hotelcontrols"
GUEST = ENGINE / "guest"

# Anything that can reach a model or the network, by top-level module.
FORBIDDEN_TOP_LEVEL = {"urllib", "http", "socket", "ssl", "asyncio", "subprocess", "smtplib",
                       "anthropic", "openai", "requests", "httpx", "tools"}
# Inside the engine: the compiler holds the proposer seam (D10), and the web layer is what an
# operator wires a proposer INTO. Neither may be reachable from a guest decision.
FORBIDDEN_ENGINE = ("hotelcontrols.compiler", "hotelcontrols.web",
                    "hotelcontrols.providers.transport", "hotelcontrols.providers.minihotel.live")


def module_name(path: pathlib.Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def path_of(name: str) -> pathlib.Path | None:
    base = ROOT.joinpath(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def imports_of(path: pathlib.Path) -> set[str]:
    """Every module this file imports, absolute, including what a package's `from . import x`
    names - so a submodule pulled in through its package is followed too."""
    package = module_name(path) if path.name == "__init__.py" else \
        module_name(path).rpartition(".")[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")
                anchor = anchor[:len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            found.add(base)
            # `from .x import y` may name a submodule y; follow it if it is one.
            found.update("%s.%s" % (base, alias.name) for alias in node.names
                         if path_of("%s.%s" % (base, alias.name)) is not None)
    return found


def reachable_from(start: pathlib.Path) -> set[str]:
    """The transitive closure of imports from every module under `start`."""
    seen: set[str] = set()
    frontier = [module_name(p) for p in sorted(start.rglob("*.py"))]
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        path = path_of(name) if name.startswith("hotelcontrols") else None
        if path is None:
            continue
        # A package's parents run first when it is imported; follow them too.
        parent = name.rpartition(".")[0]
        if parent.startswith("hotelcontrols"):
            frontier.append(parent)
        frontier.extend(imports_of(path))
    return seen


def test_the_guest_package_exists_and_imports_the_engine():
    """A guard on the guard: an empty closure would pass the test below vacuously."""
    reached = reachable_from(GUEST)
    assert "hotelcontrols.guest" in reached
    assert "hotelcontrols.evidence" in reached and "hotelcontrols.spec" in reached


def test_no_model_and_no_network_is_reachable_from_a_guest_decision():
    reached = reachable_from(GUEST)
    offenders = sorted(
        name for name in reached
        if name.split(".")[0] in FORBIDDEN_TOP_LEVEL
        or any(name == f or name.startswith(f + ".") for f in FORBIDDEN_ENGINE))
    assert not offenders, offenders


def test_the_closure_would_catch_a_model_or_a_socket_two_hops_away():
    """The rule itself, so this guard cannot rot into a test that always passes: the same walk
    from the web layer reaches the compiler (where a proposer is injected), and from the
    provider transport reaches `urllib` - both of which the test above would report."""
    web = reachable_from(ENGINE / "web")
    assert any(n == "hotelcontrols.compiler" or n.startswith("hotelcontrols.compiler.")
               for n in web)
    transport = reachable_from(ENGINE / "providers" / "transport")
    assert any(n.split(".")[0] == "urllib" for n in transport)


def test_a_planted_model_two_hops_away_is_found(tmp_path, monkeypatch):
    """A planted tree: the guest module imports a harmless-looking helper, which imports the
    compiler, which imports a model client. The walk must report both."""
    import sys
    module = sys.modules[__name__]
    engine = tmp_path / "hotelcontrols"
    for directory in ("guest", "compiler"):
        (engine / directory).mkdir(parents=True)
    (engine / "__init__.py").write_text("")
    (engine / "guest" / "__init__.py").write_text("from .decide import x\n")
    (engine / "guest" / "decide.py").write_text("from ..helpers import tidy\nx = 1\n")
    (engine / "helpers.py").write_text("from .compiler import propose\ntidy = 1\n")
    (engine / "compiler" / "__init__.py").write_text("import anthropic\npropose = 1\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    reached = reachable_from(engine / "guest")
    assert "hotelcontrols.compiler" in reached and "anthropic" in reached
