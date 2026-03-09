"""Tests for second_brain.daily_note module."""

import re
from datetime import datetime

from second_brain import config
from second_brain.daily_note import (
    create_daily_note,
    get_daily_note,
    get_today_filename,
    get_today_title,
    list_daily_notes,
)


class TestGetTodayFilename:
    """Daily note filename generation."""

    def test_format_is_yyyy_mm_dd(self):
        filename = get_today_filename()
        assert re.match(r"^\d{4}-\d{2}-\d{2}\.md$", filename)

    def test_ends_with_md(self):
        filename = get_today_filename()
        assert filename.endswith(".md")


class TestGetTodayTitle:
    """Daily note title generation."""

    def test_contains_weekday(self):
        title = get_today_title()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        assert any(day in title for day in weekdays)

    def test_contains_month(self):
        title = get_today_title()
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        assert any(month in title for month in months)

    def test_contains_year(self):
        title = get_today_title()
        year = str(datetime.now().year)
        assert year in title


class TestCreateDailyNote:
    """Daily note creation."""

    def test_creates_new_note(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            filename = get_today_filename()
            note_path, was_created = create_daily_note(open_editor=False)

            assert was_created
            assert note_path.exists()
            assert note_path.name == filename
        finally:
            config.BRAIN_DIR = old_dir

    def test_note_has_title(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            note_path, _ = create_daily_note(open_editor=False)
            content = note_path.read_text()

            title = get_today_title()
            assert f"# {title}" in content
        finally:
            config.BRAIN_DIR = old_dir

    def test_note_has_sections(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            note_path, _ = create_daily_note(open_editor=False)
            content = note_path.read_text()

            assert "## Notes" in content
            assert "## Tasks" in content
            assert "- [ ]" in content
        finally:
            config.BRAIN_DIR = old_dir

    def test_existing_note_not_overwritten(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            filename = get_today_filename()

            # Create note with custom content
            note_path = tmp_path / filename
            original_content = "# Custom Note\n\nMy custom content here."
            note_path.write_text(original_content)

            # Try to create daily note again
            _, was_created = create_daily_note(open_editor=False)

            assert not was_created
            assert note_path.read_text() == original_content
        finally:
            config.BRAIN_DIR = old_dir

    def test_creates_brain_dir_if_missing(self, tmp_path):
        brain_dir = tmp_path / "brain"
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = brain_dir
            assert not brain_dir.exists()

            create_daily_note(open_editor=False)

            assert brain_dir.exists()
        finally:
            config.BRAIN_DIR = old_dir


class TestGetDailyNote:
    """Get existing daily note by date."""

    def test_returns_none_for_missing(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            result = get_daily_note("2025-01-01")
            assert result is None
        finally:
            config.BRAIN_DIR = old_dir

    def test_returns_path_for_existing(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            (tmp_path / "2025-01-01.md").write_text("# Test")

            result = get_daily_note("2025-01-01")
            assert result == tmp_path / "2025-01-01.md"
        finally:
            config.BRAIN_DIR = old_dir


class TestListDailyNotes:
    """List all daily notes."""

    def test_empty_brain(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            notes = list_daily_notes()
            assert notes == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_returns_only_daily_notes(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            (tmp_path / "2025-01-01.md").write_text("# Daily")
            (tmp_path / "2025-01-02.md").write_text("# Daily")
            (tmp_path / "notes.md").write_text("# Regular note")
            (tmp_path / "dump.md").write_text("# Dump")

            notes = list_daily_notes()
            assert len(notes) == 2
            assert all(n.name.endswith(".md") for n in notes)
            assert all(re.match(r"^\d{4}-\d{2}-\d{2}\.md$", n.name) for n in notes)
        finally:
            config.BRAIN_DIR = old_dir

    def test_sorted_newest_first(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            (tmp_path / "2025-01-01.md").write_text("# Daily")
            (tmp_path / "2025-01-03.md").write_text("# Daily")
            (tmp_path / "2025-01-02.md").write_text("# Daily")

            notes = list_daily_notes()
            assert notes[0].name == "2025-01-03.md"
            assert notes[1].name == "2025-01-02.md"
            assert notes[2].name == "2025-01-01.md"
        finally:
            config.BRAIN_DIR = old_dir

    def test_excludes_dump(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            # dump.md matches the date pattern but should be excluded
            (tmp_path / "dump.md").write_text("# Dump")

            notes = list_daily_notes()
            assert len(notes) == 0
        finally:
            config.BRAIN_DIR = old_dir
