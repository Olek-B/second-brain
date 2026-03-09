"""Tests for multilingual linking in janitor."""

from second_brain.prompts import JANITOR_PROMPT


class TestMultilingualPrompt:
    """Test that the janitor prompt includes multilingual linking support."""

    def test_prompt_mentions_multilingual(self):
        """Check that the prompt mentions multilingual linking."""
        assert "MULTILINGUAL" in JANITOR_PROMPT
        assert "Polish" in JANITOR_PROMPT
        assert "English" in JANITOR_PROMPT

    def test_prompt_has_polish_english_examples(self):
        """Check that the prompt includes Polish-English example pairs."""
        # Should mention common Polish-English pairs
        assert "serwer" in JANITOR_PROMPT.lower()
        assert "server" in JANITOR_PROMPT.lower()
        assert "sieć" in JANITOR_PROMPT or "siec" in JANITOR_PROMPT.lower()
        assert "network" in JANITOR_PROMPT.lower()

    def test_prompt_has_linking_examples(self):
        """Check that the prompt shows how to link across languages."""
        # Should have concrete examples of cross-language linking
        assert "[[server]]" in JANITOR_PROMPT or "[[serwer]]" in JANITOR_PROMPT
