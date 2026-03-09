"""Tests for second_brain.duplicates module."""

from second_brain import config
from second_brain.duplicates import (
    compute_file_signature,
    find_duplicates,
    get_similar_words,
    jaccard_similarity,
    suggest_merge,
)


class TestComputeFileSignature:
    """File signature computation."""

    def test_empty_content(self):
        assert compute_file_signature("") == set()

    def test_single_word(self):
        sig = compute_file_signature("dns")
        assert "dns" in sig

    def test_multiple_words(self):
        sig = compute_file_signature("dns server configuration")
        assert "dns" in sig
        assert "server" in sig
        assert "configuration" in sig

    def test_removes_stop_words(self):
        sig = compute_file_signature("the dns and server")
        assert "the" not in sig
        assert "and" not in sig
        assert "dns" in sig
        assert "server" in sig

    def test_lowercase(self):
        sig = compute_file_signature("DNS Server")
        assert "dns" in sig
        assert "server" in sig

    def test_ignores_short_words(self):
        sig = compute_file_signature("a an I be dns")
        assert "dns" in sig
        assert "a" not in sig
        assert "an" not in sig
        assert "be" not in sig

    def test_complex_content(self):
        content = """
        # DNS Configuration

        This is my DNS server setup.
        The server runs on port 53.
        """
        sig = compute_file_signature(content)
        assert "dns" in sig
        assert "configuration" in sig
        assert "server" in sig
        assert "port" in sig
        assert "the" not in sig  # stop word


class TestJaccardSimilarity:
    """Jaccard similarity calculation."""

    def test_identical_sets(self):
        s1 = {"a", "b", "c"}
        s2 = {"a", "b", "c"}
        assert jaccard_similarity(s1, s2) == 1.0

    def test_no_overlap(self):
        s1 = {"a", "b", "c"}
        s2 = {"d", "e", "f"}
        assert jaccard_similarity(s1, s2) == 0.0

    def test_partial_overlap(self):
        s1 = {"a", "b", "c"}
        s2 = {"b", "c", "d"}
        # Intersection: {b, c} = 2
        # Union: {a, b, c, d} = 4
        assert jaccard_similarity(s1, s2) == 0.5

    def test_empty_sets(self):
        assert jaccard_similarity(set(), set()) == 0.0
        assert jaccard_similarity({"a"}, set()) == 0.0
        assert jaccard_similarity(set(), {"a"}) == 0.0

    def test_subset(self):
        s1 = {"a", "b"}
        s2 = {"a", "b", "c", "d"}
        # Intersection: {a, b} = 2
        # Union: {a, b, c, d} = 4
        assert jaccard_similarity(s1, s2) == 0.5


class TestFindDuplicates:
    """Finding duplicate files."""

    def test_empty_brain(self, tmp_path):
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates()
            assert duplicates == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_no_duplicates(self, tmp_path):
        (tmp_path / "a.md").write_text("This is about DNS configuration")
        (tmp_path / "b.md").write_text("Different topic about cooking recipes")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates(threshold=0.5)
            assert duplicates == []
        finally:
            config.BRAIN_DIR = old_dir

    def test_finds_duplicates(self, tmp_path):
        content = "This is about DNS server configuration and setup notes for the homelab environment with detailed information"
        (tmp_path / "a.md").write_text(content)
        (tmp_path / "b.md").write_text(content + " with some extra words added here")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates(threshold=0.3)
            assert len(duplicates) == 1
            file1, file2, similarity = duplicates[0]
            assert file1 in ["a.md", "b.md"]
            assert file2 in ["a.md", "b.md"]
            assert file1 != file2
            assert similarity > 0.3
        finally:
            config.BRAIN_DIR = old_dir

    def test_excludes_dump(self, tmp_path):
        content = "DNS server configuration notes"
        (tmp_path / "dump.md").write_text(content)
        (tmp_path / "notes.md").write_text(content)
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates(threshold=0.3)
            # dump.md should be excluded
            for file1, file2, _ in duplicates:
                assert file1 != "dump.md"
                assert file2 != "dump.md"
        finally:
            config.BRAIN_DIR = old_dir

    def test_skips_short_files(self, tmp_path):
        (tmp_path / "short.md").write_text("dns")  # Too short
        (tmp_path / "long.md").write_text("dns " * 20)
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates(min_words=10)
            # short.md should be skipped
            for file1, file2, _ in duplicates:
                assert file1 != "short.md"
                assert file2 != "short.md"
        finally:
            config.BRAIN_DIR = old_dir

    def test_sorted_by_similarity(self, tmp_path):
        base = "DNS server configuration notes about setup"
        (tmp_path / "a.md").write_text(base)
        (tmp_path / "b.md").write_text(base + " extra words here")  # High similarity
        (tmp_path / "c.md").write_text("DNS something different")  # Lower similarity
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            duplicates = find_duplicates(threshold=0.1)
            if len(duplicates) >= 2:
                assert duplicates[0][2] >= duplicates[1][2]
        finally:
            config.BRAIN_DIR = old_dir


class TestGetSimilarWords:
    """Finding common words between files."""

    def test_common_words(self, tmp_path):
        (tmp_path / "a.md").write_text("dns server configuration")
        (tmp_path / "b.md").write_text("dns server notes")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            common = get_similar_words("a.md", "b.md")
            assert "dns" in common
            assert "server" in common
        finally:
            config.BRAIN_DIR = old_dir

    def test_no_common_words(self, tmp_path):
        (tmp_path / "a.md").write_text("dns server")
        (tmp_path / "b.md").write_text("cooking recipes")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            common = get_similar_words("a.md", "b.md")
            assert common == []
        finally:
            config.BRAIN_DIR = old_dir


class TestSuggestMerge:
    """Merge suggestion generation."""

    def test_basic_merge(self, tmp_path):
        (tmp_path / "a.md").write_text("# File A\n\nContent A")
        (tmp_path / "b.md").write_text("# File B\n\nContent B")
        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = tmp_path
            merged = suggest_merge("a.md", "b.md")
            assert "# File A" in merged
            assert "Content A" in merged
            assert "## Merged from b.md" in merged
            assert "Content B" in merged
        finally:
            config.BRAIN_DIR = old_dir
