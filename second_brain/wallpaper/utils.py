"""Wallpaper utility functions."""

from __future__ import annotations

import re

from .. import config
from ..plugins import get_manager


def _parse_todos() -> list[tuple[bool, str]]:
    """Parse todo.md and return list of (done, text) tuples.

    Only returns unchecked items (- [ ]) for the wallpaper overlay.
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
        m = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", line)
        if m:
            done = m.group(1).lower() == "x"
            text = m.group(2).strip()
            items.append((done, text))

    # --- Hook: after_parse_todos (mutating) ---
    items = pm.dispatch_after_parse_todos(items)

    return items


def _parse_investments() -> dict | None:
    """Parse investments.md and return investment data.

    Returns dict with investments list and summary, or None if no investments exist.
    """
    from ..investments import get_portfolio_summary, load_investments

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
