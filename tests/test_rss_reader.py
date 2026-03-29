"""Tests for RSS reader functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from second_brain import config
from second_brain.rss_reader import RSSFeed, load_feeds, save_feeds


class TestRSSFeed:
    """Test RSSFeed dataclass."""

    def test_rssfeed_creation(self) -> None:
        """Test creating an RSSFeed object."""
        feed = RSSFeed(
            name="TestChannel",
            url="https://example.com/feed.xml",
            feed_type="standard",
        )
        assert feed.name == "TestChannel"
        assert feed.url == "https://example.com/feed.xml"
        assert feed.feed_type == "standard"


class TestFeedConfiguration:
    """Test feed configuration loading and saving."""

    def test_load_feeds_empty_file(self, tmp_path: Path) -> None:
        """Test loading from empty rss.md."""
        rss_file = tmp_path / "rss.md"
        rss_file.write_text("# RSS Feeds\n\nNo feeds configured.\n")

        with patch.object(config, 'BRAIN_DIR', tmp_path):
            feeds = load_feeds()

        assert feeds == []

    def test_load_feeds_with_youtube_channel(self, tmp_path: Path) -> None:
        """Test loading YouTube channel feed."""
        rss_file = tmp_path / "rss.md"
        rss_file.write_text(
            "# RSS Feeds\n\n"
            "## YouTube Channels\n\n"
            "- [[TestChannel]] - https://youtube.com/feeds/videos.xml?channel_id=abc123\n"
        )

        with patch.object(config, 'BRAIN_DIR', tmp_path):
            feeds = load_feeds()

        assert len(feeds) == 1
        assert feeds[0].name == "TestChannel"
        assert feeds[0].feed_type == "youtube"
        assert "channel_id=abc123" in feeds[0].url

    def test_save_feeds_creates_file(self, tmp_path: Path) -> None:
        """Test saving feeds creates rss.md."""
        rss_file = tmp_path / "rss.md"
        feeds = [
            RSSFeed(
                name="TestChannel",
                url="https://youtube.com/feeds/videos.xml?channel_id=abc123",
                feed_type="youtube",
            )
        ]

        with patch.object(config, 'BRAIN_DIR', tmp_path):
            save_feeds(feeds)

        assert rss_file.exists()
        content = rss_file.read_text()
        assert "# RSS Feeds" in content
        assert "TestChannel" in content
