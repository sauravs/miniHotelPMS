# -*- coding: utf-8 -*-
"""
Slice 0 gate: every kernel type is a frozen dataclass.

Evidence is a record of what was true when a run was made. If a `Value` or a `Verdict` can be
mutated after construction, then a stored FAIL can acquire a different number than the one it
was based on, and the audit trail becomes a suggestion.

Written as a walk over the module rather than one assertion per class, so a type added in a
later slice is covered the day it appears rather than the day somebody remembers to add a test.
"""
import dataclasses
import inspect

import pytest

from hotelcontrols import kernel


def _kernel_dataclasses():
    for name in kernel.__all__:
        obj = getattr(kernel, name)
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj):
            yield name, obj


def test_the_kernel_exports_the_types_it_promises():
    """A guard on the walk below: if the export list were empty these tests would pass
    vacuously and prove nothing."""
    assert {name for name, _ in _kernel_dataclasses()} >= {
        "Money", "Value", "Verdict", "EvidenceLine", "FixedClock", "PropertyClock"}


@pytest.mark.parametrize("name,cls", list(_kernel_dataclasses()), ids=lambda x: getattr(x, "__name__", x))
def test_every_kernel_dataclass_is_frozen(name, cls):
    assert cls.__dataclass_params__.frozen, (
        "%s must be frozen: evidence that can change after the fact is not evidence" % name)


@pytest.mark.parametrize("name,cls", list(_kernel_dataclasses()), ids=lambda x: getattr(x, "__name__", x))
def test_every_kernel_dataclass_uses_slots(name, cls):
    """Slots are a second lock: without them an attribute the class never declared can be
    attached to an instance, and a stored run can grow a field nothing validated."""
    assert "__slots__" in vars(cls), "%s must declare __slots__" % name
