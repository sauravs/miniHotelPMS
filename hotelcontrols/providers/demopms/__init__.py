# -*- coding: utf-8 -*-
"""The DemoPMS adapter. Nothing above `hotelcontrols.providers` may import from here.

`ADAPTER`, `FROZEN`, `CAPTURES` and `DEFAULT_CAPTURE` are what `providers/registry.py`
discovers. It looks for those four names and nothing else, so it can offer every provider the
engine has without a line of code anywhere naming one - which is what makes "a third PMS is a
new directory" a claim rather than an aspiration.
"""
from .adapter import DemoPmsAdapter
from .fixtures import DemoSource
from .records import IDENTITY_FIELD, Record

ADAPTER = DemoPmsAdapter
FROZEN = DemoSource
CAPTURES = ("demo2024", "demo2026")
DEFAULT_CAPTURE = "demo2026"

__all__ = ["ADAPTER", "CAPTURES", "DEFAULT_CAPTURE", "DemoPmsAdapter", "DemoSource", "FROZEN",
           "IDENTITY_FIELD", "Record"]
