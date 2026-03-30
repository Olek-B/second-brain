"""Tests for RSS reader functionality."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from second_brain import config
from second_brain.rss_reader import (
    RSSEntry,
    RSSFeed,
    fetch_feed,
    get_all_entries,
    get_latest_entries,
    load_feeds,
    save_feeds,
)


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

        with patch.object(config, "BRAIN_DIR", tmp_path):
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

        with patch.object(config, "BRAIN_DIR", tmp_path):
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

        with patch.object(config, "BRAIN_DIR", tmp_path):
            save_feeds(feeds)

        assert rss_file.exists()
        content = rss_file.read_text()
        assert "# RSS Feeds" in content
        assert "TestChannel" in content


class TestFeedFetching:
    """Test RSS feed fetching and parsing."""

    @patch("second_brain.rss_reader.feedparser.parse")
    def test_fetch_feed_parses_entries(self, mock_parse: MagicMock) -> None:
        """Test fetching and parsing a feed."""
        # Mock feedparser response using MagicMock to support attribute access
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Test Channel"}
        mock_feed.entries = [
            {
                "title": "Test Video",
                "link": "https://youtube.com/watch?v=abc123",
                "published_parsed": (2026, 3, 29, 10, 0, 0, 0, 0, 0),
                "summary": "Test description",
            }
        ]
        mock_parse.return_value = mock_feed

        entries = fetch_feed("https://youtube.com/feeds/videos.xml?channel_id=abc123")

        assert len(entries) == 1
        assert entries[0].title == "Test Video"
        assert entries[0].source == "Test Channel"
        assert entries[0].link == "https://youtube.com/watch?v=abc123"

    @patch("second_brain.rss_reader.feedparser.parse")
    def test_fetch_feed_handles_missing_summary(self, mock_parse: MagicMock) -> None:
        """Test fetching entry without summary."""
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed = {"title": "Blog"}
        mock_feed.entries = [
            {
                "title": "No Summary",
                "link": "https://example.com/post",
                "published_parsed": (2026, 3, 29, 10, 0, 0, 0, 0, 0),
            }
        ]
        mock_parse.return_value = mock_feed

        entries = fetch_feed("https://example.com/rss.xml")

        assert len(entries) == 1
        assert entries[0].summary is None

    @patch("second_brain.rss_reader.feedparser.parse")
    def test_fetch_feed_handles_errors(self, mock_parse: MagicMock) -> None:
        """Test fetching feed that raises exception."""
        mock_parse.side_effect = Exception("Network error")

        entries = fetch_feed("https://invalid-url.com/rss.xml")

        assert entries == []


class TestEntryAggregation:
    """Test entry aggregation across feeds."""

    @patch("second_brain.rss_reader.fetch_feed")
    @patch("second_brain.rss_reader.load_feeds")
    def test_get_all_entries_combines_feeds(
        self,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test getting all entries from multiple feeds."""
        # Mock configured feeds
        mock_load.return_value = [
            RSSFeed(name="Channel1", url="https://feed1.com/rss.xml", feed_type="youtube"),
            RSSFeed(name="Channel2", url="https://feed2.com/rss.xml", feed_type="youtube"),
        ]

        # Mock fetch responses
        def fetch_side_effect(url: str) -> list[RSSEntry]:
            if "feed1" in url:
                return [
                    RSSEntry(
                        title="Video 1",
                        link="https://feed1.com/video1",
                        published=datetime(2026, 3, 29, 10, 0),
                        source="Channel1",
                    )
                ]
            else:
                return [
                    RSSEntry(
                        title="Video 2",
                        link="https://feed2.com/video2",
                        published=datetime(2026, 3, 29, 11, 0),
                        source="Channel2",
                    )
                ]

        mock_fetch.side_effect = fetch_side_effect

        entries = get_all_entries()

        assert len(entries) == 2
        # Should be sorted by date (newest first)
        assert entries[0].title == "Video 2"
        assert entries[1].title == "Video 1"

    @patch("second_brain.rss_reader.get_all_entries")
    def test_get_latest_entries_limits_results(self, mock_all: MagicMock) -> None:
        """Test getting limited latest entries."""
        # get_all_entries returns entries sorted by date (newest first)
        # Entry 19 has hour=19 (newest), Entry 0 has hour=0 (oldest)
        mock_all.return_value = [
            RSSEntry(
                title=f"Entry {i}",
                link=f"https://example.com/{i}",
                published=datetime(2026, 3, 29, i, 0),
                source="Test",
            )
            for i in range(19, -1, -1)  # Reverse order: newest first
        ]

        latest = get_latest_entries(n=7)

        assert len(latest) == 7
        # Should be newest first
        assert latest[0].title == "Entry 19"
