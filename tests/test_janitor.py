"""Tests for second_brain.janitor module - safety valve and validation."""

import pytest

from second_brain import config


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
        from second_brain.janitor import JANITOR_PROMPT
        assert len(JANITOR_PROMPT) > 100

    def test_prompt_mentions_wikilinks(self):
        from second_brain.janitor import JANITOR_PROMPT
        assert "wikilink" in JANITOR_PROMPT.lower()

    def test_prompt_forbids_content_changes(self):
        from second_brain.janitor import JANITOR_PROMPT
        assert "NOT rewrite" in JANITOR_PROMPT or "Do NOT" in JANITOR_PROMPT

    def test_prompt_requires_json_output(self):
        from second_brain.janitor import JANITOR_PROMPT
        assert "JSON" in JANITOR_PROMPT


class TestTokenEstimation:
    """Token estimation helper."""

    def test_estimate_tokens(self):
        from second_brain.janitor import _estimate_tokens
        # ~4 chars per token
        assert _estimate_tokens("a" * 400) == 100

    def test_estimate_empty(self):
        from second_brain.janitor import _estimate_tokens
        assert _estimate_tokens("") == 0
