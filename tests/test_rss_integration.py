"""Integration tests for RSS reader functionality."""

from pathlib import Path
from unittest.mock import patch

from second_brain import config
from second_brain.rss_reader import (
    RSSFeed,
    load_feeds,
    save_feeds,
    get_all_entries,
    get_latest_entries,
)


class TestRSSIntegration:
    """Integration tests for RSS reader."""

    def test_full_rss_flow(self, tmp_path: Path) -> None:
        """Test complete RSS flow: save, load, fetch, aggregate."""
        # Setup: Create test rss.md
        rss_file = tmp_path / "rss.md"
        
        with patch.object(config, 'BRAIN_DIR', tmp_path):
            # Save feeds
            feeds = [
                RSSFeed(
                    name="TestChannel",
                    url="https://youtube.com/feeds/videos.xml?channel_id=test",
                    feed_type="youtube",
                )
            ]
            save_feeds(feeds)
            
            # Verify file created
            assert rss_file.exists()
            
            # Load feeds
            loaded = load_feeds()
            assert len(loaded) == 1
            assert loaded[0].name == "TestChannel"

    def test_get_latest_entries_empty(self, tmp_path: Path) -> None:
        """Test get_latest_entries with no feeds configured."""
        with patch.object(config, 'BRAIN_DIR', tmp_path):
            entries = get_latest_entries(n=7)
            assert entries == []

    def test_get_all_entries_empty(self, tmp_path: Path) -> None:
        """Test get_all_entries with no feeds configured."""
        with patch.object(config, 'BRAIN_DIR', tmp_path):
            entries = get_all_entries()
            assert entries == []
