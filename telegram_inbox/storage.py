"""Persistent storage for messages and note backups.

Messages are stored in a JSON file. Notes are stored as individual .md
files in a notes/ subdirectory, mirroring the brain directory structure.

All writes use atomic temp-file-then-rename to avoid corruption.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import config
except ImportError:
    import config  # type: ignore[no-redef]


def _data_dir() -> Path:
    """Get and ensure the data directory exists."""
    d = Path(config.get_data_dir())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _messages_path() -> Path:
    return _data_dir() / "messages.json"


def _notes_dir() -> Path:
    d = _data_dir() / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Message inbox
# ---------------------------------------------------------------------------

def _read_messages() -> list[dict]:
    """Read the current message queue."""
    path = _messages_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("messages", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _write_messages(messages: list[dict]) -> None:
    """Atomically write the message queue."""
    path = _messages_path()
    data = {"messages": messages}
    # Write to a temp file then rename for atomicity
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_message(text: str, user_id: int, username: str = "") -> None:
    """Add a message to the inbox queue."""
    messages = _read_messages()
    messages.append({
        "text": text,
        "user_id": user_id,
        "username": username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _write_messages(messages)


def get_messages() -> list[dict]:
    """Return all pending messages."""
    return _read_messages()


def ack_messages() -> int:
    """Clear the inbox. Returns the number of messages cleared."""
    messages = _read_messages()
    count = len(messages)
    _write_messages([])
    return count


# ---------------------------------------------------------------------------
# Note backup storage
# ---------------------------------------------------------------------------

def store_notes(notes: dict[str, str]) -> int:
    """Store a batch of note files (full brain sync).

    Args:
        notes: Dict mapping filename -> content (e.g. {"school.md": "# School\n..."})

    Returns:
        Number of files written.
    """
    notes_dir = _notes_dir()
    count = 0
    for fname, content in notes.items():
        # Sanitize filename — only allow .md files, no path traversal
        fname = Path(fname).name
        if not fname.endswith(".md"):
            continue
        if ".." in fname or "/" in fname:
            continue

        fpath = notes_dir / fname
        fd, tmp = tempfile.mkstemp(dir=notes_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp, fpath)
            count += 1
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    return count


def list_notes() -> list[str]:
    """Return a sorted list of backed-up note filenames."""
    notes_dir = _notes_dir()
    return sorted(f.name for f in notes_dir.glob("*.md"))


def read_note(fname: str) -> str | None:
    """Read a backed-up note by filename. Returns None if not found."""
    fname = Path(fname).name
    if not fname.endswith(".md"):
        fname += ".md"
    fpath = _notes_dir() / fname
    if not fpath.exists():
        return None
    return fpath.read_text()


def get_note_headers(fname: str) -> list[dict]:
    """Parse ## headers from a note file.

    Returns a list of dicts with:
        - "header": the header text (without ##)
        - "level": heading level (1-6)
        - "line": line number (0-indexed)
    """
    content = read_note(fname)
    if content is None:
        return []

    headers = []
    for i, line in enumerate(content.splitlines()):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            headers.append({
                "header": m.group(2).strip(),
                "level": len(m.group(1)),
                "line": i,
            })

    return headers


def get_note_section(fname: str, header_line: int) -> str | None:
    """Extract a section starting at the given header line.

    Returns content from the header line until the next header of the
    same or higher level, or end of file.
    """
    content = read_note(fname)
    if content is None:
        return None

    lines = content.splitlines()
    if header_line < 0 or header_line >= len(lines):
        return None

    # Determine the level of the starting header
    m = re.match(r"^(#{1,6})\s+", lines[header_line])
    if not m:
        return None
    start_level = len(m.group(1))

    # Collect lines until we hit another header of same or higher level
    section_lines = [lines[header_line]]
    for line in lines[header_line + 1:]:
        hm = re.match(r"^(#{1,6})\s+", line)
        if hm and len(hm.group(1)) <= start_level:
            break
        section_lines.append(line)

    return "\n".join(section_lines).strip()
