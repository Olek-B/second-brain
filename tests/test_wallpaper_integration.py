"""Integration tests for wallpaper compositing."""

from pathlib import Path
from unittest.mock import patch

from second_brain import config
from second_brain.wallpaper.overlays import render_todo_overlay, render_rss_overlay
from second_brain.wallpaper.utils import _parse_todos


class TestWallpaperIntegration:
    """Integration tests for wallpaper."""

    def test_parse_todos_empty_file(self, tmp_path: Path) -> None:
        """Test parsing empty todo file."""
        todo_file = tmp_path / "todo.md"
        todo_file.write_text("")
        
        with patch.object(config, 'TODO_FILE', todo_file):
            todos = _parse_todos()
            assert todos == []

    def test_parse_todos_with_items(self, tmp_path: Path) -> None:
        """Test parsing todo file with items."""
        todo_file = tmp_path / "todo.md"
        todo_file.write_text("# Todo\n\n- [ ] task 1\n- [x] task 2\n- [ ] task 3\n")
        
        with patch.object(config, 'TODO_FILE', todo_file):
            todos = _parse_todos()
            # Returns all items (both checked and unchecked)
            assert len(todos) == 3
            # Check that we have 2 unchecked and 1 checked
            unchecked = [t for d, t in todos if not d]
            checked = [t for d, t in todos if d]
            assert len(unchecked) == 2
            assert len(checked) == 1

    def test_render_todo_overlay_no_todos(self, tmp_path: Path) -> None:
        """Test todo overlay returns None when no todos."""
        todo_file = tmp_path / "todo.md"
        todo_file.write_text("")
        output_path = tmp_path / "todo_overlay.png"
        
        with patch.object(config, 'TODO_FILE', todo_file):
            with patch.object(config, 'TODO_OVERLAY', output_path):
                result = render_todo_overlay()
                assert result is None

    def test_render_rss_overlay_no_feeds(self, tmp_path: Path) -> None:
        """Test RSS overlay returns None when no feeds."""
        rss_file = tmp_path / "rss.md"
        rss_file.write_text("")
        output_path = tmp_path / "rss_overlay.png"
        
        with patch.object(config, 'BRAIN_DIR', tmp_path):
            with patch.object(config, 'TODO_FILE', tmp_path / "todo.md"):
                result = render_rss_overlay(output_path=output_path)
                assert result is None
