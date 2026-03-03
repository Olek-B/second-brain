"""The Librarian - AI-driven markdown organizer using Groq API."""

import json
import re
from datetime import datetime
from pathlib import Path

from groq import Groq

from . import config


SYSTEM_PROMPT = """\
You are a "Second Brain" librarian. Your job is to process a dump of raw \
thoughts and organize them into a structured knowledge base of Markdown files.

RULES:
1. You will receive:
   - A dump of raw thoughts (the user's input).
   - A list of EXISTING files already in the knowledge base.

2. For each distinct thought/topic in the dump:
   a) TODO DETECTION: If a thought contains a task, action item, or anything \
that implies something needs to be done (keywords like "todo", "need to", \
"should", "must", "have to", "want to", "look into", "figure out", "fix", \
"implement", "build", "set up", "learn", "explore", "check", "try", \
"remember to", "don't forget"), generate a "todo" action. Summarize the task \
into a short, punchy one-liner. Each todo item should be a SINGLE concise \
line like a checklist item, not a paragraph.
   b) SEMANTIC MATCH: If a thought relates to an existing file (e.g., \
a thought about "TLS certificates" matches a file named "https.md" or \
"networking.md"), generate an APPEND action to add content to that file.
   c) NEW THOUGHT: If no existing file matches, generate a CREATE action \
with a clean snake_case.md filename.
   NOTE: A single thought can produce BOTH a todo action AND an append/create \
action. The todo captures the task, the append/create captures the knowledge.

3. CONTENT FORMATTING:
   - For TODO actions: The content field must be a SHORT one-line summary \
of the task. No headers, no markdown formatting, just the task. Examples: \
"Research certificate pinning for mobile apps", "Set up mTLS between services".
   - For APPEND actions: Start content with a timestamped header: \
"## Update - YYYY-MM-DD HH:MM" followed by the organized content.
   - For CREATE actions: Start with a "# Title" header, then organized content.
   - ALWAYS insert [[Wikilinks]] to other relevant files from the existing \
files list. For example, if a thought about DNS mentions HTTP, and "https.md" \
exists, write "...related to [[https]]...". Use the filename without .md \
extension inside the wikilink brackets.
   - Be thorough but concise. Preserve all information from the dump.

4. OUTPUT FORMAT: You MUST return a valid JSON object.
   - Use \\n for newlines inside content strings. NEVER use literal newlines \
inside JSON string values.
   - Escape all special characters properly in JSON strings.
   - Action types are: "append", "create", or "todo".
   - For "todo" actions, target is always "todo.md".
   - Schema:
{"actions": [\
{"type": "todo", "target": "todo.md", "content": "Short task summary"}, \
{"type": "append", "target": "existing_file.md", "content": "## Update\\n\\nText here"}, \
{"type": "create", "target": "new_file.md", "content": "# Title\\n\\nText here"}]}

CRITICAL: Return ONLY valid JSON. No markdown fences, no explanation.\
"""


def build_user_prompt(dump_text: str, existing_files: list[str]) -> str:
    """Build the user prompt with dump content and file list."""
    files_list = "\n".join(f"  - {f}" for f in existing_files) if existing_files else "  (none - knowledge base is empty)"

    return f"""\
## Existing Files in Knowledge Base:
{files_list}

## Raw Thoughts Dump:
{dump_text}

## Current Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M")}

Process these thoughts and return the JSON actions.\
"""


def _repair_json(text: str) -> str:
    """Attempt to repair broken JSON from LLM output.

    Common issues:
    - Unescaped newlines inside string values
    - Unescaped backslashes
    - Trailing commas
    - Missing closing braces
    """
    # Strip markdown fences
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Extract just the JSON object if there's surrounding text
    # Find the first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    # Fix unescaped newlines inside JSON string values.
    # Walk through the string tracking whether we're inside a JSON string.
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]

        if ch == "\\" and in_string and i + 1 < len(text):
            # Escaped character -- keep both the backslash and next char
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"' :
            # Check this isn't an incorrectly unescaped quote inside a string.
            # A quote toggle is legitimate if it's at a structural position.
            if in_string:
                # Peek ahead: if the next non-whitespace char is a structural
                # JSON char (:, ,, }, ]) then this closes the string.
                rest = text[i + 1:].lstrip()
                if rest and rest[0] in ":,}]":
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                # Also handle end-of-text
                if not rest:
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                # Check if this quote starts a new key (the previous value ended)
                # Pattern: "..." "next_key" -- missing comma, but closing is valid
                if rest and rest[0] == '"':
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                # Otherwise it's an unescaped quote inside the string -- escape it
                result.append('\\"')
                i += 1
                continue
            else:
                in_string = True
                result.append(ch)
                i += 1
                continue

        if ch == "\n" and in_string:
            result.append("\\n")
            i += 1
            continue

        if ch == "\r" and in_string:
            result.append("\\r")
            i += 1
            continue

        if ch == "\t" and in_string:
            result.append("\\t")
            i += 1
            continue

        result.append(ch)
        i += 1

    text = "".join(result)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


