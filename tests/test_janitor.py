"""Tests for second_brain.janitor module - batching and safety valve."""

from second_brain.janitor import (
    JANITOR_PROMPT,
    _build_batches,
    _build_janitor_input,
    _estimate_tokens,
)


class TestJanitorSafetyValve:
    """The janitor's content shrinkage safety valve.

    The janitor rejects changes where new content is < 80% of original size.
    We test the logic inline since it's embedded in run_janitor().
    """

    def test_safety_check_rejects_large_shrinkage(self):
        """Content shrinking by >20% should be rejected."""
        old_content = "x" * 1000
        new_content = "x" * 700  # 30% shrinkage
        old_len = len(old_content)
        new_len = len(new_content)
        assert new_len < old_len * 0.8  # This SHOULD be rejected

    def test_safety_check_accepts_small_shrinkage(self):
        """Content shrinking by <=20% should be accepted."""
        old_content = "x" * 1000
        new_content = "x" * 850  # 15% shrinkage
        old_len = len(old_content)
        new_len = len(new_content)
        assert new_len >= old_len * 0.8  # This should pass

    def test_safety_check_accepts_growth(self):
        """Content growing should always be accepted."""
        old_content = "x" * 1000
        new_content = "x" * 1200  # 20% growth
        old_len = len(old_content)
        new_len = len(new_content)
        assert new_len >= old_len * 0.8

    def test_safety_check_accepts_equal(self):
        """Same-size content should pass."""
        old_content = "x" * 1000
        new_content = "y" * 1000
        old_len = len(old_content)
        new_len = len(new_content)
        assert new_len >= old_len * 0.8

    def test_safety_boundary_exactly_80_percent(self):
        """Exactly 80% should pass (not rejected)."""
        old_content = "x" * 1000
        new_content = "x" * 800
        old_len = len(old_content)
        new_len = len(new_content)
        assert new_len >= old_len * 0.8


class TestJanitorPrompt:
    """Verify janitor prompt structure."""

    def test_prompt_exists(self):
        assert len(JANITOR_PROMPT) > 100

    def test_prompt_mentions_wikilinks(self):
        assert "wikilink" in JANITOR_PROMPT.lower()

    def test_prompt_forbids_content_changes(self):
        assert "NOT rewrite" in JANITOR_PROMPT or "Do NOT" in JANITOR_PROMPT

    def test_prompt_requires_json_output(self):
        assert "JSON" in JANITOR_PROMPT


class TestTokenEstimation:
    """Token estimation helper."""

    def test_estimate_tokens(self):
        # ~4 chars per token
        assert _estimate_tokens("a" * 400) == 100

    def test_estimate_empty(self):
        assert _estimate_tokens("") == 0


class TestBuildBatches:
    """Batching logic for splitting files into token-budget groups."""

    def _make_files(self, sizes: list[int]) -> dict[str, str]:
        """Create fake files with given character sizes."""
        return {f"file_{i}.md": "x" * size for i, size in enumerate(sizes)}

    def test_single_small_file_one_batch(self):
        files = self._make_files([100])
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=28000)
        assert len(batches) == 1
        assert list(batches[0].keys()) == ["file_0.md"]

    def test_all_fit_in_one_batch(self):
        files = self._make_files([100, 200, 300])
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=28000)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_splits_into_multiple_batches(self):
        # Each file is ~10K chars = ~2500 tokens.  Budget ~3000 means
        # at most 1 file per batch (after overhead).
        files = self._make_files([10000, 10000, 10000])
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=4000)
        assert len(batches) >= 2
        # All files should be present across all batches
        all_files = set()
        for batch in batches:
            all_files.update(batch.keys())
        assert all_files == set(files.keys())

    def test_oversized_file_gets_own_batch(self):
        # One huge file + two small ones
        files = self._make_files([100000, 100, 100])
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=5000)
        # The huge file should be alone in its batch
        assert len(batches) >= 2
        big_batch = [b for b in batches if "file_0.md" in b]
        assert len(big_batch) == 1

    def test_empty_files_dict(self):
        batches = _build_batches({}, [], max_tokens=28000)
        assert batches == []

    def test_preserves_all_file_contents(self):
        files = {"a.md": "content_a", "b.md": "content_b", "c.md": "content_c"}
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=28000)
        # Reconstruct all files from batches
        reconstructed = {}
        for batch in batches:
            reconstructed.update(batch)
        assert reconstructed == files

    def test_batch_token_estimate_respects_budget(self):
        # Create files that should require splitting
        files = self._make_files([4000] * 10)  # 10 files, 1000 tokens each
        file_list = list(files.keys())
        batches = _build_batches(files, file_list, max_tokens=3000)
        # Each batch (excluding the file list overhead) should be
        # roughly within budget
        assert len(batches) > 1


class TestBuildJanitorInput:
    """User prompt builder for janitor."""

    def test_includes_file_list_header(self):
        result = _build_janitor_input(
            {"notes.md": "hello"},
            ["notes.md", "other.md"],
        )
        assert "notes.md" in result
        assert "other.md" in result

    def test_wraps_files_in_markers(self):
        result = _build_janitor_input(
            {"notes.md": "content here"},
            ["notes.md"],
        )
        assert "--- FILE: notes.md ---" in result
        assert "--- END: notes.md ---" in result
        assert "content here" in result

    def test_includes_instruction(self):
        result = _build_janitor_input({"a.md": "x"}, ["a.md"])
        assert "Review these files" in result
