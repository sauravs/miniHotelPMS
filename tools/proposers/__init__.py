# -*- coding: utf-8 -*-
"""
EVERY BACKEND THAT CAN DRAFT A SENTENCE, AND THE ONE LINE THAT PICKS ONE.

    build("local")   Ollama on this machine. FREE, offline, no dependency.   <- default
    build("claude")  the hosted API. Paid, opt-in, needs `anthropic`.
    build("stub")    fixed replies. No model at all. What every test wires.
    build("off")     None - the compose front end stays inert.

All four satisfy one protocol - `hotelcontrols.compiler.sentences.SentenceProposer`, a single
method returning text - which is why choosing between them is a string and not a code change.
The same shape that made a second PMS an adapter rather than a rewrite.

THIS PACKAGE IS OUTSIDE THE ENGINE, AND THAT IS THE WHOLE DESIGN
-----------------------------------------------------------------
`hotelcontrols/` imports only the standard library and contains no outbound HTTP client
(criterion 11, asserted over the AST in two places). A model client is precisely what would
break that, so it lives here and is INJECTED into the app at startup by `tools/serve.py`. The
engine-side seam takes a proposer and never goes looking for one.

Nothing under `hotelcontrols/` imports this package. If that ever changes, both guard tests
fail, which is the intended alarm.
"""
from __future__ import annotations

import pathlib

from hotelcontrols.compiler.sentences import SentenceProposer
from hotelcontrols.spec.registry import SPEC_DIR

from .base import ENABLE, ProposerDisabled, assert_armed, is_enabled, system_prompt, under_test
from .stub import ExplodingProposer, StubProposer

# Ordered as they should appear in a chooser: free first, then paid, then the one that needs
# nothing at all.
NAMES = ("local", "claude", "stub", "off")
DEFAULT = "local"


def build(name: str = DEFAULT,
          spec_dir: pathlib.Path | str = SPEC_DIR) -> SentenceProposer | None:
    """One backend by name, or None for "the compose front end is switched off".

    The live backends are imported lazily so that asking for the stub never touches a module
    that could import `anthropic` - which may not be installed, and should not have to be.
    """
    chosen = (name or DEFAULT).strip().lower()

    if chosen in ("off", "none", ""):
        return None
    if chosen == "stub":
        return StubProposer()
    if chosen == "local":
        from .local import LocalProposer
        return LocalProposer(spec_dir=spec_dir)
    if chosen == "claude":
        from .anthropic_api import AnthropicProposer
        return AnthropicProposer(spec_dir=spec_dir)

    raise ValueError("no proposer called %r. Available: %s" % (name, ", ".join(NAMES)))


__all__ = [
    "DEFAULT",
    "ENABLE",
    "ExplodingProposer",
    "NAMES",
    "ProposerDisabled",
    "StubProposer",
    "assert_armed",
    "build",
    "is_enabled",
    "system_prompt",
    "under_test",
]
