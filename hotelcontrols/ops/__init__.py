# -*- coding: utf-8 -*-
"""
OPS - the operational log (slice 20): structured JSON lines at the request, the run and the
dispatch, stamped by an injected clock, and holding no guest's details and no password.

    OpsLog(clock, logger).emit(event, **fields)    one record; the five keys always present
    attach(stream)                                  what the server's `--log` does
"""
from .log import CARRIES, LOGGER_NAME, JsonLines, OpsLog, attach, elapsed_ms

__all__ = ["CARRIES", "LOGGER_NAME", "JsonLines", "OpsLog", "attach", "elapsed_ms"]
