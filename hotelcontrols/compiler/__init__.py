# -*- coding: utf-8 -*-
"""
L0 · COMPILER - a sentence becomes a rule, and only ever a rule.

Stage 1 of the six `control_rule_architecture.docx` section 17 specifies, and the one v1 did
not have (finding F6). It runs BESIDE the stack rather than inside it: it produces a spec
artifact that L2 validates, and nothing at runtime depends on it.

Three front ends, one gate.

    GrammarCompiler   restricted English, deterministic, offline, no model. What CI runs and
                      what every test asserts against.
    normalise()       PROSE, via an injected sentence proposer, which rewrites it into
                      restricted English and then hands it to the grammar above. Decision D10.
                      The intermediate is a SENTENCE a person can read and correct, so nothing
                      new decides what a rule means.
    ModelCompiler     the seam for a proposal that is already IR. Decision D9: built and
                      exercised against a stub.

None of the three finds a model, holds a key, or makes a request - a proposer is always handed
in, and every model client in this repository lives under `tools/`, outside the engine. That is
what keeps criterion 11 true and keeps `tests/unit/test_compiler_grammar.py`'s network guard
passing unchanged.

Both end in `grammar.finish`, which calls `spec.validate` - the same function that has policed
hand-written IR files since slice 1. A model's proposal is rejected exactly as a person's is,
by the same code, naming the same missing vocabulary. A second validation path, however small,
would be a second standard, and the weaker one would be the one a model's output travelled
down.

**Neither emits anything executable.** Section 17 is explicit about why, and the gate that makes
it safe already works: fed the doc's own example - "All VIP arrivals should have an assigned
room that is clean by 2 PM" - it answers with the two canonical fields that do not exist rather
than producing a rule that runs and quietly answers about nothing.
"""
from .grammar import GrammarCompiler, compile_sentence, finish
from .model import ModelCompiler, Proposer
from .problems import (DEPLOYMENT_KEYS, LOGIC_KEYS, OPTIONAL_DEPLOYMENT_KEYS, SENTENCE_KEYS,
                       Compilation, deployment_of)
from .sentences import Normalisation, SentenceProposer, Turn, normalise, split_reply

__all__ = [
    "Compilation",
    "DEPLOYMENT_KEYS",
    "GrammarCompiler",
    "LOGIC_KEYS",
    "ModelCompiler",
    "Normalisation",
    "OPTIONAL_DEPLOYMENT_KEYS",
    "Proposer",
    "SENTENCE_KEYS",
    "SentenceProposer",
    "Turn",
    "compile_sentence",
    "deployment_of",
    "finish",
    "normalise",
    "split_reply",
]
