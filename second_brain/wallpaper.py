"""Wallpaper Layering - composite graph + todo panel onto wallpaper."""

import logging
import re
import subprocess
from pathlib import Path

from . import config
from .plugins import get_manager
from .rss_reader import RSSEntry, get_latest_entries

log = logging.getLogger("second_brain.wallpaper")


def _parse_investments() -> list[dict] | None:
    """Parse investments.md and return investment data.

    Returns list of dicts with ticker, name, shares, buy_price, price, value, currency
    or None if no investments exist.
    """
    from .investments import get_portfolio_summary, load_investments

    investments = load_investments()
    summary = get_portfolio_summary()

    if not investments:
        return None

    data = []
    for inv in investments:
        if inv.current_price is not None:
            data.append(
                {
                    "ticker": inv.ticker,
                    "name": inv.name,
                    "shares": inv.shares,
                    "buy_price": inv.buy_price,
                    "price": inv.current_price,
                    "value": inv.market_value,
                    "currency": inv.currency,
                }
            )

    return {"investments": data, "summary": summary}


def _parse_todos() -> list[tuple[bool, str]]:
    """Parse todo.md and return list of (done, text) tuples.

    Only returns unchecked items (- [ ]) for the wallpaper overlay,
    limited to the most recent ones that fit.
    """
    pm = get_manager()

    # --- Hook: before_parse_todos ---
    pm.dispatch_before_parse_todos()

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

    # --- Hook: after_parse_todos (mutating) ---
    items = pm.dispatch_after_parse_todos(items)

    return items


def render_investments_overlay(output_path: Path | None = None) -> Path | None:
    """Render the investment portfolio as a transparent PNG for the bottom-left corner.

    Uses ImageMagick to draw text on a semi-transparent dark panel.
    Returns the path to the overlay PNG, or None if no investments exist.
    """
    pm = get_manager()

    if output_path is None:
        output_path = config.BRAIN_DIR / "investments_overlay.png"

    inv_data = _parse_investments()

    if not inv_data:
        # Clean up old overlay if no investments
        output_path.unlink(missing_ok=True)
        return None

    # --- Hook: before_render_investments_overlay ---
    pm.dispatch_before_render_investments_overlay(inv_data)

    width, height = config.get_monitor_resolution()
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})
    im_font, _ = config.get_font()

    # Get colors with proper fallbacks
    fg = colors.get("color15", "#ebdbb2") or "#ebdbb2"
    bg = colors.get("color0", "#1d2021") or "#1d2021"
    
    # Find a good accent color from available colors
    accent = None
    for key in ("color10", "color11", "color12", "color4", "color6", "color3"):
        c = colors.get(key, "")
        if c:
            accent = c
            break
    if not accent:
        accent = "#83a598"  # Default blue-green

    # Panel dimensions: bottom-left, compact
    panel_w = int(width * 0.25)  # 25% of screen width
    panel_h = 180  # Fixed height for investments
    pad_x = 20
    pad_y = 15
    line_height = 20
    title_size = 14
    item_size = 10

    # Limit to 5 investments max
    display_investments = inv_data["investments"][:5]
    remaining = len(inv_data["investments"]) - len(display_investments)
    summary = inv_data["summary"]

    # Build ImageMagick draw commands
    draw_cmds = []

    # Semi-transparent dark background panel with rounded corners
    draw_cmds.append(
        f"roundrectangle {pad_x - 10},{pad_y - 10} "
        f"{panel_w - 20},{panel_h - 20} "
        f"10,10"
    )

    magick_args = [
        "magick",
        "-size",
        f"{panel_w}x{panel_h}",
        "xc:none",
        # Draw the background panel
        "-fill",
        f"{bg}C0",
        "-stroke",
        f"{accent}80",
        "-strokewidth",
        "1",
        "-draw",
        draw_cmds[0],
        # Title with total value
        "-font",
        im_font,
        "-fill",
        accent,
        "-strokewidth",
        "0",
        "-pointsize",
        str(title_size),
        "-gravity",
        "NorthWest",
        "-annotate",
        f"+{pad_x}+{pad_y}",
        f"  Investments: {summary['total_value']:.0f} PLN",
    ]

    # Draw separator line
    magick_args.extend(
        [
            "-fill",
            f"{accent}60",
            "-draw",
            f"line {pad_x},{pad_y + 25} {panel_w - pad_x},{pad_y + 25}",
        ]
    )

    # Draw each investment
    y = pad_y + 42
    for inv in display_investments:
        ticker = inv["ticker"].upper()
        value = inv["value"]
        shares = inv["shares"]
        price = inv["price"]
        currency = inv.get("currency", "PLN")
        buy_price = inv.get("buy_price", 0)
        
        # Calculate gain/loss
        gain_loss = (price - buy_price) * shares if buy_price > 0 else 0
        gain_loss_pct = ((price - buy_price) / buy_price * 100) if buy_price > 0 else 0
        gain_sign = "+" if gain_loss >= 0 else ""
        
        # Format: TICKER  value  (+/-X%)
        line_text = f"  {ticker:<6} {value:.0f} {currency}  ({gain_sign}{gain_loss_pct:.1f}%)"

        magick_args.extend(
            [
                "-fill",
                fg,
                "-pointsize",
                str(item_size),
                "-annotate",
                f"+{pad_x}+{y}",
                line_text,
            ]
        )
        y += line_height

    # Show remaining count if truncated
    if remaining > 0:
        magick_args.extend(
            [
                "-fill",
                f"{fg}88",
                "-pointsize",
                str(item_size - 1),
                "-annotate",
                f"+{pad_x}+{y + 3}",
                f"   +{remaining} more...",
            ]
        )

    magick_args.append(str(output_path))

    subprocess.run(
        magick_args,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    # --- Hook: after_render_investments_overlay ---
    pm.dispatch_after_render_investments_overlay(output_path)

    return output_path


def render_rss_overlay(output_path: Path | None = None) -> Path | None:
    """Render RSS feed entries as a transparent PNG for the wallpaper.

    Shows the latest 5-7 entries from all feeds.
    Returns the path to the overlay PNG, or None if no entries.

    Args:
        output_path: Output path for the overlay PNG.

    Returns:
        Path to rendered overlay, or None if no entries.
    """
    pm = get_manager()

    if output_path is None:
        output_path = config.BRAIN_DIR / "rss_overlay.png"

    entries = get_latest_entries(n=7)

    if not entries:
        # Clean up old overlay if no entries
        if output_path.exists():
            output_path.unlink()
        return None

    # --- Hook: before_render_rss_overlay ---
    pm.dispatch_before_render_rss_overlay(entries)

    width, height = config.get_monitor_resolution()

    # RSS panel dimensions (left side, below todo panel)
    panel_width = int(width * 0.18)  # 18% of screen width
    panel_height = int(height * 0.3)  # 30% of screen height
    panel_x = 20  # Left margin
    panel_y = int(height * 0.35)  # Start below todo panel (35% down)

    # Get colors
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})
    bg = colors.get("color0", "#1d2021")
    fg = colors.get("color15", "#ebdbb2")
    accent = colors.get("color4", "#458588")

    # Get font
    font_im, _ = config.get_font()

    # Build text content
    lines = [
        "RSS Feed",
        "=" * 40,
    ]

    for entry in entries[:7]:
        # Truncate title to fit panel width (~50 chars)
        title = entry.title[:50] + "..." if len(entry.title) > 50 else entry.title
        source = entry.source[:20]
        lines.append(f"• {title}")
        lines.append(f"  [{source}]")

    # Create text content
    text_content = "\n".join(lines)

    # Create overlay with ImageMagick
    magick_cmds = [
        "magick",
        "-size",
        f"{panel_width}x{panel_height}",
        "xc:none",  # Transparent background
        "-font",
        font_im,
        "-pointsize",
        "14",
        "-fill",
        fg,
        "-gravity",
        "NorthWest",
        "-annotate",
        f"+10+10",
        text_content.replace("\n", "\\n"),
        str(output_path),
    ]

    try:
        subprocess.run(
            magick_cmds,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )

        # --- Hook: after_render_rss_overlay ---
        pm.dispatch_after_render_rss_overlay(output_path)

        return output_path

    except subprocess.CalledProcessError as e:
        log.error("Error creating RSS overlay: %s", e.stderr)
        return None


