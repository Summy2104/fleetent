"""Tools capability public API.

Tool registration, schema building, dispatch, access control, result
truncation, plugin loading, multimodal message assembly, and vision/image-gen
clients. Cross-package callers import the public API from here; importing this
package also triggers built-in tool registration as a side effect.

Importing ``builtin_tools`` below is load-bearing: ``import fleetent.tools``
registers the built-in tools (preserving the historical flat-module side
effect), so ``get_schemas()`` is non-empty after import.

Submodules (``registry``, ``builtin_tools``, ``multimodal``,
``vision_client``, ``image_gen_client``, ``plugin_loader``,
``result_truncation``) reference each other directly to avoid an import cycle
through this ``__init__``.
"""

from fleetent.tools import builtin_tools  # noqa: F401  # side-effect: register built-in tools
from fleetent.tools import file_tools  # noqa: F401  # side-effect: register file tools
from fleetent.tools.builtin_tools import _get_manager  # noqa: F401  # compat re-export
from fleetent.tools.multimodal import build_message_with_images, has_image_block
from fleetent.tools.plugin_loader import expand_plugin_patterns, load_plugins
from fleetent.tools.registry import (
    ToolContext,
    _registry,  # noqa: F401  # compat re-export
    dispatch,
    get_schemas,
    tool,
)
from fleetent.tools.result_truncation import truncate_tool_result

# _get_manager / _registry are compat attributes for legacy lazy imports
# (`from fleetent.tools import _get_manager` / `_registry`); intentionally not
# in __all__.

__all__ = [
    "ToolContext",
    "build_message_with_images",
    "dispatch",
    "expand_plugin_patterns",
    "get_schemas",
    "has_image_block",
    "load_plugins",
    "tool",
    "truncate_tool_result",
]
