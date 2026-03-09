"""Plugin system for Second Brain - Backward Compatibility Module.

This module re-exports all public symbols from the split plugin modules
for backward compatibility. New code should import from the specific
modules directly:
  - brain_api: BrainAPI class
  - plugin_base: SecondBrainPlugin class
  - plugin_manager: PluginManager class, get_manager(), reset_manager()
"""

from __future__ import annotations

# Re-export all public symbols for backward compatibility
from .brain_api import BrainAPI, brain_api
from .plugin_base import SecondBrainPlugin
from .plugin_manager import (
    PluginManager,
    _has_override,
    _log_error,
    get_manager,
    reset_manager,
)

__all__ = [
    "BrainAPI",
    "brain_api",
    "SecondBrainPlugin",
    "PluginManager",
    "get_manager",
    "reset_manager",
    "_log_error",
    "_has_override",
]
