# RSS Reader Design Specification

**Date:** 2026-03-29  
**Status:** Approved

## Overview

Add RSS feed support to Second Brain for displaying YouTube subscriptions and other RSS feeds in both the TUI (as a feed browser) and on the wallpaper overlay (latest 5-7 items).

## Requirements

### Functional Requirements

1. **Feed Configuration**
   - Feeds stored in `~/Documents/brain/rss.md` as markdown
   - Support YouTube channel RSS feeds
   - Support standard RSS/Atom feeds
   - Each feed has: name, URL, optional type

2. **TUI Feed Browser**
   - Accessible via `r` keybind
   - Two-pane view: feeds on left, items on right
   - Click item to open URL in default browser
   - Auto-refresh feeds on TUI start (background thread)
   - Show latest items from selected feed or all feeds

3. **Wallpaper Overlay**
   - Display latest 5-7 items from all feeds
   - Position: left-middle of screen (below todo panel)
   - Show: title, source feed, truncated
   - Auto-update when graph is regenerated

4. **CLI Commands**
   - `second-brain rss` - List configured feeds
   - `second-brain rss --refresh` - Fetch and display latest entries
   - `second-brain rss --add <name> <url>` - Add new feed
   - `second-brain rss --remove <name>` - Remove feed

5. **No Read Tracking**
   - Always show latest items, no read/unread state
   - Simpler implementation, matches "always current" philosophy

### Non-Functional Requirements

- Feed fetching runs in background threads (non-blocking)
- Network errors handled gracefully (retry once, then skip)
- No external database - all state in markdown files
- Minimal dependencies (feedparser only)

## Architecture

### New Module: `second_brain/rss_reader.py`

```python
@dataclass
class RSSEntry:
    title: str
    link: str
    published: datetime
    source: str  # feed name
    summary: str | None

@dataclass
class RSSFeed:
    name: str
    url: str
    feed_type: str  # "youtube" or "standard"
    last_updated: datetime | None

# Core functions
def load_feeds() -> list[RSSFeed]
def save_feeds(feeds: list[RSSFeed]) -> None
def fetch_feed(url: str) -> list[RSSEntry]
def get_all_entries() -> list[RSSEntry]
def get_latest_entries(n: int = 7) -> list[RSSEntry]
```

### New File: `rss.md`

```markdown
# RSS Feeds

Configured feeds for the RSS reader.

## YouTube Channels

- [[channel_name]] - https://www.youtube.com/feeds/videos.xml?channel_id=XXX

## Other Feeds

- [[feed_name]] - https://example.com/rss.xml
```

### TUI Integration

- New `action_view_rss()` handler in `BrainApp`
- New `RSSBrowser` screen class (or reuse existing pane structure)
- Keybind `r` added to BINDINGS
- Auto-refresh on mount via `_auto_refresh_rss()` background worker

### Wallpaper Integration

- New `render_rss_overlay()` in `wallpaper.py`
- Modified `composite_wallpaper()` to include RSS layer
- Positioned below todo panel, left side

### CLI Integration

- New `rss` command in `__main__.py`
- Subcommands: list, add, remove, refresh

## Dependencies

Add to `pyproject.toml`:
```toml
dependencies = [
    "feedparser>=6.0.0",
    # ... existing deps
]
```

## Data Flow

```
rss.md (config)
    │
    ├─→ [RSS Reader] ─→ fetch_feed() ─→ parse RSS/Atom ─→ RSSEntry[]
    │                                             │
    │                                             ├─→ TUI feed browser
    │                                             │
    │                                             └─→ wallpaper overlay (latest 7)
    │
    └─→ CLI: rss --add/--remove/--list
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Invalid feed URL | Log warning, skip feed, show error in TUI status |
| Network timeout | Retry once with 5s timeout, skip on second failure |
| No feeds configured | Show setup instructions in TUI |
| Parse error | Log error, skip malformed entries |

## Testing Strategy

1. **Unit Tests**
   - `test_load_feeds()` - parse rss.md correctly
   - `test_save_feeds()` - write feeds back to markdown
   - `test_fetch_feed()` - mock HTTP response parsing
   - `test_get_latest_entries()` - sorting and limiting

2. **Integration Tests**
   - Wallpaper overlay renders with RSS data
   - TUI RSS view displays feeds and items
   - CLI commands work end-to-end

3. **Test Fixtures**
   - Sample RSS feeds (YouTube, standard RSS, Atom)
   - Sample rss.md file

## Success Criteria

- [ ] Can add/remove feeds via CLI
- [ ] TUI shows feed browser with `r` key
- [ ] Clicking items opens URLs in browser
- [ ] Wallpaper shows latest 5-7 items
- [ ] Feeds auto-refresh on TUI start
- [ ] All tests pass (400+)
- [ ] Ruff linting passes
- [ ] Mypy type checking passes

## Out of Scope

- Read/unread tracking
- Feed categories/folders
- Search within feed content
- Enclosure/media download
- Podcast-specific features
