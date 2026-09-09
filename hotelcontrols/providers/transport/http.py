# -*- coding: utf-8 -*-
"""
THE LIVE TRANSPORT - the only code in this engine that can open an outbound socket, and it is
off.

Review finding F13. v1 had no HTTP client by design, which was the right safety property and
also meant there was no path from the demo to production: the most operationally risky component
in the system was the one nobody had written or tested. This is that component, built with the
safety property intact.

TWO LOCKS, AND THE SECOND ONE IS THE REAL ONE
----------------------------------------------
    1. `HOTELCONTROLS_LIVE` is unset by default, so nothing dials out by accident.
    2. It refuses to arm at all while a test runner is loaded in the process.

Lock 1 alone would be a lock whose key is one line of `monkeypatch.setenv` away, and criterion
11 says NO TEST CAN REACH THE NETWORK. So the second lock is the process itself. Everything
below is exercised with an injected dialer standing where the socket would be - pacing, retry,
give-up, recording, credentials - and `tests/unit/test_transport.py` sets the variable and is
still refused, which is as close to proving a negative as this gets.

WHAT THIS FILE KNOWS, AND WHAT IT MUST NEVER KNOW
--------------------------------------------------
It knows how to wait, how to retry, how to give up, and how to write a response down. It knows
nothing about any PMS: not an endpoint, not a wire format, not a vendor name. `providers/
transport/` sits outside every adapter's directory, so the canonical-boundary grep polices it
exactly as it polices the evaluator. The request-to-HTTP encoding is the ADAPTER's, handed in
as a callable, and the credentials' environment variables are built from a provider name that
arrives as data.

A GIVE-UP IS AN EVIDENCE GAP, NOT A CRASH
------------------------------------------
`ResponseUnavailable` is a `ProviderError`, and the evidence layer turns one into an UNKNOWN
carrying a reason. That is the difference between a control that reports "the folio call failed
after three attempts" and a run that dies with a traceback - and it is why the retry policy
lives here rather than in a caller who would have to remember it.

A refusal to arm is NOT retried. A disabled transport is a configuration mistake, and turning a
loud instant failure into a slow confusing one helps nobody.
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from ...kernel import Clock
from ..base import Request, ResponseUnavailable
from .ratelimit import TokenBucket

# The one variable that arms the transport. Named rather than assembled, so a grep for it in
# this repository finds every place the decision is made.
ENABLE = "HOTELCONTROLS_LIVE"
TRUTHY = ("1", "true", "yes", "on")

# What a test runner looks like from inside the process it is running. `unittest` is included
# because it is what a runner other than pytest would bring, and nothing in a stdlib-only
# engine imports it in production.
TEST_RUNNERS = ("pytest", "_pytest", "unittest", "nose")

# Deliberately conservative, and both are ceilings rather than targets. A run's real ceiling is
# the CallBudget it already carries (R1) - this only decides how fast the calls it is allowed
# to make may go out.
DEFAULT_CAPACITY = 3
DEFAULT_INTERVAL = timedelta(seconds=1)
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = timedelta(seconds=2)
DEFAULT_TIMEOUT = 60.0


class TransportDisabled(RuntimeError):
    """The live transport was asked to make a call and is not armed.

    A `RuntimeError` and deliberately NOT a `ProviderError`. A ProviderError becomes an UNKNOWN
    with a reason - the right answer for a call that failed - and a transport nobody enabled is
    not an evidence gap about a hotel. It is a mistake about this machine, and it must be loud.
    """


class MissingCredential(RuntimeError):
    """A credential is not in the environment. There is no default and there will not be one.

    Finding F15: v1 hard-coded `USER, PWD, HOTEL = "Test", "3657488", "sandbox"` in a file about
    to be pushed to a public repository. They were the vendor's own published sandbox
    credentials, which made that defensible and made the habit dangerous - the same line
    survives the move to production credentials.
    """


@dataclass(frozen=True, slots=True)
class HttpCall:
    """One outbound request, fully composed by whoever knows the wire format."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


@dataclass(frozen=True, slots=True)
class Credentials:
    """One account on one property. From the environment, with no default, ever."""

    user: str
    password: str
    hotel: str
    base_url: str

    @classmethod
    def from_environment(cls, provider: str) -> Credentials:
        """`HOTELCONTROLS_<PROVIDER>_{USER,PASSWORD,HOTEL,BASE_URL}`.

        The provider name arrives as data - from a tenant file, by way of the registry that
        discovers adapters by import - so no vendor is spelled out in this file.
        """
        prefix = "HOTELCONTROLS_%s_" % provider.upper().replace("-", "_")
        values = {}
        for field_name, suffix in (("user", "USER"), ("password", "PASSWORD"),
                                   ("hotel", "HOTEL"), ("base_url", "BASE_URL")):
            value = os.environ.get(prefix + suffix, "")
            if not value.strip():
                # An empty variable counts as missing. `export ...PASSWORD=` is the commonest
                # way to have a credential and not have it, and starting with three of four
                # would fail at the vendor's authentication layer - where the error a reader
                # sees is about the vendor rather than about this machine.
                raise MissingCredential(
                    "%s is not set. Credentials come from the environment with no default, so "
                    "a missing one fails here rather than becoming a checked-in sandbox "
                    "account (F15). See .env.example." % (prefix + suffix))
            values[field_name] = value.strip()
        return cls(**values)

    def __repr__(self) -> str:
        """Everything but the password. Credentials get printed by accident - in a traceback,
        a log line, a debugger - and this is the field that must not be there when they are."""
        return "Credentials(user=%r, hotel=%r, base_url=%r, password=***)" % (
            self.user, self.hotel, self.base_url)

    __str__ = __repr__


