# -*- coding: utf-8 -*-
"""
RECORD MODE - a live response, written down with the question that produced it.

The valuable half of the transport slice, and the half review finding F13 was really about.
Probing stops being a hand-run script whose output somebody copies into a directory, and starts
being reproducible: every response lands next to the exact request that produced it, in the
shape `FrozenSource` already reads, so a capture taken on Tuesday can be replayed for ever.

THE FINGERPRINT IS THE POINT
-----------------------------
Review finding F19c: v1 replayed filters against a fixture without knowing what the fixture had
actually been asked. A control querying a window the capture never covered got an empty
population, which on screen is indistinguishable from "no violations found". Issue #9 is the
same defect surviving into v2 in a narrower form. So a recorded response is worthless without
the request beside it, and this writes them together or not at all.

IT WRITES WHERE GIT IS NOT LOOKING
-----------------------------------
Decision D6 and finding F15. A live response carries guest names, email addresses, phone
numbers and free-text remarks - one of the 2026 captures holds Hebrew prose naming a guest and
describing a manager's approval - and this repository is public. So the default directory is
`fixtures/<provider>/raw/`, which `.gitignore` covers, and `tools/scrub_fixtures.py` is what
promotes a capture into the committed set. A recorder whose default wrote straight into
`fixtures/<provider>/` would put third-party personal data one `git add -A` away from being
published, and nothing in the commit would look wrong.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from ..base import Request, sorted_repr

FIXTURE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "fixtures"

# What the body is written as. Chosen from the first non-space character rather than from the
# provider's name, because this package must not know that one provider speaks XML and another
# JSON - and because a response that is neither should still be written down.
SUFFIXES = {"<": ".xml", "{": ".json", "[": ".json"}
DEFAULT_SUFFIX = ".txt"


class Recorder:
    """Writes responses and their fingerprints into a directory `FrozenSource` can read."""

    def __init__(self, directory: pathlib.Path | str, provider: str,
                 capture: str = "live", observed_at: str = "",
                 label: str = "recorded live", as_of: str = "") -> None:
        self.directory = pathlib.Path(directory)
        self.provider = provider
        self.capture = capture
        self.observed_at = observed_at
        self.label = label
        self.as_of = as_of or observed_at

    @classmethod
    def for_provider(cls, provider: str, capture: str = "live",
                     observed_at: str = "", root: pathlib.Path | str = FIXTURE_ROOT,
                     **kwargs) -> Recorder:
        """The default home: `fixtures/<provider>/raw/`, which git ignores (D6, F15)."""
        return cls(pathlib.Path(root) / provider / "raw", provider=provider, capture=capture,
                   observed_at=observed_at, **kwargs)

    # ------------------------------------------------------------------ writing
    def record(self, request: Request, body: str) -> pathlib.Path:
        """One response, its file, and its entry in the index. Written together."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / self._filename(request, body)
        path.write_text(body, encoding="utf-8")

        index = self._index()
        entry = {
            "file": path.name,
            "endpoint": request.endpoint,
            "request": _plain(request.params),
            "captures": [self.capture],
            "captured_at": self.observed_at,
        }
        # Replace rather than append when the same question is asked twice: a capture holding
        # two answers to one question cannot say which one a replay should use.
        index["responses"] = [r for r in index["responses"] if r["file"] != path.name]
        index["responses"].append(entry)
        index["responses"].sort(key=lambda r: r["file"])
        self._write_index(index)
        return path

    def _filename(self, request: Request, body: str) -> str:
        """Endpoint, plus a short digest of the PARAMETERS.

        Keyed on the request rather than on the endpoint alone because a folio is one call per
        reservation and no bulk journal endpoint exists (R1) - a capture holds five answers
        from one endpoint, and a recorder keyed on the endpoint would keep only the last.
        """
        digest = hashlib.sha256(sorted_repr(request.params).encode("utf-8")).hexdigest()[:8]
        suffix = SUFFIXES.get(body.lstrip()[:1], DEFAULT_SUFFIX)
        return "%s_%s%s" % (_safe(request.endpoint), digest, suffix)

    # ------------------------------------------------------------------ the index
    def _index(self) -> dict[str, Any]:
        path = self.directory / "index.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return {
            "provider": self.provider,
            "source": "recorded by hotelcontrols.providers.transport",
            "note": ("RAW, UNSCRUBBED responses. They carry third-party guest data and this "
                     "repository is public - run tools/scrub_fixtures.py before committing "
                     "anything derived from them (D6, F15)."),
            "captures": {},
            "responses": [],
        }

    def _write_index(self, index: dict[str, Any]) -> None:
        index.setdefault("captures", {})[self.capture] = {
            "label": self.label,
            "captured_at": self.observed_at,
            "as_of": self.as_of,
        }
        (self.directory / "index.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def __repr__(self) -> str:
        return "Recorder(%s -> %s)" % (self.capture, self.directory)


def _plain(value: Any) -> Any:
    """The request's parameters as plain JSON, so the fingerprint survives a round trip."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe(name: str) -> str:
    """A filename from an endpoint name. Endpoints arrive from a spec file, and a spec file is
    edited by people."""
    return "".join(character if character.isalnum() or character in "-_" else "-"
                   for character in name) or "response"
