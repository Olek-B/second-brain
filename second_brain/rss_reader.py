"""RSS feed reader for Second Brain.

Manages RSS feed configuration and fetching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from second_brain import config

# Pattern to match feed lines: - [[name]] - url
_FEED_LINE_PATTERN = re.compile(r"^-\s*\[\[([^\]]+)\]\]\s*-\s*(.+)$")


@dataclass
class RSSFeed:
    """Represents an RSS feed configuration."""

    name: str
    url: str
    feed_type: str  # "youtube" or "standard"


def get_rss_file_path() -> Path:
    """Get path to rss.md configuration file."""
    return config.BRAIN_DIR / "rss.md"


def load_feeds() -> list[RSSFeed]:
    """Load configured feeds from rss.md.
    
    Returns:
        List of RSSFeed objects parsed from the markdown file.
    """
    rss_file = get_rss_file_path()
    
    if not rss_file.exists():
        return []
    
    feeds: list[RSSFeed] = []
    content = rss_file.read_text()
    current_type = "standard"
    
    for line in content.splitlines():
        line = line.strip()
        
        # Detect section headers
        if line.startswith("## YouTube"):
            current_type = "youtube"
        elif line.startswith("##"):
            current_type = "standard"
        
        # Parse feed lines
        match = _FEED_LINE_PATTERN.match(line)
        if match:
            name = match.group(1).strip()
            url = match.group(2).strip()
            feeds.append(RSSFeed(
                name=name,
                url=url,
                feed_type=current_type,
            ))
    
    return feeds


def save_feeds(feeds: list[RSSFeed]) -> None:
    """Save feeds to rss.md configuration file.
    
    Args:
        feeds: List of RSSFeed objects to save.
    """
    rss_file = get_rss_file_path()
    
    lines = ["# RSS Feeds\n", "\n", "Configured feeds for the RSS reader.\n", "\n"]
    
    # Group by type
    youtube_feeds = [f for f in feeds if f.feed_type == "youtube"]
    standard_feeds = [f for f in feeds if f.feed_type != "youtube"]
    
    if youtube_feeds:
        lines.append("## YouTube Channels\n\n")
        for feed in youtube_feeds:
            lines.append(f"- [[{feed.name}]] - {feed.url}\n")
        lines.append("\n")
    
    if standard_feeds:
        lines.append("## Other Feeds\n\n")
        for feed in standard_feeds:
            lines.append(f"- [[{feed.name}]] - {feed.url}\n")
        lines.append("\n")
    
    rss_file.write_text("".join(lines))
