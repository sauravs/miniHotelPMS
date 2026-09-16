# -*- coding: utf-8 -*-
"""
THE LOCAL PROPOSER - a model on this machine, free forever, no key, no account.

    OLLAMA_HOST=http://127.0.0.1:11434  OLLAMA_MODEL=qwen2.5:7b

The default backend, and the reason the compose front end can exist at all under a "must be
free to run" requirement. It speaks Ollama's HTTP API with `urllib.request` from the standard
library, so it adds no dependency to this repository - not even an optional one.

It is also the backend that fits this project's temperament. Everything else here runs offline
against captured evidence; a compose window that needed somebody's paid API to draft a sentence
would be the only part of the system that could not be demonstrated on a train.

WHY IT IS STILL BEHIND BOTH LOCKS
----------------------------------
`localhost` is a socket. "No test in this repository reaches a model or a network" is stated
without an exception for loopback, and a rule with one exception acquires a second. So this
refuses to arm without `HOTELCONTROLS_COMPOSE=1` and refuses outright inside a test process -
see `base.assert_armed`. Tests wire `StubProposer`.

WHY TEMPERATURE IS ZERO
------------------------
The same sentence should compile to the same rule twice. `GrammarCompiler` is stateless
precisely so a rule cannot depend on its history, and a sampling proposer in front of it would
put that back - not in the compiler, but in the thing a person sees and approves. A translation
task has one right answer anyway.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

from hotelcontrols.compiler.sentences import Turn
from hotelcontrols.spec.registry import SPEC_DIR

from .base import assert_armed, system_prompt, user_prompt

DEFAULT_HOST = "http://127.0.0.1:11434"
# A 7B instruct model is enough for a template rewrite and runs on a laptop. Named as a default
# rather than a requirement: anything Ollama serves can be pointed at with OLLAMA_MODEL.
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_TIMEOUT = 120.0


class LocalProposer:
    """Ollama, over the standard library. Free, offline, zero dependencies."""

    name = "local"

    __slots__ = ("host", "model", "timeout", "_spec_dir", "_prompt")

    def __init__(self, host: str | None = None, model: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 spec_dir: pathlib.Path | str = SPEC_DIR) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self._spec_dir = spec_dir
        # Built once. It is a few thousand tokens of vocabulary and examples, it is identical on
        # every turn, and regenerating it per request would re-read four files to get the same
        # string. `serve.py` is long-lived, so this is built at startup and reused.
        self._prompt = system_prompt(spec_dir)

    def __repr__(self) -> str:
        return "LocalProposer(%s, model=%r)" % (self.host, self.model)

    # ------------------------------------------------------------------ the request
    def propose(self, prose: str, history: tuple[Turn, ...] = ()) -> str:
        """One sentence, or one question. Raises rather than returning a plausible default."""
        assert_armed("the local proposer")

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": user_prompt(prose, history)},
            ],
            "stream": False,
            # Deterministic, and short: the answer is one sentence. A large ceiling here just
            # gives a chatty model room to explain itself, which `split_reply` would then have
            # to discard.
            "options": {"temperature": 0, "num_predict": 300},
        }).encode("utf-8")

        request = urllib.request.Request(                        # noqa: S310 - see assert_armed
            "%s/api/chat" % self.host, data=payload, method="POST",
            headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(self._explain_http(exc)) from exc
        except urllib.error.URLError as exc:
            # The overwhelmingly common case on a fresh machine, and the one worth a real
            # sentence: nothing is listening, because nothing is installed.
            raise RuntimeError(
                "no model is answering at %s (%s). Start one with:\n"
                "    brew install ollama && ollama pull %s && ollama serve\n"
                "or point OLLAMA_HOST at a host that is already serving, or switch backend "
                "with --llm claude." % (self.host, exc.reason, self.model)) from exc

        message = body.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(
                "%s answered with no content. The full reply was: %s"
                % (self.model, json.dumps(body)[:400]))
        return content

    def _explain_http(self, exc: urllib.error.HTTPError) -> str:
        """Turn a status code into something a person can act on."""
        if exc.code == 404:
            return ("%s is not pulled on this host. Run `ollama pull %s`, or set OLLAMA_MODEL "
                    "to one of the models `ollama list` shows." % (self.model, self.model))
        return "the local model host refused the request: HTTP %s %s" % (exc.code, exc.reason)
