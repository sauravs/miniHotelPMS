# -*- coding: utf-8 -*-
"""
THE HOSTED PROPOSER - opt-in, paid, and better at the translation than a 7B model.

    ANTHROPIC_API_KEY=...   ANTHROPIC_MODEL=claude-haiku-4-5   (the default)

NOT the default backend, because running this system must stay free (that was a requirement,
not a preference). It exists because the local backend's quality depends on whatever the
operator managed to install, and there should be one backend whose behaviour we can reason
about when a sentence comes back wrong.

WHAT IT COSTS, SO NOBODY IS SURPRISED
--------------------------------------
The request is the generated system prompt - the canonical vocabulary, the grammar's keyword
tables, six worked examples, measured at ~7,900 characters or roughly 2,000 tokens - plus one
short sentence, returning one short sentence. On `claude-haiku-4-5` that is around a quarter of
a cent per attempt, and well under that once the system prompt is being served from cache,
which it is on every turn after the first.

The vocabulary is marked `cache_control` for exactly that reason: it is byte-identical on every
request in a session and sits first in render order, so it is the ideal cached prefix. The
volatile half - the prose, and any refusal being fed back - goes in the user message, after it.

`anthropic` is an OPTIONAL dependency, declared in `requirements-llm.txt` and imported inside
`__init__` rather than at module scope. The package must be importable with nothing installed,
because `tools/proposers/__init__.py` offers every backend and the operator picks one at
startup. Nothing under `hotelcontrols/` imports this file, which is what keeps criterion 11
true and both AST guards green.
"""
from __future__ import annotations

import os
import pathlib

from hotelcontrols.compiler.sentences import Turn
from hotelcontrols.spec.registry import SPEC_DIR

from .base import assert_armed, system_prompt, user_prompt

# The model named in the approved plan. Overridable, and `claude-opus-5` is the upgrade if a
# sentence comes back wrong often enough to be worth five times the price.
DEFAULT_MODEL = "claude-haiku-4-5"

# The answer is one sentence. This is a deliberately short output, not a lowballed ceiling -
# a larger one only gives a model room to explain itself, which `split_reply` then discards.
MAX_TOKENS = 512


class AnthropicProposer:
    """One `messages.create` per turn, with the vocabulary cached."""

    name = "claude"

    __slots__ = ("model", "_client", "_prompt")

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 spec_dir: pathlib.Path | str = SPEC_DIR) -> None:
        try:
            import anthropic
        except ImportError as exc:                       # pragma: no cover - env-dependent
            raise RuntimeError(
                "the hosted proposer needs the `anthropic` package, which this engine does "
                "not depend on. Install it with:\n"
                "    pip install -r requirements-llm.txt\n"
                "or use the free local backend with --llm local.") from exc

        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        # No default credential, ever - a missing one must fail loudly rather than silently
        # becoming an anonymous request. The SDK's own resolution order (env var, then an
        # `ant auth login` profile) is left alone; passing None lets it do its job.
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._prompt = system_prompt(spec_dir)

    def __repr__(self) -> str:
        return "AnthropicProposer(model=%r)" % self.model

    def propose(self, prose: str, history: tuple[Turn, ...] = ()) -> str:
        """One sentence, or one question. Raises rather than returning a plausible default."""
        assert_armed("the hosted proposer")
        import anthropic

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                # The stable prefix, cached. Everything volatile is in the user message below.
                system=[{"type": "text", "text": self._prompt,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt(prose, history)}],
            )
        except anthropic.AuthenticationError as exc:
            raise RuntimeError(
                "the model host rejected the credentials. ANTHROPIC_API_KEY comes from the "
                "environment with no default (decision D6), so an unset one fails here rather "
                "than becoming an anonymous request.") from exc
        except anthropic.RateLimitError as exc:
            after = exc.response.headers.get("retry-after", "60") if exc.response else "60"
            raise RuntimeError("rate limited by the model host; retry after %ss" % after) from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(
                "the model host returned HTTP %s: %s" % (exc.status_code, exc.message)) from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError("could not reach the model host: %s" % exc) from exc

        # Checked BEFORE reading content, because a declined request still returns HTTP 200 and
        # its content blocks are not an answer.
        if response.stop_reason == "refusal":
            raise RuntimeError(
                "the model declined to answer this request%s. Rephrase the rule."
                % (" (%s)" % response.stop_details.category
                   if response.stop_details is not None else ""))

        text = "\n".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise RuntimeError("%s answered with no text (stop_reason: %s)"
                               % (self.model, response.stop_reason))
        return text