def parse_llm_response(response_text: str) -> dict:
    """Parse the LLM response into a structured dict, handling edge cases."""
    text = response_text.strip()

    # First try parsing as-is
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        return _validate_actions(result)

    # Strip markdown fences and try again
    cleaned = text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    else:
        return _validate_actions(result)

    # Full repair pass
    repaired = _repair_json(text)
    try:
        result = json.loads(repaired)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Could not parse LLM response as JSON even after repair.\n"
            f"Parse error: {e}\n"
            f"First 800 chars of response:\n{text[:800]}"
        )

    return _validate_actions(result)


def _validate_actions(result: dict) -> dict:
    """Validate and normalize the parsed actions dict."""
    if "actions" not in result:
        raise ValueError(f"LLM response missing 'actions' key: {list(result.keys())}")

    for action in result["actions"]:
        if action.get("type") not in ("append", "create", "todo"):
            raise ValueError(f"Invalid action type: {action.get('type')}")
        if action["type"] == "todo":
            action["target"] = "todo.md"
            continue
        if not action.get("target", "").endswith(".md"):
            action["target"] = action["target"] + ".md"
        # Ensure snake_case for new files
        if action["type"] == "create":
            name = action["target"]
            name = re.sub(r"[^a-z0-9_.]", "_", name.lower())
            name = re.sub(r"_+", "_", name).strip("_")
            if not name.endswith(".md"):
                name += ".md"
            action["target"] = name

    return result


def process_dump(dump_text: str | None = None) -> dict:
    """Process the dump file through the Groq LLM and return actions.

    Args:
        dump_text: Optional raw text. If None, reads from dump.md.

    Returns:
        Dict with "actions" list of append/create operations.
    """
    if dump_text is None:
        dump_path = config.DUMP_FILE
        if not dump_path.exists():
            return {"actions": [], "error": "dump.md not found"}
        dump_text = dump_path.read_text().strip()

    if not dump_text:
        return {"actions": [], "error": "dump.md is empty"}

    existing_files = config.get_brain_files()
    api_key = config.get_groq_api_key()

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(dump_text, existing_files)},
        ],
        temperature=0.3,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    response_text: str = response.choices[0].message.content or ""
    if not response_text:
        raise ValueError("LLM returned empty response")
    return parse_llm_response(response_text)


def execute_actions(actions: dict) -> list[str]:
    """Execute the actions returned by the LLM.

    Returns list of summary strings describing what was done.
    """
    brain_dir = config.BRAIN_DIR
    brain_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    # Collect all todo items first so we can batch-write them
    todo_items: list[str] = []

    for action in actions.get("actions", []):
        if action["type"] == "todo":
            # Summarize to a single clean line
            line = action["content"].strip().split("\n")[0].strip()
            # Remove leading "- [ ] " or "- " if the LLM added it
            line = re.sub(r"^-\s*(\[.\]\s*)?", "", line).strip()
            if line:
                todo_items.append(line)
            continue

        target = brain_dir / action["target"]
        content = action["content"]

        if action["type"] == "append":
            if target.exists():
                existing = target.read_text()
                target.write_text(existing.rstrip() + "\n\n" + content + "\n")
                summaries.append(f"APPEND -> {action['target']}")
            else:
                # File doesn't exist despite match; create it instead
                target.write_text(content + "\n")
                summaries.append(f"CREATE (fallback) -> {action['target']}")

        elif action["type"] == "create":
            if target.exists():
                # Avoid overwriting; append instead
                existing = target.read_text()
                target.write_text(existing.rstrip() + "\n\n" + content + "\n")
                summaries.append(f"APPEND (exists) -> {action['target']}")
            else:
                target.write_text(content + "\n")
                summaries.append(f"CREATE -> {action['target']}")

    # Write todos to todo.md
    if todo_items:
        todo_path = config.TODO_FILE
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if todo_path.exists():
            existing = todo_path.read_text().rstrip()
        else:
            existing = "# Todo\n\nTasks extracted from brain dumps."

        new_lines = [f"\n\n## Added - {timestamp}"]
        for item in todo_items:
            new_lines.append(f"- [ ] {item}")

        todo_path.write_text(existing + "\n".join(new_lines) + "\n")
        summaries.append(f"TODO -> {len(todo_items)} task(s)")

    return summaries


def clear_dump():
    """Clear the dump file after processing."""
    if config.DUMP_FILE.exists():
        config.DUMP_FILE.write_text("")
