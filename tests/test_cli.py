"""CLI command integration tests."""

import subprocess
import sys
from pathlib import Path


class TestCLI:
    """CLI command tests."""

    def test_help_command(self) -> None:
        """Test CLI help output."""
        result = subprocess.run(
            [sys.executable, "-m", "second_brain", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Second Brain" in result.stdout
        assert "commands:" in result.stdout.lower()

    def test_rss_list_empty(self, tmp_path: Path) -> None:
        """Test RSS list with no feeds."""
        # Create empty brain directory
        brain_dir = tmp_path / "brain"
        brain_dir.mkdir()
        
        result = subprocess.run(
            [
                sys.executable, "-m", "second_brain", "rss",
            ],
            capture_output=True,
            text=True,
        )
        # Should show "No RSS feeds configured" message
        assert result.returncode == 0

    def test_list_command(self, tmp_path: Path) -> None:
        """Test list command with empty brain."""
        brain_dir = tmp_path / "brain"
        brain_dir.mkdir()
        
        result = subprocess.run(
            [
                sys.executable, "-m", "second_brain", "list",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
