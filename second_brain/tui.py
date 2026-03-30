"""Backward compatibility - import from tui package."""

from .tui.app import BrainApp, run_tui

__all__ = ["BrainApp", "run_tui"]
