"""Daily Notes - create dated notes for journaling and daily logs."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from . import config
from .plugins import get_manager


def get_today_filename() -> str:
    """Get the filename for today's daily note.

    Returns:
        Filename in YYYY-MM-DD.md format (e.g., "2025-03-08.md")
    """
    return datetime.now().strftime("%Y-%m-%d.md")


def get_today_title() -> str:
    """Get the title for today's daily note.

    Returns:
        Human-readable date (e.g., "Saturday, March 8, 2025")
    """
    return datetime.now().strftime("%A, %B %d, %Y")


def create_daily_note(open_editor: bool = False) -> tuple[Path, bool]:
    """Create today's daily note if it doesn't exist.

    Args:
        open_editor: If True, open the note in $EDITOR after creation.

    Returns:
        Tuple of (note_path, was_created) where was_created is True if
        the note was just created, False if it already existed.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR
    brain_dir.mkdir(parents=True, exist_ok=True)

    filename = get_today_filename()
    note_path = brain_dir / filename
    title = get_today_title()

    was_created = False

    if not note_path.exists():
        # --- Hook: before_daily_note_create ---
        pm.dispatch_before_daily_note_create(filename)

        # Create new daily note with template
        content = f"# {title}\n\n## Notes\n\n\n## Tasks\n\n- [ ] \n\n"
        note_path.write_text(content)
        was_created = True

        # --- Hook: after_daily_note_create ---
        pm.dispatch_after_daily_note_create(note_path, was_created)
    else:
        # --- Hook: after_daily_note_open ---
        pm.dispatch_after_daily_note_open(note_path, was_created)

    if open_editor:
        editor = os.environ.get("EDITOR", "nvim")
        subprocess.run([editor, str(note_path)])

    return note_path, was_created


def get_daily_note(date_str: str) -> Path | None:
    """Get the path to a daily note for a specific date.

    Args:
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Path to the note if it exists, None otherwise.
    """
    brain_dir = config.BRAIN_DIR
    filename = f"{date_str}.md"
    note_path = brain_dir / filename
    return note_path if note_path.exists() else None


def list_daily_notes() -> list[Path]:
    """List all daily notes in the brain directory.

    Returns:
        List of paths to daily notes, sorted by date (newest first).
    """
    brain_dir = config.BRAIN_DIR
    daily_pattern = r"^\d{4}-\d{2}-\d{2}\.md$"

    import re

    daily_notes = []

    for f in brain_dir.glob("*.md"):
        if f.name == "dump.md":
            continue
        if re.match(daily_pattern, f.name):
            daily_notes.append(f)

    # Sort by date (newest first)
    daily_notes.sort(key=lambda p: p.name, reverse=True)
    return daily_notes
