"""Top-level reflection package public entrypoint."""

from fleetent.intelligence import reflection as _legacy_reflection

__all__ = [name for name in dir(_legacy_reflection) if not name.startswith("_")]
globals().update({name: getattr(_legacy_reflection, name) for name in __all__})
