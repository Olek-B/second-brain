"""Interactive setup for Second Brain.

Auto-detects system capabilities and generates ~/.config/second_brain/config.json.
"""

import json
import shutil
import subprocess
from pathlib import Path

from . import config


def _check_tool(name: str) -> bool:
    """Check if a command-line tool is available."""
    return shutil.which(name) is not None


def _detect_session_type() -> str:
    """Detect display server type."""
    session = ""
    # XDG_SESSION_TYPE is set on most modern Linux
    xdg = __import__("os").environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg in ("wayland", "x11"):
        session = xdg
    elif __import__("os").environ.get("WAYLAND_DISPLAY"):
        session = "wayland"
    elif __import__("os").environ.get("DISPLAY"):
        session = "x11"
    return session or "unknown"


def _detect_compositor() -> str:
    """Try to identify the running compositor/WM."""
    import os
    # Hyprland
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    # Sway
    if os.environ.get("SWAYSOCK"):
        return "sway"
    # GNOME
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop:
        return "gnome"
    if "kde" in desktop or "plasma" in desktop:
        return "kde"
    if "xfce" in desktop:
        return "xfce"
    if "i3" in desktop:
        return "i3"
    return "unknown"


def detect_all() -> dict:
    """Run all detections and return a summary dict."""
    session = _detect_session_type()
    compositor = _detect_compositor()

    # Wallpaper backends
    wp_backends = []
    for b in config._WALLPAPER_BACKENDS:
        available = _check_tool(b["detect"])
        wp_backends.append({
            "name": b["name"],
            "available": available,
        })

    # Resolution detectors
    res_methods = []
    for name, fn in config._RESOLUTION_DETECTORS:
        if _check_tool(name.split()[0]):
            result = fn()
            res_methods.append({
                "name": name,
                "available": True,
                "result": list(result) if result else None,
            })
        else:
            res_methods.append({"name": name, "available": False, "result": None})

    # Font
    im_font, gv_font = config._detect_font()

    # Colors
    wal_available = (config._XDG_CACHE / "wal" / "colors.json").exists()

    # Required tools
    required = {
        "magick": _check_tool("magick"),
        "dot": _check_tool("dot"),
    }

    return {
        "session_type": session,
        "compositor": compositor,
        "wallpaper_backends": wp_backends,
        "resolution_methods": res_methods,
        "font": {"imagemagick": im_font, "graphviz": gv_font},
        "pywal_available": wal_available,
        "required_tools": required,
    }


def generate_config(detection: dict | None = None) -> dict:
    """Generate a config.json dict from detection results."""
    if detection is None:
        detection = detect_all()

    cfg: dict = {}

    # Paths
    cfg["paths"] = {
        "brain_dir": str(config._default_brain_dir()),
        "wallpaper_output": str(config._default_wallpaper_output()),
    }

    # Wallpaper backend -- pick first available
    for b in detection["wallpaper_backends"]:
        if b["available"]:
            cfg["wallpaper"] = {"backend": b["name"]}
            break
    if "wallpaper" not in cfg:
        cfg["wallpaper"] = {"backend": None}

    # Wallpaper cache files
    cache_paths = config._detect_wallpaper_cache_paths()
    if cache_paths:
        cfg["wallpaper"]["cache_files"] = [str(p) for p in cache_paths]

    # Display
    resolution = None
    for m in detection["resolution_methods"]:
        if m["result"]:
            resolution = m["result"]
            break

    cfg["display"] = {
        "resolution": resolution or [1920, 1080],
        "font_imagemagick": detection["font"]["imagemagick"],
        "font_graphviz": detection["font"]["graphviz"],
    }

    return cfg


def run_setup(interactive: bool = True) -> Path:
    """Run setup: detect, optionally prompt, then write config.

    Returns the path to the written config file.
    """
    print("Detecting system configuration...\n")
    detection = detect_all()

    # Print detection results
    print(f"  Session type:  {detection['session_type']}")
    print(f"  Compositor:    {detection['compositor']}")
    print()

    print("  Wallpaper backends:")
    for b in detection["wallpaper_backends"]:
        status = "found" if b["available"] else "not found"
        marker = "*" if b["available"] else " "
        print(f"    [{marker}] {b['name']:12s}  {status}")
    print()

    print("  Resolution detection:")
    for m in detection["resolution_methods"]:
        if m["available"]:
            res_str = f"{m['result'][0]}x{m['result'][1]}" if m["result"] else "no output"
            print(f"    [*] {m['name']:12s}  {res_str}")
        else:
            print(f"    [ ] {m['name']:12s}  not found")
    print()

    print(f"  Font:          {detection['font']['imagemagick']}")
    print(f"  Pywal:         {'found' if detection['pywal_available'] else 'not found (using defaults)'}")
    print()

    # Required tools
    missing = [k for k, v in detection["required_tools"].items() if not v]
    if missing:
        print(f"  WARNING: Missing required tools: {', '.join(missing)}")
        print("  Install them for full functionality:")
        print(f"    sudo pacman -S {' '.join(missing)} / apt install {' '.join(missing)}")
        print()

    # Generate config
    cfg = generate_config(detection)

    if interactive:
        # Allow user to override brain dir
        default_brain = cfg["paths"]["brain_dir"]
        answer = input(f"  Brain directory [{default_brain}]: ").strip()
        if answer:
            cfg["paths"]["brain_dir"] = answer
        print()

    # Write config
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path = config.CONFIG_FILE

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"  Config written to: {config_path}")
    print("  Edit this file to customize further.\n")

    # Ensure brain directory exists
    brain_dir = Path(cfg["paths"]["brain_dir"])
    if not brain_dir.exists():
        brain_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Created brain directory: {brain_dir}")

    # Reload config in memory
    config.reload_config()

    return config_path
