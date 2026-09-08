# -*- coding: utf-8 -*-
"""The MiniHotel adapter. Nothing above `hotelcontrols.providers` may import from here.

`ADAPTER`, `FROZEN`, `CAPTURES` and `DEFAULT_CAPTURE` are what `providers/registry.py`
discovers. It looks for those four names and nothing else, so it can offer every provider the
engine has without a line of code anywhere naming one.
"""
from .adapter import MiniHotelAdapter
from .fixtures import FrozenSource
from .records import IDENTITY_FIELD, Record

ADAPTER = MiniHotelAdapter
FROZEN = FrozenSource
CAPTURES = ("sandbox2024", "sandbox2026")
DEFAULT_CAPTURE = "sandbox2026"

__all__ = ["ADAPTER", "CAPTURES", "DEFAULT_CAPTURE", "FROZEN", "FrozenSource",
           "IDENTITY_FIELD", "MiniHotelAdapter", "Record"]
