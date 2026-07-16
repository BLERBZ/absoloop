"""Import helpers for the extension-less executables under test.

`bin/absoloop` and `templates/absoloop-run` have no .py suffix, so normal
imports cannot load them; tests import them through SourceFileLoader.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from importlib.machinery import SourceFileLoader

REPO = pathlib.Path(__file__).resolve().parent.parent


def load_module(name: str, relpath: str):
    if name in sys.modules:
        return sys.modules[name]
    path = REPO / relpath
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def load_cli():
    return load_module("absoloop_cli_under_test", "bin/absoloop")


def load_runner():
    return load_module("absoloop_run_under_test", "templates/absoloop-run")
