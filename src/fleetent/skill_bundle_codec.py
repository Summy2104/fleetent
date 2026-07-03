"""Binary-safe encoding for skill bundle file contents.

A backflow bundle is a ``dict[str, str]`` (relpath -> content) that is JSON-serialized into
the backflow table and later written into a git working tree by ``push_branch``. JSON strings
can't carry raw bytes, and a skill may legitimately ship binary files (images, PDFs, compiled
helpers). This codec makes each value round-trip losslessly while staying backward-compatible:

* **Text** (valid UTF-8) encodes to *itself* — a plain string, byte-identical to the pre-codec
  format, so existing rows and text files are unchanged and diff/text tooling keeps working.
* **Binary** (not valid UTF-8) encodes to ``<sentinel><base64>``. ``decode`` recognises the
  sentinel and restores the original bytes; ``is_binary`` lets callers avoid text-diffing it.

The sentinel is a NUL-delimited marker. A NUL byte marks a file as binary by universal
convention (git included), so a genuine *text* file whose decoded content begins with this
exact marker does not occur in practice.

Top-level, dependency-free infrastructure (like ``structured_logging``): it is shared by both
the git backend — which writes the real bytes — and ``platform.skill_management`` — which
captures and diffs bundles — so it lives above any layering boundary and pulls in nothing else.
"""

from __future__ import annotations

import base64

_SENTINEL = "\x00fleetent:b64\x00"


def encode(data: bytes) -> str:
    """Encode raw file bytes into a JSON-safe bundle value.

    Valid UTF-8 returns the decoded text unchanged (backward-compatible); anything else
    returns ``<sentinel><base64>``.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return _SENTINEL + base64.b64encode(data).decode("ascii")


def decode(value: str) -> bytes:
    """Restore the original file bytes from a bundle value (inverse of ``encode``)."""
    if value.startswith(_SENTINEL):
        return base64.b64decode(value[len(_SENTINEL) :])
    return value.encode("utf-8")


def is_binary(value: str) -> bool:
    """Whether a bundle value holds base64-encoded binary (vs. plain text)."""
    return value.startswith(_SENTINEL)
