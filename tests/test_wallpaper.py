"""Tests for second_brain.wallpaper module - todo parsing."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from second_brain import config
from second_brain.wallpaper import _parse_todos


class TestParseTodos:
    """Todo parsing from todo.md."""

    def test_parse_empty_file(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text("")
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            assert _parse_todos() == []
        finally:
            config.TODO_FILE = old

    def test_parse_no_file(self, tmp_path):
        old = config.TODO_FILE
        try:
            config.TODO_FILE = tmp_path / "nonexistent.md"
            assert _parse_todos() == []
        finally:
            config.TODO_FILE = old

    def test_parse_unchecked_items(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text("# Todo\n\n- [ ] Buy milk\n- [ ] Fix DNS\n")
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            items = _parse_todos()
            assert len(items) == 2
            assert items[0] == (False, "Buy milk")
            assert items[1] == (False, "Fix DNS")
        finally:
            config.TODO_FILE = old

    def test_parse_checked_items(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text("- [x] Done task\n- [X] Also done\n")
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            items = _parse_todos()
            assert len(items) == 2
            assert items[0] == (True, "Done task")
            assert items[1] == (True, "Also done")
        finally:
            config.TODO_FILE = old

    def test_parse_mixed_items(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text("- [ ] Pending\n- [x] Done\n- [ ] Also pending\n")
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            items = _parse_todos()
            assert len(items) == 3
            done_count = sum(1 for d, _ in items if d)
            pending_count = sum(1 for d, _ in items if not d)
            assert done_count == 1
            assert pending_count == 2
        finally:
            config.TODO_FILE = old

    def test_parse_ignores_non_todo_lines(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text("# Todo\n\nSome text here.\n\n- [ ] Real task\n\nMore text.\n")
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            items = _parse_todos()
            assert len(items) == 1
            assert items[0] == (False, "Real task")
        finally:
            config.TODO_FILE = old

    def test_parse_with_sections(self, tmp_path):
        todo = tmp_path / "todo.md"
        todo.write_text(
            "# Todo\n\n## Added - 2025-01-01 12:00\n"
            "- [ ] Task 1\n- [ ] Task 2\n\n"
            "## Added - 2025-01-02 12:00\n"
            "- [ ] Task 3\n- [x] Task 4\n"
        )
        old = config.TODO_FILE
        try:
            config.TODO_FILE = todo
            items = _parse_todos()
            assert len(items) == 4
        finally:
            config.TODO_FILE = old


class TestRSSOverlay:
    """Test RSS wallpaper overlay rendering."""

    @patch("second_brain.wallpaper.overlays.get_latest_entries")
    def test_render_rss_overlay_creates_file(self, mock_get: MagicMock, tmp_path: Path) -> None:
        """Test RSS overlay creates PNG file."""
        from second_brain.rss_reader import RSSEntry
        from second_brain.wallpaper import render_rss_overlay

        mock_get.return_value = [
            RSSEntry(
                title="Test Video Title",
                link="https://youtube.com/watch?v=abc",
                published=datetime(2026, 3, 29, 10, 0),
                source="Test Channel",
                summary=None,
            )
        ]

        output_path = tmp_path / "rss_overlay.png"
        result = render_rss_overlay(output_path=output_path)

        assert result is not None
        assert result.exists()
        assert result == output_path

    @patch("second_brain.wallpaper.overlays.get_latest_entries")
    def test_render_rss_overlay_returns_none_when_empty(
        self, mock_get: MagicMock, tmp_path: Path
    ) -> None:
        """Test RSS overlay returns None when no entries."""
        from second_brain.wallpaper import render_rss_overlay

        mock_get.return_value = []

        output_path = tmp_path / "rss_overlay.png"
        result = render_rss_overlay(output_path=output_path)

        assert result is None
