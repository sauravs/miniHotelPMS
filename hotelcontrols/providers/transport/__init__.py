# -*- coding: utf-8 -*-
"""
TRANSPORT - opt-in, off by default, and unable to arm inside a test process.

Review finding F13: v1 had no HTTP client at all. That was the right safety property and it
also meant there was no path from the demo to production - the most operationally risky
component in the system was the one nobody had written or tested. This package is that
component, with the safety property intact.

    is_enabled()      lock 1: the HOTELCONTROLS_LIVE environment variable
    assert_armed()    lock 2: and no test runner in the process
    TokenBucket       pacing, as a pure function of an injected clock (R8)
    LiveSource        a body of evidence fetched now, shaped like one replayed
    Recorder          the response, written down with the question that produced it
    Credentials       from the environment, with no default, ever (F15)

NOTHING HERE NAMES A PMS. This package sits outside every adapter's directory, so the
canonical-boundary grep polices it exactly as it polices the evaluator: the request-to-HTTP
encoding is the adapter's and arrives as a callable, and the credential variable names are
built from a provider name that arrives as data.
"""
from .http import (Credentials, HttpCall, LiveSource, MissingCredential, TransportDisabled,
                   assert_armed, is_enabled, open_socket)
from .ratelimit import TokenBucket
from .record import Recorder

__all__ = [
    "Credentials",
    "HttpCall",
    "LiveSource",
    "MissingCredential",
    "Recorder",
    "TokenBucket",
    "TransportDisabled",
    "assert_armed",
    "is_enabled",
    "open_socket",
]
