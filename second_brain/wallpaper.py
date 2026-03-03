"""Wallpaper Layering - composite graph + todo panel onto wallpaper."""

import re
import subprocess
from pathlib import Path

from . import config


def _parse_todos() -> list[tuple[bool, str]]:
    """Parse todo.md and return list of (done, text) tuples.

    Only returns unchecked items (- [ ]) for the wallpaper overlay,
    limited to the most recent ones that fit.
    """
    todo_path = config.TODO_FILE
    if not todo_path.exists():
        return []

    content = todo_path.read_text()
    items: list[tuple[bool, str]] = []

    for line in content.splitlines():
        line = line.strip()
        # Match "- [ ] task" (unchecked) or "- [x] task" (checked)
        m = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", line)
        if m:
            done = m.group(1).lower() == "x"
            text = m.group(2).strip()
            items.append((done, text))

    return items


def render_todo_overlay(output_path: Path | None = None) -> Path | None:
    """Render the todo list as a transparent PNG for the left side of the wallpaper.

    Uses ImageMagick to draw text on a semi-transparent dark panel.
    Returns the path to the overlay PNG, or None if no todos exist.
    """
    if output_path is None:
        output_path = config.TODO_OVERLAY

    items = _parse_todos()
    # Only show unchecked items on wallpaper
    pending = [(done, text) for done, text in items if not done]

    if not pending:
        # Clean up old overlay if no pending todos
        output_path.unlink(missing_ok=True)
        return None

    width, height = config.get_monitor_resolution()
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})
    im_font, _ = config.get_font()

    fg = colors.get("color15", "#ebdbb2")
    bg = colors.get("color0", "#1d2021")
    accent = colors.get("color10", "#b8bb26") or colors.get("color3", "#d79921")
    # Find a good accent from available colors
    for key in ("color10", "color3", "color11", "color4", "color6"):
        c = colors.get(key, "")
        if c:
            accent = c
            break

    # Panel dimensions: left 20% of screen, with padding
    panel_w = int(width * 0.20)
    panel_h = height
    pad_x = 30
    pad_y = 60
    line_height = 24
    title_size = 16
    item_size = 11

    # Limit items to what fits on screen
    max_items = (panel_h - pad_y * 2 - 60) // line_height
    display_items = pending[:max_items]
    remaining = len(pending) - len(display_items)

    # Build ImageMagick draw commands
    draw_cmds = []

    # Semi-transparent dark background panel with rounded corners
    draw_cmds.append(
        f"roundrectangle {pad_x - 20},{pad_y - 20} "
        f"{panel_w - 20},{pad_y + 50 + len(display_items) * line_height + 10} "
        f"12,12"
    )

    magick_args = [
        "magick",
        "-size", f"{panel_w}x{panel_h}",
        "xc:none",
        # Draw the background panel
        "-fill", f"{bg}B0",
        "-stroke", f"{accent}60",
        "-strokewidth", "1",
        "-draw", draw_cmds[0],
        # Title
        "-font", im_font,
        "-fill", accent,
        "-strokewidth", "0",
        "-pointsize", str(title_size),
        "-gravity", "NorthWest",
        "-annotate", f"+{pad_x}+{pad_y}", "  Todo",
    ]

    # Draw each todo item
    y = pad_y + 45
    for _done, text in display_items:
        # Truncate long items
        if len(text) > 42:
            text = text[:40] + ".."
        bullet = "  "
        line_text = f"{bullet} {text}"

        magick_args.extend([
            "-fill", fg,
            "-pointsize", str(item_size),
            "-annotate", f"+{pad_x}+{y}", line_text,
        ])
        y += line_height

    # Show remaining count if truncated
    if remaining > 0:
        magick_args.extend([
            "-fill", f"{fg}88",
            "-pointsize", str(item_size - 2),
            "-annotate", f"+{pad_x}+{y + 5}", f"   +{remaining} more...",
        ])

    magick_args.append(str(output_path))

    subprocess.run(
        magick_args,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    return output_path


def composite_wallpaper(
    graph_path: Path | None = None,
    wallpaper_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Composite graph (right) and todo panel (left) onto the wallpaper.

    Uses ImageMagick to layer both overlays onto the base wallpaper.
    Returns the path to the composited wallpaper.
    """
    if graph_path is None:
        graph_path = config.GRAPH_OUTPUT
    if output_path is None:
        output_path = config.WALLPAPER_OUTPUT
    if wallpaper_path is None:
        wallpaper_path = config.get_current_wallpaper()

    if wallpaper_path is None or not wallpaper_path.exists():
        backend = config.get_wallpaper_backend() or "unknown"
        raise FileNotFoundError(
            f"Could not determine current wallpaper. "
            f"Make sure your wallpaper backend ({backend}) is running. "
            f"Run 'second-brain setup' to configure."
        )

    if not graph_path.exists():
        raise FileNotFoundError(
            f"Graph overlay not found at {graph_path}. "
            "Run the graph engine first."
        )

    width, height = config.get_monitor_resolution()

    # Render todo overlay
    todo_path = render_todo_overlay()

    # Build the composite command
    # Base: resize wallpaper to monitor resolution
    magick_args = [
        "magick",
        str(wallpaper_path),
        "-resize", f"{width}x{height}^",
        "-gravity", "center",
        "-extent", f"{width}x{height}",
    ]

    # Layer 1: todo panel on the left
    if todo_path and todo_path.exists():
        magick_args.extend([
            str(todo_path),
            "-gravity", "NorthWest",
            "-composite",
        ])

    # Layer 2: graph on the right
    magick_args.extend([
        str(graph_path),
        "-gravity", "East",
        "-composite",
    ])

    magick_args.append(str(output_path))

    subprocess.run(
        magick_args,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    return output_path


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
                cache_path.write_text(
                    f"#!/bin/sh\nfeh --bg-fill '{wallpaper_path}'\n"
                )
            else:
                # Plain text (e.g., ml4w current_wallpaper)
                cache_path.write_text(str(wallpaper_path))
        except OSError:
            pass


def _update_nitrogen_config(cfg_path: Path, wallpaper_path: Path) -> None:
    """Update nitrogen's bg-saved.cfg, preserving INI structure."""
    import configparser

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
    if wallpaper_path is None:
        wallpaper_path = config.WALLPAPER_OUTPUT

    if not wallpaper_path.exists():
        raise FileNotFoundError(f"Wallpaper not found: {wallpaper_path}")

    # Try special handler first (e.g., hyprpaper needs multi-step commands)
    if config.set_wallpaper_special(wallpaper_path):
        _update_wallpaper_caches(wallpaper_path)
        return True

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
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return False


def refresh_wallpaper() -> str:
    """Full pipeline: render graph -> composite (with todo) -> set wallpaper.

    Returns a status message.
    """
    from .graph import render_graph

    try:
        graph_path = render_graph()
        composited = composite_wallpaper(graph_path=graph_path)
        success = set_wallpaper(composited)
        if success:
            return f"Wallpaper updated: {composited}"
        else:
            backend = config.get_wallpaper_backend() or "none detected"
            return (
                f"Graph composited to {composited} but could not set wallpaper. "
                f"Backend: {backend}. Run 'second-brain setup' to configure."
            )
    except Exception as e:
        return f"Error: {e}"
