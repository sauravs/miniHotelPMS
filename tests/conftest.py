# -*- coding: utf-8 -*-
"""Shared test configuration.

The repository is not installed as a package - the engine has no packaging step and no
runtime dependencies - so the project root goes on the path here rather than in a build
artefact somebody has to remember to rebuild.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_ambient_authentication(monkeypatch):
    """v3 slice 24: an `App` reads its authentication from the environment, so a developer with
    HOTELCONTROLS_AUTH_SECRET exported would otherwise run every test in auth mode and see a wall
    of 401s that say nothing about the code. Each test starts with auth OFF - the demo every
    other test was written against - and a test about auth sets what it needs itself."""
    for name in ("HOTELCONTROLS_AUTH_SECRET", "HOTELCONTROLS_AUTH"):
        monkeypatch.delenv(name, raising=False)