def render_todo_overlay(output_path: Path | None = None) -> Path | None:
    """Render the todo list as a transparent PNG for the left side of the wallpaper.

    Uses ImageMagick to draw text on a semi-transparent dark panel.
    Returns the path to the overlay PNG, or None if no todos exist.
    """
    pm = get_manager()

    if output_path is None:
        output_path = config.TODO_OVERLAY

    items = _parse_todos()
    # Only show unchecked items on wallpaper
    pending = [(done, text) for done, text in items if not done]

    if not pending:
        # Clean up old overlay if no pending todos
        output_path.unlink(missing_ok=True)
        # --- Hook: after_render_todo_overlay ---
        pm.dispatch_after_render_todo_overlay(None)
        return None

    # --- Hook: before_render_todo_overlay ---
    pm.dispatch_before_render_todo_overlay(pending)  # type: ignore[arg-type]

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
        "-size",
        f"{panel_w}x{panel_h}",
        "xc:none",
        # Draw the background panel
        "-fill",
        f"{bg}B0",
        "-stroke",
        f"{accent}60",
        "-strokewidth",
        "1",
        "-draw",
        draw_cmds[0],
        # Title
        "-font",
        im_font,
        "-fill",
        accent,
        "-strokewidth",
        "0",
        "-pointsize",
        str(title_size),
        "-gravity",
        "NorthWest",
        "-annotate",
        f"+{pad_x}+{pad_y}",
        "  Todo",
    ]

    # Draw each todo item
    y = pad_y + 45
    for _done, text in display_items:
        # Truncate long items
        if len(text) > 42:
            text = text[:40] + ".."
        bullet = "  "
        line_text = f"{bullet} {text}"

        magick_args.extend(
            [
                "-fill",
                fg,
                "-pointsize",
                str(item_size),
                "-annotate",
                f"+{pad_x}+{y}",
                line_text,
            ]
        )
        y += line_height

    # Show remaining count if truncated
    if remaining > 0:
        magick_args.extend(
            [
                "-fill",
                f"{fg}88",
                "-pointsize",
                str(item_size - 2),
                "-annotate",
                f"+{pad_x}+{y + 5}",
                f"   +{remaining} more...",
            ]
        )

    magick_args.append(str(output_path))

    subprocess.run(
        magick_args,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    # --- Hook: after_render_todo_overlay ---
    pm.dispatch_after_render_todo_overlay(output_path)

    return output_path


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

    from .graph import render_graph

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
