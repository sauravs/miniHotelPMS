# -*- coding: utf-8 -*-
"""
L7 · WEB - the demo, and the reason it is thin.

    handle(path) -> (status, content_type, body)

Its single job is to prove a verdict traces to the fields that produced it. Server-side
rendering, no JavaScript, no framework, one stylesheet served from this package - because a
page that assembles itself from an API call is a page a browser, a CSP or a `file://` open can
break, and an unexplained verdict is not auditable.

Four success criteria live here:

    2   UNKNOWN is distinguishable from FAIL by hue, border AND wording
    3   every verdict lists its fields, their values WITH UNITS, and the call each came from
    8   a run that concluded nothing says so, and shows no count tiles
   10   readiness per control per provider, so a hotel knows what its PMS can answer

`app.py` routes, `render.py` renders, `server.py` is the only file that knows a socket exists.
"""
from .app import App, Response, handle
from . import render

__all__ = ["App", "Response", "handle", "render"]
