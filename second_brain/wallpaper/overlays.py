"""Wallpaper overlay rendering functions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import config
from ..plugins import get_manager
from ..rss_reader import get_latest_entries
from .utils import _parse_investments, _parse_todos


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
        f"{bg}C0",
        "-stroke",
        f"{accent}80",
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


def render_rss_overlay(output_path: Path | None = None) -> Path | None:
    """Render RSS feed entries as a transparent PNG for the wallpaper.

    Shows the latest 5-7 entries from all feeds on a styled panel
    matching the todo panel aesthetic (semi-transparent background,
    rounded corners, accent stroke).

    Returns the path to the overlay PNG, or None if no entries.
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
    wal = config.get_wal_colors()
    colors = wal.get("colors", {})
    font_im, _ = config.get_font()

    # Get colors with proper fallbacks
    bg = colors.get("color0", "#1d2021") or "#1d2021"
    fg = colors.get("color15", "#ebdbb2") or "#ebdbb2"

    # Find a good accent color from available colors
    accent = None
    for key in ("color10", "color11", "color12", "color4", "color6", "color3"):
        c = colors.get(key, "")
        if c:
            accent = c
            break
    if not accent:
        accent = "#83a598"  # Default blue-green

    # Panel dimensions: left side, below todo panel
    panel_w = int(width * 0.18)  # 18% of screen width
    panel_h = int(height * 0.3)  # 30% of screen height
    pad_x = 20
    pad_y = 40
    line_height = 18  # Slightly tighter for two-line entries
    title_size = 14
    item_size = 10
    header_height = 35

    # Limit items to what fits on screen (each entry takes 2 lines)
    max_items = (panel_h - pad_y * 2 - header_height) // (line_height * 2 - 4)
    display_items = entries[:max_items]
    remaining = len(entries) - len(display_items)

    # Calculate actual content height for panel background
    content_height = header_height + (len(display_items) * (line_height * 2 - 4))

    # Build ImageMagick draw commands
    draw_cmds = []

    # Semi-transparent dark background panel with rounded corners
    # Panel extends from pad_y to pad_y + content_height + padding
    draw_cmds.append(
        f"roundrectangle {pad_x - 10},{pad_y - 10} "
        f"{panel_w - 20},{pad_y + content_height + 10} "
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
        # Title
        "-font",
        font_im,
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
        "  RSS Feed",
    ]

    # Draw each RSS entry (title + source on separate lines)
    y = pad_y + header_height
    for entry in display_items:
        # Truncate long titles
        title = entry.title[:40] + "..." if len(entry.title) > 40 else entry.title
        source = entry.source[:30]  # Truncate source if needed

        # Draw title line
        line_text = f"• {title}"
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
        y += line_height - 2  # Slightly tighter spacing

        # Draw source line (indented)
        source_text = f"    [{source}]"
        magick_args.extend(
            [
                "-fill",
                f"{fg}AA",
                "-pointsize",
                str(item_size - 1),
                "-annotate",
                f"+{pad_x}+{y}",
                source_text,
            ]
        )
        y += line_height - 2

    # Show remaining count if truncated
    if remaining > 0:
        magick_args.extend(
            [
                "-fill",
                f"{fg}88",
                "-pointsize",
                str(item_size - 1),
                "-annotate",
                f"+{pad_x}+{y + 5}",
                f"  +{remaining} more...",
            ]
        )

    magick_args.append(str(output_path))

    try:
        subprocess.run(
            magick_args,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )

        # --- Hook: after_render_rss_overlay ---
        pm.dispatch_after_render_rss_overlay(output_path)

        return output_path

    except subprocess.CalledProcessError as e:
        log = config.logging.getLogger("second_brain.wallpaper")
        log.error("Error creating RSS overlay: %s", e.stderr)
        return None


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
        f"roundrectangle {pad_x - 10},{pad_y - 10} {panel_w - 20},{panel_h - 20} 10,10"
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
