# -*- coding: utf-8 -*-
"""
L7 · WEB - who is asking, verified (v3 slice 24, decision D14).

THE HOST AUTHENTICATES; THE ENGINE VERIFIES
--------------------------------------------
The engine has no login, stores no password and knows no user. The product in front of it - the
Next.js UI in this repository, or a hotel group's own portal - signs a short-lived TENANT
CONTEXT ("this request is about property P, on behalf of S, until T") with a secret it shares
with the engine, and sends it with every request. The engine checks the signature with
`hmac.compare_digest`, checks the expiry through the injected clock, and from then on the
CONTEXT decides which property a request is about. `?property=` and a POST's `property` field
stop selecting anything: the verified property overwrites them, on every route, before any route
runs (`App.handle`). That is the whole of G5's second half - identity from a signature, never
from a URL.

WHY A SIGNED CONTEXT AND NOT A SESSION
---------------------------------------
Standard library only (D2): `hmac`, `hashlib`, `base64`, `json`. No token library, no cookie the
engine must remember, nothing stored - so the engine stays stateless about people, and a context
that leaks expires on its own within `MAXIMUM_LIFETIME`.

THE WIRE FORM, AND WHY IT IS THIS SMALL
----------------------------------------
    <base64url(payload JSON)>.<base64url(HMAC-SHA256(secret, the first part))>

No padding. The MAC covers the payload's base64 text exactly as it was sent, so no JSON has to
be re-serialised identically in two languages - the UI signs it with `node:crypto` and the
cross-language vector in `ui/test/fixtures/auth-vector.json` pins that both produce one string.
The payload is parsed only AFTER its signature holds: nothing an attacker wrote is read first.

    {"v": 1, "aud": "hotelcontrols-engine", "property": "sandbox", "sub": "alice", "exp": 1767225600}

`aud` keeps a token minted for something else - the UI's own session cookie is signed with the
same secret - from being replayed here as a context.

OFF IS TODAY'S DEMO EXACTLY
----------------------------
Auth mode is switched on by the secret's PRESENCE (`HOTELCONTROLS_AUTH_SECRET`). Absent, the
engine is the single-operator demo it has always been, and every golden payload is byte-identical
- the exit test that keeps this slice from changing an answer. `HOTELCONTROLS_AUTH=1` DEMANDS auth
mode: with it set and no usable secret, the engine refuses to start rather than serving the demo
unprotected to somebody who believes it is protected. A secret that is empty or shorter than
`MINIMUM_SECRET` is refused the same way - a guessable key is a forged context waiting to happen.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from ..kernel import PropertyClock

SECRET_VARIABLE = "HOTELCONTROLS_AUTH_SECRET"
DEMAND_VARIABLE = "HOTELCONTROLS_AUTH"

# Where the context arrives. A header of its own rather than `Authorization`, because the caller
# is a server acting for a person, not a person's browser speaking HTTP authentication.
HEADER = "X-HotelControls-Context"

AUDIENCE = "hotelcontrols-engine"
VERSION = 1

# Characters, not bits: the secret is read from an environment variable as text. 32 is the floor
# below which an HMAC key stops being a secret worth the name.
MINIMUM_SECRET = 32

# "Short-lived" made a number. A context still claiming more than this when it arrives is refused
# - not because it is forged, but because a context good for a month is a password by another
# name, and a leaked one would be a month of somebody else's hotel.
MAXIMUM_LIFETIME = 15 * 60


class AuthMisconfigured(RuntimeError):
    """The engine was asked to verify identities and cannot. It refuses to START, loudly, rather
    than serving every property to anybody who asks."""


class ContextRefused(Exception):
    """A request whose context is missing, malformed, wrongly signed, expired or not for a
    property here. `status` is what a reader sees; the token itself is never echoed."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True, slots=True)
class TenantContext:
    """A verified answer to "who is asking, about which property". Built only by `verify`."""

    property_id: str
    subject: str
    expires: int


