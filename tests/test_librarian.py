"""Tests for second_brain.librarian module - JSON repair and parsing."""

import json

import pytest

from second_brain.librarian import (
    _repair_json,
    _validate_actions,
    parse_llm_response,
)


class TestRepairJson:
    """JSON repair function for broken LLM output."""

    def test_valid_json_unchanged(self):
        original = '{"actions": [{"type": "todo", "content": "test"}]}'
        result = _repair_json(original)
        assert json.loads(result) == json.loads(original)

    def test_strips_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _repair_json(text)
        assert json.loads(result) == {"key": "value"}

    def test_fixes_literal_newlines_in_strings(self):
        text = '{"key": "line1\nline2"}'
        result = _repair_json(text)
        parsed = json.loads(result)
        assert "line1" in parsed["key"]
        assert "line2" in parsed["key"]

    def test_fixes_tabs_in_strings(self):
        text = '{"key": "before\tafter"}'
        result = _repair_json(text)
        parsed = json.loads(result)
        assert "before" in parsed["key"]

    def test_removes_trailing_commas(self):
        text = '{"a": 1, "b": 2, }'
        result = _repair_json(text)
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}

    def test_removes_trailing_comma_in_array(self):
        text = '{"items": [1, 2, 3, ]}'
        result = _repair_json(text)
        parsed = json.loads(result)
        assert parsed == {"items": [1, 2, 3]}

    def test_extracts_json_from_surrounding_text(self):
        text = 'Here is the plan:\n{"actions": []}\nDone!'
        result = _repair_json(text)
        assert json.loads(result) == {"actions": []}

    def test_handles_escaped_chars(self):
        text = '{"key": "path\\\\to\\\\file"}'
        result = _repair_json(text)
        parsed = json.loads(result)
        assert "\\" in parsed["key"]

    def test_complex_broken_json(self):
        """Simulate typical LLM broken output."""
        text = '''```json
{
  "actions": [
    {"type": "todo", "content": "Fix the DNS config"},
    {"type": "append", "target": "networking.md",
     "description": "Add notes about DNS
troubleshooting",
     "excerpt": "raw text here",
     "wikilinks": ["dns"]},
  ]
}
```'''
        result = _repair_json(text)
        parsed = json.loads(result)
        assert len(parsed["actions"]) == 2


class TestValidateActions:
    """Action validation and normalization."""

    def test_valid_actions_pass_through(self):
        result = _validate_actions({
            "actions": [
                {"type": "todo", "content": "Test task"},
                {"type": "create", "target": "notes.md", "description": "test"},
            ]
        })
        assert len(result["actions"]) == 2

    def test_todo_gets_target_set(self):
        result = _validate_actions({
            "actions": [{"type": "todo", "content": "Test"}]
        })
        assert result["actions"][0]["target"] == "todo.md"

    def test_missing_md_extension_added(self):
        result = _validate_actions({
            "actions": [{"type": "append", "target": "notes"}]
        })
        assert result["actions"][0]["target"] == "notes.md"

    def test_create_normalized_to_snake_case(self):
        result = _validate_actions({
            "actions": [{"type": "create", "target": "My Cool Notes.md", "description": "test"}]
        })
        target = result["actions"][0]["target"]
        assert " " not in target
        assert target.endswith(".md")
        assert target == target.lower()

    def test_create_cleans_special_chars(self):
        result = _validate_actions({
            "actions": [{"type": "create", "target": "DNS (config)!.md", "description": "test"}]
        })
        target = result["actions"][0]["target"]
        # Should only contain [a-z0-9_.]
        import re
        assert re.match(r"^[a-z0-9_.]+$", target)

    def test_invalid_action_type_raises(self):
        with pytest.raises(ValueError, match="Invalid action type"):
            _validate_actions({
                "actions": [{"type": "delete", "target": "notes.md"}]
            })

    def test_missing_actions_key_raises(self):
        with pytest.raises(ValueError, match="missing 'actions'"):
            _validate_actions({"result": []})


class TestParseLlmResponse:
    """Full LLM response parsing pipeline."""

    def test_parse_clean_json(self):
        text = '{"actions": [{"type": "todo", "content": "Test"}]}'
        result = parse_llm_response(text)
        assert result["actions"][0]["type"] == "todo"

    def test_parse_json_with_fences(self):
        text = '```json\n{"actions": [{"type": "todo", "content": "Test"}]}\n```'
        result = parse_llm_response(text)
        assert result["actions"][0]["type"] == "todo"

    def test_parse_broken_json_with_repair(self):
        text = '{"actions": [{"type": "todo", "content": "line1\nline2"},]}'
        result = parse_llm_response(text)
        assert result["actions"][0]["type"] == "todo"

    def test_parse_completely_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_llm_response("This is not JSON at all, just plain text.")

    def test_parse_empty_actions(self):
        text = '{"actions": []}'
        result = parse_llm_response(text)
        assert result["actions"] == []

    def test_parse_multiple_action_types(self):
        text = json.dumps({
            "actions": [
                {"type": "todo", "content": "Buy milk"},
                {"type": "create", "target": "shopping.md",
                 "description": "Shopping list", "excerpt": "buy milk"},
                {"type": "append", "target": "notes.md",
                 "description": "Add item", "excerpt": "note text"},
            ]
        })
        result = parse_llm_response(text)
        types = [a["type"] for a in result["actions"]]
        assert "todo" in types
        assert "create" in types
        assert "append" in types
