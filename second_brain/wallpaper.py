"""Backward compatibility - import from wallpaper package."""

from .wallpaper.composite import composite_wallpaper
from .wallpaper.overlays import render_rss_overlay, render_todo_overlay
from .wallpaper.setter import refresh_wallpaper, set_wallpaper

__all__ = [
    "render_todo_overlay",
    "render_rss_overlay",
    "composite_wallpaper",
    "set_wallpaper",
    "refresh_wallpaper",
]
