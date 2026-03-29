"""Tests for RSS reader functionality."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from second_brain import config
from second_brain.rss_reader import RSSFeed, RSSEntry, fetch_feed, load_feeds, save_feeds


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


class TestFeedFetching:
    """Test RSS feed fetching and parsing."""

    @patch('second_brain.rss_reader.feedparser.parse')
    def test_fetch_feed_parses_entries(self, mock_parse: MagicMock) -> None:
        """Test fetching and parsing a feed."""
        # Mock feedparser response using MagicMock to support attribute access
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Test Channel'}
        mock_feed.entries = [
            {
                'title': 'Test Video',
                'link': 'https://youtube.com/watch?v=abc123',
                'published_parsed': (2026, 3, 29, 10, 0, 0, 0, 0, 0),
                'summary': 'Test description',
            }
        ]
        mock_parse.return_value = mock_feed

        entries = fetch_feed("https://youtube.com/feeds/videos.xml?channel_id=abc123")

        assert len(entries) == 1
        assert entries[0].title == "Test Video"
        assert entries[0].source == "Test Channel"
        assert entries[0].link == "https://youtube.com/watch?v=abc123"

    @patch('second_brain.rss_reader.feedparser.parse')
    def test_fetch_feed_handles_missing_summary(self, mock_parse: MagicMock) -> None:
        """Test fetching entry without summary."""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {'title': 'Blog'}
        mock_feed.entries = [
            {
                'title': 'No Summary',
                'link': 'https://example.com/post',
                'published_parsed': (2026, 3, 29, 10, 0, 0, 0, 0, 0),
            }
        ]
        mock_parse.return_value = mock_feed

        entries = fetch_feed("https://example.com/rss.xml")

        assert len(entries) == 1
        assert entries[0].summary is None

    @patch('second_brain.rss_reader.feedparser.parse')
    def test_fetch_feed_handles_errors(self, mock_parse: MagicMock) -> None:
        """Test fetching feed that raises exception."""
        mock_parse.side_effect = Exception("Network error")

        entries = fetch_feed("https://invalid-url.com/rss.xml")

        assert entries == []
