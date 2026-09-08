# -*- coding: utf-8 -*-
"""The MiniHotel adapter. Nothing above `hotelcontrols.providers` may import from here."""
from .adapter import MiniHotelAdapter
from .fixtures import FrozenSource
from .records import IDENTITY_FIELD, Record

__all__ = ["FrozenSource", "IDENTITY_FIELD", "MiniHotelAdapter", "Record"]
