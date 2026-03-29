"""RSS feed reader for Second Brain.

Manages RSS feed configuration and fetching.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import feedparser

from second_brain import config

log = logging.getLogger("second_brain.rss_reader")

# Pattern to match feed lines: - [[name]] - url
_FEED_LINE_PATTERN = re.compile(r"^-\s*\[\[([^\]]+)\]\]\s*-\s*(.+)$")


@dataclass
class RSSFeed:
    """Represents an RSS feed configuration."""

    name: str
    url: str
    feed_type: str  # "youtube" or "standard"


@dataclass
class RSSEntry:
    """Represents a parsed RSS entry."""

    title: str
    link: str
    published: datetime
    source: str
    summary: str | None = None


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


def _parse_published(entry: dict) -> datetime:
    """Parse published date from feed entry."""
    published_parsed = entry.get('published_parsed')
    if published_parsed:
        return datetime(*published_parsed[:6])

    # Fallback to updated_parsed
    updated_parsed = entry.get('updated_parsed')
    if updated_parsed:
        return datetime(*updated_parsed[:6])

    # Default to now
    return datetime.now()


def fetch_feed(url: str) -> list[RSSEntry]:
    """Fetch and parse a single RSS/Atom feed.

    Args:
        url: URL of the RSS/Atom feed.

    Returns:
        List of RSSEntry objects, or empty list on error.
    """
    try:
        feed = feedparser.parse(url)

        if feed.bozo:
            log.warning("Bozo feed (parse warning) for %s: %s", url, feed.bozo_exception)

        entries: list[RSSEntry] = []
        feed_title = feed.feed.get('title', 'Unknown Feed')

        for entry in feed.entries:
            title = entry.get('title', 'No Title')
            link = entry.get('link', '')

            if not link:
                # Some feeds use id for link
                link = entry.get('id', '')

            published = _parse_published(entry)
            summary = entry.get('summary', entry.get('description', None))

            # Clean summary (remove HTML tags)
            if summary:
                summary = re.sub(r'<[^>]+>', '', summary).strip()
                # Truncate long summaries
                if len(summary) > 200:
                    summary = summary[:197] + "..."

            entries.append(RSSEntry(
                title=title,
                link=link,
                published=published,
                source=feed_title,
                summary=summary,
            ))

        return entries

    except Exception as e:
        log.error("Error fetching feed %s: %s", url, e)
        return []


def get_all_entries() -> list[RSSEntry]:
    """Fetch all entries from all configured feeds.

    Returns:
        List of all RSSEntry objects, sorted by published date (newest first).
    """
    feeds = load_feeds()
    all_entries: list[RSSEntry] = []

    for feed in feeds:
        entries = fetch_feed(feed.url)
        all_entries.extend(entries)

    # Sort by published date (newest first)
    all_entries.sort(key=lambda e: e.published, reverse=True)

    return all_entries


def get_latest_entries(n: int = 7) -> list[RSSEntry]:
    """Get the N most recent entries from all feeds.

    Args:
        n: Number of entries to return (default 7).

    Returns:
        List of N most recent RSSEntry objects.
    """
    all_entries = get_all_entries()
    return all_entries[:n]
