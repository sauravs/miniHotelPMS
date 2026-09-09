# -*- coding: utf-8 -*-
"""The MiniHotel adapter. Nothing above `hotelcontrols.providers` may import from here.

`ADAPTER`, `FROZEN`, `CAPTURES` and `DEFAULT_CAPTURE` are what `providers/registry.py`
discovers. It looks for those four names and nothing else, so it can offer every provider the
engine has without a line of code anywhere naming one.

`ENCODER` is the fifth and it is OPTIONAL: how a request looks on the wire is only knowable for
a PMS somebody has actually called. A provider without one can be replayed and cannot be
probed, which is a real difference and is reported rather than papered over.
"""
from .adapter import MiniHotelAdapter
from .fixtures import FrozenSource
from .live import encode
from .records import IDENTITY_FIELD, Record

ADAPTER = MiniHotelAdapter
FROZEN = FrozenSource
ENCODER = encode
CAPTURES = ("sandbox2024", "sandbox2026")
DEFAULT_CAPTURE = "sandbox2026"

__all__ = ["ADAPTER", "CAPTURES", "DEFAULT_CAPTURE", "ENCODER", "FROZEN",
           "FrozenSource", "IDENTITY_FIELD", "MiniHotelAdapter", "Record", "encode"]