class Verifier:
    """Checks a signed tenant context. Holds the key; never hands it out."""

    __slots__ = ("_key", "_clock")

    def __init__(self, secret: str, clock=None) -> None:
        if not isinstance(secret, str) or len(secret.strip()) < MINIMUM_SECRET:
            raise AuthMisconfigured(
                "%s must be at least %d characters: a short key makes a forged context a "
                "guess away" % (SECRET_VARIABLE, MINIMUM_SECRET))
        self._key = secret.encode("utf-8")
        # Expiry is judged by THIS clock - injected in a test, the kernel's otherwise.
        # `kernel/clock.py` stays the only module in the engine that reads a wall clock.
        self._clock = clock if clock is not None else PropertyClock("UTC")

    @classmethod
    def from_environment(cls, clock=None, environ=None) -> Verifier | None:
        """The verifier the environment asks for, or None for today's demo.

        None ONLY when no secret is set and auth is not demanded. A secret that is set but empty
        or short, or auth demanded with no secret, refuses - never quietly falls back to "off".
        """
        environ = os.environ if environ is None else environ
        secret = environ.get(SECRET_VARIABLE)
        if secret is None:
            if environ.get(DEMAND_VARIABLE) == "1":
                raise AuthMisconfigured(
                    "%s=1 demands authentication, and %s is not set. There is no default "
                    "secret; refusing to start rather than serve every property to anyone"
                    % (DEMAND_VARIABLE, SECRET_VARIABLE))
            return None
        return cls(secret, clock)

    def verify(self, token: str | None, properties) -> TenantContext:
        """The context a request carries, verified - or `ContextRefused` saying which check
        failed. Unsigned, malformed, wrongly signed and expired are each a different sentence,
        so an integrator can tell them apart; none of them repeats the token."""
        if not token:
            raise ContextRefused(401, "This engine requires a signed tenant context (%s), and "
                                      "the request carried none." % HEADER)
        parts = token.strip().split(".")
        if len(parts) != 2 or not all(parts):
            raise ContextRefused(401, "The tenant context is malformed: it must be two "
                                      "base64url parts joined by a dot.")
        payload_text, signature_text = parts
        try:
            signature = _decode(signature_text)
        except (binascii.Error, ValueError):
            raise ContextRefused(401, "The tenant context's signature is not base64url.") \
                from None
        expected = hmac.new(self._key, payload_text.encode("ascii", errors="replace"),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise ContextRefused(401, "The tenant context is not signed with this engine's "
                                      "secret.")

        # Only now is anything the caller wrote read.
        try:
            payload = json.loads(_decode(payload_text))
        except (binascii.Error, ValueError):
            raise ContextRefused(401, "The tenant context's payload is not JSON.") from None
        if not isinstance(payload, dict) or payload.get("v") != VERSION \
                or payload.get("aud") != AUDIENCE:
            raise ContextRefused(401, "The tenant context is not one this engine reads (it "
                                      "expects v=%d, aud=%s)." % (VERSION, AUDIENCE))
        property_id, subject, expires = (payload.get("property"), payload.get("sub"),
                                         payload.get("exp"))
        if not (isinstance(property_id, str) and property_id
                and isinstance(subject, str) and subject
                and isinstance(expires, int) and not isinstance(expires, bool)):
            raise ContextRefused(401, "The tenant context must name a property, a subject and "
                                      "an expiry in whole seconds.")

        now = self._clock.now().timestamp()
        if expires <= now:
            raise ContextRefused(401, "The tenant context has expired. Contexts are short-lived "
                                      "on purpose; the host signs a fresh one per request.")
        if expires - now > MAXIMUM_LIFETIME:
            raise ContextRefused(401, "The tenant context claims to be valid for longer than "
                                      "%d seconds, which this engine does not accept."
                                 % MAXIMUM_LIFETIME)
        if property_id not in tuple(properties):
            # Signed with the right key for a property this engine does not have: a real
            # identity, asking about nothing here. Forbidden rather than unauthenticated.
            raise ContextRefused(403, "The tenant context is for a property this engine does "
                                      "not serve.")
        return TenantContext(property_id=property_id, subject=subject, expires=expires)


def sign(secret: str, property_id: str, subject: str, expires: int) -> str:
    """A context, signed - what the host does. Here for tests and for anything that hosts this
    engine from Python; the UI does the same in `ui/lib/auth.ts`, pinned by a shared vector."""
    payload = json.dumps({"v": VERSION, "aud": AUDIENCE, "property": property_id,
                          "sub": subject, "exp": expires},
                         separators=(",", ":"), sort_keys=True)
    payload_text = _encode(payload.encode("utf-8"))
    mac = hmac.new(secret.encode("utf-8"), payload_text.encode("ascii"),
                   hashlib.sha256).digest()
    return "%s.%s" % (payload_text, _encode(mac))


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    # Strict alphabet: urlsafe_b64decode would otherwise discard characters it does not know.
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
           for c in text):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
