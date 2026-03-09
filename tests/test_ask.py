"""Tests for second_brain.ask module - AI Q&A / recall."""

import pytest
from second_brain.ask import (
    _INDEX_LINES,
    ANSWER_PROMPT,
    RELEVANCE_PROMPT,
    _build_answer_context,
    _build_file_index,
)
from second_brain.plugins import PluginManager, SecondBrainPlugin

# ---------------------------------------------------------------------------
# Prompt structure
# ---------------------------------------------------------------------------


class TestRelevancePrompt:
    """Verify the relevance-pass prompt structure."""

    def test_prompt_exists(self):
        assert len(RELEVANCE_PROMPT) > 100

    def test_prompt_mentions_json_output(self):
        assert "JSON" in RELEVANCE_PROMPT

    def test_prompt_mentions_files_key(self):
        assert '"files"' in RELEVANCE_PROMPT

    def test_prompt_limits_to_10_files(self):
        assert "10" in RELEVANCE_PROMPT

    def test_prompt_forbids_markdown_fences(self):
        assert "No markdown fences" in RELEVANCE_PROMPT

    def test_prompt_handles_empty_relevance(self):
        """Prompt should tell the LLM it can return an empty list."""
        assert "empty" in RELEVANCE_PROMPT.lower()


class TestAnswerPrompt:
    """Verify the answer-pass prompt structure."""

    def test_prompt_exists(self):
        assert len(ANSWER_PROMPT) > 100

    def test_prompt_mentions_wikilinks(self):
        assert "[[wikilink" in ANSWER_PROMPT.lower() or "[[" in ANSWER_PROMPT

    def test_prompt_forbids_hallucination(self):
        assert "ONLY" in ANSWER_PROMPT and "provided" in ANSWER_PROMPT

    def test_prompt_mentions_honesty(self):
        assert "honestly" in ANSWER_PROMPT.lower() or "say so" in ANSWER_PROMPT.lower()

    def test_prompt_mentions_citations(self):
        assert "cite" in ANSWER_PROMPT.lower()


# ---------------------------------------------------------------------------
# _build_file_index
# ---------------------------------------------------------------------------


class TestBuildFileIndex:
    """Compact index builder for the relevance pass."""

    def test_basic_index(self, tmp_path):
        (tmp_path / "notes.md").write_text("# Notes\nLine 2\nLine 3\n")
        result = _build_file_index(tmp_path, ["notes.md"])
        assert "--- notes.md ---" in result
        assert "# Notes" in result
        assert "Line 2" in result

    def test_index_truncates_to_n_lines(self, tmp_path):
        lines = [f"Line {i}" for i in range(20)]
        (tmp_path / "long.md").write_text("\n".join(lines))
        result = _build_file_index(tmp_path, ["long.md"])
        # Should include first _INDEX_LINES lines
        for i in range(_INDEX_LINES):
            assert f"Line {i}" in result
        # Should NOT include lines beyond the limit
        assert f"Line {_INDEX_LINES + 5}" not in result

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.md").write_text("Alpha content")
        (tmp_path / "b.md").write_text("Beta content")
        result = _build_file_index(tmp_path, ["a.md", "b.md"])
        assert "--- a.md ---" in result
        assert "--- b.md ---" in result
        assert "Alpha content" in result
        assert "Beta content" in result

    def test_missing_file_skipped(self, tmp_path):
        (tmp_path / "exists.md").write_text("Here")
        result = _build_file_index(tmp_path, ["exists.md", "nope.md"])
        assert "exists.md" in result
        assert "nope.md" not in result

    def test_empty_file_list(self, tmp_path):
        result = _build_file_index(tmp_path, [])
        assert result == ""

    def test_empty_file_content(self, tmp_path):
        (tmp_path / "empty.md").write_text("")
        result = _build_file_index(tmp_path, ["empty.md"])
        assert "--- empty.md ---" in result


# ---------------------------------------------------------------------------
# _build_answer_context
# ---------------------------------------------------------------------------


class TestBuildAnswerContext:
    """Full-content builder for the answer pass."""

    def test_basic_context(self, tmp_path):
        (tmp_path / "notes.md").write_text("# Notes\nFull content here.")
        result = _build_answer_context(tmp_path, ["notes.md"])
        assert "--- FILE: notes.md ---" in result
        assert "--- END: notes.md ---" in result
        assert "Full content here." in result

    def test_includes_full_content(self, tmp_path):
        lines = [f"Line {i}" for i in range(100)]
        full_text = "\n".join(lines)
        (tmp_path / "big.md").write_text(full_text)
        result = _build_answer_context(tmp_path, ["big.md"])
        # Should contain ALL lines, unlike the index builder
        assert "Line 0" in result
        assert "Line 99" in result

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.md").write_text("Content A")
        (tmp_path / "b.md").write_text("Content B")
        result = _build_answer_context(tmp_path, ["a.md", "b.md"])
        assert "--- FILE: a.md ---" in result
        assert "--- FILE: b.md ---" in result
        assert "--- END: a.md ---" in result
        assert "--- END: b.md ---" in result

    def test_missing_file_skipped(self, tmp_path):
        (tmp_path / "exists.md").write_text("Here")
        result = _build_answer_context(tmp_path, ["exists.md", "nope.md"])
        assert "exists.md" in result
        assert "nope.md" not in result

    def test_empty_file_list(self, tmp_path):
        result = _build_answer_context(tmp_path, [])
        assert result == ""


# ---------------------------------------------------------------------------
# Plugin hooks - existence and dispatch
# ---------------------------------------------------------------------------


class TestAskPluginHooks:
    """Verify ask-related plugin hooks exist and dispatch correctly."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from second_brain.plugins import reset_manager

        reset_manager()
        yield
        reset_manager()

    @pytest.fixture
    def manager(self):
        return PluginManager()

    def test_before_ask_default_returns_none(self):
        p = SecondBrainPlugin()
        assert p.before_ask("question?") is None

    def test_after_ask_default_returns_none(self):
        p = SecondBrainPlugin()
        assert p.after_ask("question?", "answer") is None

    def test_before_ask_mutation(self, manager):
        class RewriteQ(SecondBrainPlugin):
            def before_ask(self, question):
                return question.upper()

        manager._plugins.append(RewriteQ())
        result = manager.dispatch_before_ask("hello?")
        assert result == "HELLO?"

    def test_before_ask_none_passes_through(self, manager):
        class Noop(SecondBrainPlugin):
            def before_ask(self, question):
                return None

        manager._plugins.append(Noop())
        result = manager.dispatch_before_ask("hello?")
        assert result == "hello?"

    def test_after_ask_observational(self, manager):
        calls = []

        class Logger(SecondBrainPlugin):
            def after_ask(self, question, answer):
                calls.append((question, answer))

        manager._plugins.append(Logger())
        manager.dispatch_after_ask("q?", "a!")
        assert calls == [("q?", "a!")]

    def test_brain_api_has_ask_brain(self):
        from second_brain.plugins import BrainAPI

        api = BrainAPI()
        assert hasattr(api, "ask_brain")
        assert callable(api.ask_brain)
