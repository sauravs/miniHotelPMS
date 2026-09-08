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
