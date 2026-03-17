#!/usr/bin/env python3
"""Backward-compatible setup.py shim.

This file allows ``pip install .`` to work with older versions of pip
that do not natively support PEP 517 / pyproject.toml.

All project metadata is defined in pyproject.toml.
"""

from setuptools import setup

setup()
