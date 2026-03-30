"""Wallpaper setting functions - apply composited wallpaper to desktop."""

import configparser
import subprocess
from pathlib import Path

from .. import config
from ..plugins import get_manager


def _update_wallpaper_caches(wallpaper_path: Path) -> None:
    """Update any DE-specific wallpaper cache files.

    This prevents desktop environment restore scripts from overwriting
    our composited wallpaper on next login.

    Handles different cache formats:
    - Plain text files (ml4w): just write the path
    - nitrogen bg-saved.cfg: INI format, update file= keys
    - feh ~/.fehbg: shell script, rewrite with --bg-fill
    """
    for cache_path in config.get_wallpaper_cache_paths():
        try:
            if not cache_path.parent.exists():
                continue

            name = cache_path.name

            if name == "bg-saved.cfg":
                # nitrogen uses INI format -- update file= values in-place
                _update_nitrogen_config(cache_path, wallpaper_path)
            elif name == ".fehbg":
                # feh uses a shell script
                cache_path.write_text(f"#!/bin/sh\nfeh --bg-fill '{wallpaper_path}'\n")
            else:
                # Plain text (e.g., ml4w current_wallpaper)
                cache_path.write_text(str(wallpaper_path))
        except OSError:
            pass


def _update_nitrogen_config(cfg_path: Path, wallpaper_path: Path) -> None:
    """Update nitrogen's bg-saved.cfg, preserving INI structure."""
    cp = configparser.ConfigParser()
    if cfg_path.exists():
        cp.read(cfg_path)

    # Update file= in all sections, or create a default section
    if not cp.sections():
        cp.add_section("xin_-1")
        cp.set("xin_-1", "file", str(wallpaper_path))
        cp.set("xin_-1", "mode", "5")  # zoom-fill
        cp.set("xin_-1", "bgcolor", "#000000")
    else:
        for section in cp.sections():
            cp.set(section, "file", str(wallpaper_path))

    with open(cfg_path, "w") as f:
        cp.write(f)


def set_wallpaper(wallpaper_path: Path | None = None) -> bool:
    """Set the composited wallpaper using the configured backend.

    Returns True if successful.
    """
    pm = get_manager()

    if wallpaper_path is None:
        wallpaper_path = config.WALLPAPER_OUTPUT

    if not wallpaper_path.exists():
        raise FileNotFoundError(f"Wallpaper not found: {wallpaper_path}")

    # --- Hook: before_set_wallpaper ---
    pm.dispatch_before_set_wallpaper(wallpaper_path)

    success = False

    # Try special handler first (e.g., hyprpaper needs multi-step commands)
    if config.set_wallpaper_special(wallpaper_path):
        _update_wallpaper_caches(wallpaper_path)
        success = True
    else:
        # Standard single-command backend
        cmd = config.get_wallpaper_set_cmd(wallpaper_path)
        if cmd:
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                _update_wallpaper_caches(wallpaper_path)
                success = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    # --- Hook: after_set_wallpaper ---
    pm.dispatch_after_set_wallpaper(wallpaper_path, success)

    return success


def refresh_wallpaper() -> str:
    """Full pipeline: render graph -> composite (with todo) -> set wallpaper.

    Returns a status message.
    """
    pm = get_manager()

    # --- Hook: before_refresh_wallpaper ---
    pm.dispatch_before_refresh_wallpaper()

    from ..graph import render_graph
    from .composite import composite_wallpaper

    try:
        graph_path = render_graph()
        composited = composite_wallpaper(graph_path=graph_path)
        success = set_wallpaper(composited)
        if success:
            result = f"Wallpaper updated: {composited}"
        else:
            backend = config.get_wallpaper_backend() or "none detected"
            result = (
                f"Graph composited to {composited} but could not set wallpaper. "
                f"Backend: {backend}. Run 'second-brain setup' to configure."
            )
    except Exception as e:
        result = f"Error: {e}"

    # --- Hook: after_refresh_wallpaper ---
    pm.dispatch_after_refresh_wallpaper(result)

    return result

