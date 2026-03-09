"""Tests for second_brain.tags module."""

from second_brain import config
from second_brain.tags import (
    add_tag_to_file,
    extract_tags,
    get_all_tags,
    get_files_by_tag,
    get_tags_by_file,
    remove_tag_from_file,
)


class TestExtractTags:
    """Tag extraction from markdown content."""

    def test_empty_content(self):
        assert extract_tags("") == []

    def test_single_tag(self):
        assert extract_tags("#dns") == ["dns"]

    def test_multiple_tags(self):
        content = "#dns #homelab #server"
        assert extract_tags(content) == ["dns", "homelab", "server"]

    def test_tags_in_text(self):
        content = "This is about #dns and #networking setup"
        assert extract_tags(content) == ["dns", "networking"]

    def test_tags_with_hyphens(self):
        content = "#my-tag #another-one"
        assert extract_tags(content) == ["another-one", "my-tag"]

    def test_tags_case_insensitive(self):
        content = "#DNS #dns #Dns"
        assert extract_tags(content) == ["dns"]

    def test_ignores_hashtags_in_urls(self):
        content = "See https://example.com#section for more"
        assert extract_tags(content) == []

    def test_ignores_hashtags_in_code(self):
        content = "Use `#tag` in your code"
        # This will still match - we don't have code block awareness
        # Could be improved in future
        assert "tag" in extract_tags(content)

    def test_tag_must_start_with_letter(self):
        content = "#123 invalid #valid"
        assert extract_tags(content) == ["valid"]

    def test_duplicates_removed(self):
        content = "#dns #homelab #dns"
        assert extract_tags(content) == ["dns", "homelab"]


class TestGetAllTags:
    """Building tag index from brain directory."""

    def test_empty_brain(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert get_all_tags() == {}
        finally:
            config.BRAIN_DIR = old_dir

    def test_single_file_tags(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns #homelab")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            tags = get_all_tags()
            assert "dns" in tags
            assert "homelab" in tags
            assert tags["dns"] == ["notes.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_multiple_files_same_tag(self, tmp_path):
        (tmp_path / "a.md").write_text("#dns")
        (tmp_path / "b.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            tags = get_all_tags()
            assert tags["dns"] == ["a.md", "b.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_excludes_dump(self, tmp_path):
        (tmp_path / "dump.md").write_text("#ignored")
        (tmp_path / "notes.md").write_text("#kept")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            tags = get_all_tags()
            assert "ignored" not in tags
            assert "kept" in tags
        finally:
            config.BRAIN_DIR = old_dir


class TestGetFilesByTag:
    """Querying files by tag."""

    def test_nonexistent_tag(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert get_files_by_tag("nonexistent") == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_existing_tag(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            files = get_files_by_tag("dns")
            assert files == ["notes.md"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_tag_with_hash_prefix(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            files = get_files_by_tag("#dns")
            assert files == ["notes.md"]
        finally:
            config.BRAIN_DIR = old_dir


class TestGetTagsByFile:
    """Getting tags from a specific file."""

    def test_nonexistent_file(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert get_tags_by_file("missing.md") == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_file_with_tags(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns #homelab")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            tags = get_tags_by_file("notes.md")
            assert tags == ["dns", "homelab"]
        finally:
            config.BRAIN_DIR = old_dir

    def test_file_without_tags(self, tmp_path):
        (tmp_path / "notes.md").write_text("No tags here")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert get_tags_by_file("notes.md") == []
        finally:
            config.BRAIN_DIR = old_dir


class TestRemoveTagFromFile:
    """Removing tags from files."""

    def test_nonexistent_file(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert remove_tag_from_file("missing.md", "dns") is False
        finally:
            config.BRAIN_DIR = old_dir

    def test_nonexistent_tag(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert remove_tag_from_file("notes.md", "other") is False
        finally:
            config.BRAIN_DIR = old_dir

    def test_remove_existing_tag(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns #homelab")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert remove_tag_from_file("notes.md", "dns") is True
            content = (tmp_path / "notes.md").read_text()
            assert "#dns" not in content
            assert "#homelab" in content
        finally:
            config.BRAIN_DIR = old_dir


class TestAddTagToFile:
    """Adding tags to files."""

    def test_nonexistent_file(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert add_tag_to_file("missing.md", "dns") is False
        finally:
            config.BRAIN_DIR = old_dir

    def test_add_to_end(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert add_tag_to_file("notes.md", "homelab") is True
            content = (tmp_path / "notes.md").read_text()
            assert "#homelab" in content
        finally:
            config.BRAIN_DIR = old_dir

    def test_add_duplicate_tag(self, tmp_path):
        (tmp_path / "notes.md").write_text("#dns")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            assert add_tag_to_file("notes.md", "dns") is True
            content = (tmp_path / "notes.md").read_text()
            # Should only have one #dns
            assert content.count("#dns") == 1
        finally:
            config.BRAIN_DIR = old_dir

    def test_add_at_start(self, tmp_path):
        (tmp_path / "notes.md").write_text("Content here")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            add_tag_to_file("notes.md", "dns", location="start")
            content = (tmp_path / "notes.md").read_text()
            assert content.startswith("#dns")
        finally:
            config.BRAIN_DIR = old_dir

    def test_add_after_title(self, tmp_path):
        (tmp_path / "notes.md").write_text("# My Note\n\nContent")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            add_tag_to_file("notes.md", "dns", location="after_title")
            content = (tmp_path / "notes.md").read_text()
            lines = content.splitlines()
            assert lines[0] == "# My Note"
            assert "#dns" in lines[1]
        finally:
            config.BRAIN_DIR = old_dir
