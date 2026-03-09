"""Tag System - extract and manage #tags in markdown files."""

import re

from . import config
from .plugins import get_manager

# Pattern to match #tags (alphanumeric + hyphens, must start with letter)
_TAG_PATTERN = re.compile(r"(?<!\w)#([a-zA-Z][a-zA-Z0-9-]*)")


def extract_tags(content: str) -> list[str]:
    """Extract all #tags from markdown content.

    Args:
        content: Markdown file content.

    Returns:
        List of unique tags (without # prefix), lowercase.
    """
    pm = get_manager()

    # --- Hook: before_extract_tags ---
    pm.dispatch_before_extract_tags(content)

    tags = set()
    for match in _TAG_PATTERN.finditer(content):
        tags.add(match.group(1).lower())

    tag_list = sorted(tags)

    # --- Hook: after_extract_tags (mutating) ---
    result = pm.dispatch_after_extract_tags(tag_list)
    if result is not None:
        tag_list = result

    return tag_list


def get_all_tags() -> dict[str, list[str]]:
    """Scan all brain files and build tag index.

    Returns:
        Dict mapping tag -> list of filenames containing that tag.
    """
    brain_dir = config.BRAIN_DIR
    tag_index: dict[str, list[str]] = {}

    for md_file in brain_dir.glob("*.md"):
        if md_file.name == "dump.md":
            continue

        content = md_file.read_text()
        tags = extract_tags(content)

        for tag in tags:
            tag_index.setdefault(tag, []).append(md_file.name)

    # Sort files within each tag
    for tag in tag_index:
        tag_index[tag].sort()

    return tag_index


def get_files_by_tag(tag: str) -> list[str]:
    """Get all files containing a specific tag.

    Args:
        tag: Tag name (with or without # prefix).

    Returns:
        List of filenames containing the tag.
    """
    tag = tag.lstrip("#").lower()
    tag_index = get_all_tags()
    return tag_index.get(tag, [])


def get_tags_by_file(filename: str) -> list[str]:
    """Get all tags in a specific file.

    Args:
        filename: Name of file in brain directory.

    Returns:
        List of tags in the file.
    """
    brain_dir = config.BRAIN_DIR
    filepath = brain_dir / filename

    if not filepath.exists():
        return []

    content = filepath.read_text()
    return extract_tags(content)


def remove_tag_from_file(filename: str, tag: str) -> bool:
    """Remove a specific tag from a file.

    Args:
        filename: Name of file in brain directory.
        tag: Tag to remove (with or without # prefix).

    Returns:
        True if tag was removed, False if file not found or tag not present.
    """
    tag = tag.lstrip("#").lower()
    brain_dir = config.BRAIN_DIR
    filepath = brain_dir / filename

    if not filepath.exists():
        return False

    content = filepath.read_text()

    # Pattern to match the tag with # and optional surrounding spaces
    pattern = re.compile(rf"\s*#{re.escape(tag)}\s*", re.IGNORECASE)

    if not pattern.search(content):
        return False

    # Remove all occurrences of the tag
    new_content = pattern.sub(" ", content)
    filepath.write_text(new_content)

    return True


def add_tag_to_file(filename: str, tag: str, location: str = "end") -> bool:
    """Add a tag to a file.

    Args:
        filename: Name of file in brain directory.
        tag: Tag to add (with or without # prefix).
        location: Where to add tag - "end" (default), "start", or "after_title"

    Returns:
        True if tag was added, False if file not found.
    """
    tag = tag.lstrip("#").lower()
    brain_dir = config.BRAIN_DIR
    filepath = brain_dir / filename

    if not filepath.exists():
        return False

    content = filepath.read_text()
    tags = extract_tags(content)

    # Don't add if tag already exists
    if tag in tags:
        return True  # Already present, consider success

    tag_line = f" #{tag}"

    if location == "start":
        # Add at very beginning
        new_content = tag_line.lstrip() + " " + content
    elif location == "after_title":
        # Add after first # heading
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines.insert(i + 1, tag_line)
                break
        else:
            # No title found, add at start
            lines.insert(0, tag_line)
        new_content = "\n".join(lines)
    else:  # "end"
        # Add at end of file
        new_content = content.rstrip() + tag_line + "\n"

    filepath.write_text(new_content)
    return True