# --------------------------------------------------------------------------- the two locks
def is_enabled() -> bool:
    """Lock 1: the environment variable. False unless it is explicitly truthy."""
    return os.environ.get(ENABLE, "").strip().lower() in TRUTHY


def under_test() -> bool:
    """Lock 2: whether a test runner is loaded in this process.

    Looked up in `sys.modules` at the moment of the call rather than remembered at import, so
    it cannot be defeated by importing this module early.
    """
    return any(name in sys.modules for name in TEST_RUNNERS)


def assert_armed() -> None:
    """Refuse unless both locks are open. Called before anything can open a socket."""
    if not is_enabled():
        raise TransportDisabled(
            "the live transport is off. Set %s=1 to arm it, and read docs/open-questions.md "
            "first: calls to the vendor sandbox are approved individually, bounded and staged "
            "(decision D3, R8)." % ENABLE)
    if under_test():
        raise TransportDisabled(
            "the live transport refuses to arm inside a test process (%s is loaded). Success "
            "criterion 11 says no test can reach the network, and an environment variable "
            "alone would be a lock a test can open in one line."
            % ", ".join(name for name in TEST_RUNNERS if name in sys.modules))


def open_socket(call: HttpCall, timeout: float = DEFAULT_TIMEOUT) -> str:
    """The default dialer, and the only outbound socket in this engine.

    Asks permission BEFORE composing a request object, so nothing - not a DNS lookup, not a
    TLS handshake - leaves the machine when the transport is not armed.
    """
    assert_armed()
    request = urllib.request.Request(                        # noqa: S310 - see assert_armed
        call.url, data=call.body.encode("utf-8") or None,
        headers=dict(call.headers), method=call.method)
    with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310
        return response.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- the source
class LiveSource:
    """A body of evidence fetched now, shaped exactly like a body of evidence replayed.

    An adapter takes a source and calls `fetch`. Live and frozen are interchangeable there, or
    "the same code path" would be a claim rather than a fact - and the record mode below is
    what turns one into the other.
    """

    def __init__(self, provider: str, encoder: Callable[[Request, Credentials], HttpCall],
                 credentials: Credentials, clock: Clock,
                 bucket: TokenBucket | None = None,
                 dialer: Callable[[HttpCall], str] | None = None,
                 recorder: Any = None,
                 attempts: int = DEFAULT_ATTEMPTS,
                 backoff: timedelta = DEFAULT_BACKOFF,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.provider = provider
        self.encoder = encoder
        self.credentials = credentials
        self.clock = clock
        self.bucket = bucket or TokenBucket(DEFAULT_CAPACITY, DEFAULT_INTERVAL, clock)
        # The DEFAULT is the guarded one. A source that quietly defaulted to something
        # unguarded would make every safety test in this slice a decoration.
        self.dialer = dialer or open_socket
        self.recorder = recorder
        self.attempts = max(1, attempts)
        self.backoff = backoff
        self.sleeper = sleeper
        self.calls: list[Request] = []

    # ------------------------------------------------------------------ what a source is
    @property
    def origin(self) -> str:
        return "live %s, fetched %s" % (self.provider, self.clock.today().isoformat())

    @property
    def as_of(self) -> str:
        return self.clock.today().isoformat()

    @property
    def observed_at(self) -> str:
        """When these bytes were obtained, by the PROPERTY's clock and not the machine's (F11).

        A run's freshness is measured against this, and a laptop in another timezone would date
        it differently from the hotel it describes.
        """
        return self.clock.today().isoformat()

    @property
    def is_synthetic(self) -> bool:
        return False

    # ------------------------------------------------------------------ fetching
    def fetch(self, request: Request) -> str:
        """One call: paced, retried, recorded. Or a stated evidence gap."""
        self.calls.append(request)
        call = self.encoder(request, self.credentials)

        last = None
        for attempt in range(1, self.attempts + 1):
            self._pace()
            try:
                body = self.dialer(call)
            except TransportDisabled:
                # Never retried. A disabled transport is a configuration mistake, and three
                # attempts with backoff turns a loud instant failure into a slow confusing one.
                raise
            except Exception as exc:                                     # noqa: BLE001
                last = exc
                if attempt < self.attempts:
                    self._wait(self.backoff * attempt)
                continue

            if self.recorder is not None:
                self.recorder.record(request, body)
            return body

        raise ResponseUnavailable(
            "%s did not answer %s after %d attempt(s): %s: %s. This is an evidence gap, so the "
            "records that needed it are UNKNOWN rather than judged"
            % (self.provider, request.endpoint, self.attempts,
               type(last).__name__, last))

    def _pace(self) -> None:
        """R8. The vendor asked not to be queried hard, so the queue is here and not in a
        caller who would have to remember it."""
        self._wait(self.bucket.take())

    def _wait(self, delay: timedelta) -> None:
        if delay > timedelta(0):
            self.sleeper(delay.total_seconds())

    def __repr__(self) -> str:
        return "LiveSource(%s, %d call(s))" % (self.provider, len(self.calls))
