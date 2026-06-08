"""Top-level reflection package public entrypoint."""

import sys
from types import ModuleType
from typing import Any, cast

from . import reflection as _reflection
from .reflection import *  # noqa: F403


def __getattr__(name: str) -> object:
    if name == "_database":
        return _reflection._database
    return getattr(_reflection, name)


class _ReflectionPackage(ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(_reflection, name):
            super().__setattr__(name, value)
            setattr(_reflection, name, cast(Any, value))
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _ReflectionPackage
