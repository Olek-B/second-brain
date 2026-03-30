"""Wallpaper compositing - layer graph and overlays onto wallpaper."""

import subprocess
from pathlib import Path

from .. import config
from ..plugins import get_manager
from .overlays import render_investments_overlay, render_rss_overlay, render_todo_overlay


def composite_wallpaper(
    graph_path: Path | None = None,
    wallpaper_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Composite graph (right), todo panel (left), RSS panel (left), and investments (bottom-left) onto wallpaper.

    Uses ImageMagick to layer overlays onto the base wallpaper.
    Returns the path to the composited wallpaper.
    """
    pm = get_manager()

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
            f"Graph overlay not found at {graph_path}. Run the graph engine first."
        )

    # --- Hook: before_composite ---
    pm.dispatch_before_composite(graph_path, wallpaper_path)

    width, height = config.get_monitor_resolution()

    # Render todo overlay (left side)
    todo_path = render_todo_overlay()

    # Render RSS overlay (left side, below todo)
    rss_path = render_rss_overlay()

    # Render investments overlay (bottom-left corner)
    investments_path = render_investments_overlay()

    # Create gradient panel for graph area (left-to-right fade)
    panel_w = int(width * 0.78)  # Graph area width
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})
    bg = colors.get("color0", "#1d2021")

    gradient_panel_path = config.GRAPH_OUTPUT.parent / "gradient_panel.png"

    # Create left-to-right gradient panel (transparent on left, darker on right)
    gradient_cmds = [
        "magick",
        "-size",
        f"{panel_w}x{height}",
        f"gradient:{bg}D0-{bg}00",
        "-rotate",
        "90",
        str(gradient_panel_path),
    ]

    subprocess.run(
        gradient_cmds,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    # Build the composite command
    # Base: resize wallpaper to monitor resolution
    magick_args = [
        "magick",
        str(wallpaper_path),
        "-resize",
        f"{width}x{height}^",
        "-gravity",
        "center",
        "-extent",
        f"{width}x{height}",
    ]

    # Layer 1: todo panel on the left
    if todo_path and todo_path.exists():
        magick_args.extend(
            [
                str(todo_path),
                "-gravity",
                "NorthWest",
                "-composite",
            ]
        )

    # Layer 2: RSS panel (left side, below todo)
    if rss_path and rss_path.exists():
        magick_args.extend(
            [
                str(rss_path),
                "-gravity",
                "NorthWest",
                "-geometry",
                f"+20+{int(height * 0.35)}",
                "-composite",
            ]
        )

    # Layer 3: gradient panel on the right (left-to-right fade)
    magick_args.extend(
        [
            str(gradient_panel_path),
            "-gravity",
            "East",
            "-composite",
        ]
    )

    # Layer 4: graph on the right (composited over gradient panel)
    magick_args.extend(
        [
            str(graph_path),
            "-gravity",
            "East",
            "-composite",
        ]
    )

    # Layer 5: investments panel on bottom-left
    if investments_path and investments_path.exists():
        magick_args.extend(
            [
                str(investments_path),
                "-gravity",
                "SouthWest",
                "-composite",
            ]
        )

    magick_args.append(str(output_path))

    subprocess.run(
        magick_args,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Clean up temporary gradient panel
    gradient_panel_path.unlink(missing_ok=True)

    # --- Hook: after_composite ---
    pm.dispatch_after_composite(output_path)

    return output_path
