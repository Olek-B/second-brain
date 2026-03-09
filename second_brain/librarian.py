"""The Librarian - AI-driven markdown organizer using Groq API.

Three-pass architecture:
  Pass 1 (Plan):   Reads dump + file list -> decides WHERE content goes
                   (create/append/todo), returns lightweight plan with no
                   heavy content, just descriptions and todo one-liners.
  Pass 2 (Write):  For each create/append action, sends the plan entry +
                   target file content as context -> returns cleaned-up
                   markdown that fits naturally into the file.
  Pass 3 (Review): Compares the writer's output against the raw excerpt,
                   strips anything the writer added that wasn't in the
                   original (invented info, advice, filler).
"""

import json
import re
from datetime import datetime

from groq import Groq

from . import config
from .plugins import get_manager
from .prompts import (
    PLAN_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    WRITE_SYSTEM_PROMPT,
)

# Marker appended to lines the AI marks for soft-deletion.
# The TUI renderer hides these lines but they remain in the file on disk.
DELETE_MARKER = "<!-- DELETE -->"


def _build_review_user_prompt(excerpt: str, writer_output: str) -> str:
    """Build the user prompt for the review pass."""
    return f"""\
## Original Raw Excerpt:
{excerpt}

## Writer's Output:
{writer_output}

Compare these two. If the writer added anything not in the original, \
return a corrected version. If it's fine, return the writer's output as-is.\
"""


# Maximum allowed growth ratio: writer output vs raw excerpt.
# If the writer produces more than 2.5x the excerpt length, fall back
# to a minimal version with just wikilinks injected.  Slightly generous
# to allow grammar fixes that may expand terse/garbled text.
_MAX_GROWTH_RATIO = 2.5


def _fallback_minimal(action: dict, timestamp: str) -> str:
    """Build a bare-minimum note from the raw excerpt + wikilinks.

    Used when the writer's output is rejected by the safety check.
    """
    excerpt = action.get("excerpt", "").strip()
    wikilinks = action.get("wikilinks", [])
    parts = []

    if action["type"] == "create":
        title = action["target"].replace(".md", "").replace("_", " ").title()
        parts.append(f"# {title}\n")
    else:
        desc = action.get("description", "Update")
        parts.append(f"## {desc}\n")
        parts.append(f"*{timestamp}*\n")

    # Inject wikilinks into the excerpt text where possible
    text = excerpt
    for wl in wikilinks:
        # Simple case-insensitive replacement of the first mention
        pattern = re.compile(re.escape(wl), re.IGNORECASE)
        text = pattern.sub(f"[[{wl}]]", text, count=1)

    parts.append(text)
    return "\n".join(parts)


def _build_plan_user_prompt(dump_text: str, existing_files: list[str]) -> str:
    """Build the user prompt for the planning pass."""
    files_list = (
        "\n".join(f"  - {f}" for f in existing_files)
        if existing_files
        else "  (none - knowledge base is empty)"
    )

    return f"""\
## Existing Files in Knowledge Base:
{files_list}

## Raw Thoughts Dump:
{dump_text}

Analyze these thoughts and return the JSON plan.\
"""


def _build_write_user_prompt(
    action: dict,
    existing_content: str | None,
    timestamp: str,
) -> str:
    """Build the user prompt for a single write action."""
    parts = []

    parts.append(f"## Action: {action['type'].upper()}")
    parts.append(f"## Target: {action['target']}")
    parts.append(f"## Description: {action.get('description', 'Write content')}")
    parts.append(f"## Timestamp: {timestamp}")

    wikilinks = action.get("wikilinks", [])
    if wikilinks:
        parts.append(f"## Wikilinks to include: {', '.join(f'[[{w}]]' for w in wikilinks)}")

    parts.append(f"\n## Raw Excerpt from Dump:\n{action.get('excerpt', '')}")

    if existing_content is not None:
        # For large files, send last 200 lines for context rather than entire file
        lines = existing_content.splitlines()
        if len(lines) > 200:
            parts.append(f"\n## Existing File Content (last 200 of {len(lines)} lines):")
            parts.append("\n".join(lines[-200:]))
        else:
            parts.append(f"\n## Existing File Content:\n{existing_content}")

    parts.append("\nWrite the markdown content now.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON repair + parsing (unchanged)
# ---------------------------------------------------------------------------


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
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]

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

        if ch == '"':
            # Check this isn't an incorrectly unescaped quote inside a string.
            if in_string:
                # Peek ahead: if the next non-whitespace char is a structural
                # JSON char (:, ,, }, ]) then this closes the string.
                rest = text[i + 1 :].lstrip()
                if rest and rest[0] in ":,}]":
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                if not rest:
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                if rest and rest[0] == '"':
                    in_string = False
                    result.append(ch)
                    i += 1
                    continue
                # Otherwise it's an unescaped quote inside the string
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
        if action.get("type") not in ("append", "create", "todo", "delete"):
            raise ValueError(f"Invalid action type: {action.get('type')}")
        if action["type"] == "todo":
            action["target"] = "todo.md"
            continue
        if action["type"] == "delete":
            # delete actions need a target file and a lines list
            if not action.get("target", "").endswith(".md"):
                action["target"] = action["target"] + ".md"
            if "lines" not in action:
                action["lines"] = []
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
        # Ensure tags field exists and is valid
        if "tags" not in action:
            action["tags"] = []
        elif not isinstance(action["tags"], list):
            # Try to repair if it's a string
            if isinstance(action["tags"], str):
                action["tags"] = [t.strip() for t in action["tags"].split(",") if t.strip()]
            else:
                action["tags"] = []

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def process_dump(dump_text: str | None = None) -> dict:
    """Process the dump file through 3 LLM passes and return actions with content.

    Pass 1: Plan — decide where each thought goes.
    Pass 2: Write — generate cleaned-up content for each create/append action.
    Pass 3: Review — compare against raw excerpt, strip any added content.

    Args:
        dump_text: Optional raw text. If None, reads from dump.md.

    Returns:
        Dict with "actions" list of append/create/todo operations,
        where create/append actions have their final "content" populated.
    """
    pm = get_manager()

    if dump_text is None:
        dump_path = config.DUMP_FILE
        if not dump_path.exists():
            return {"actions": [], "error": "dump.md not found"}
        dump_text = dump_path.read_text().strip()

    if not dump_text:
        return {"actions": [], "error": "dump.md is empty"}

    # --- Hook: before_process_dump (mutating) ---
    dump_text = pm.dispatch_before_process_dump(dump_text)

    existing_files = config.get_brain_files()
    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------ Pass 1: Plan ------
    try:
        plan_response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": _build_plan_user_prompt(dump_text, existing_files)},
            ],
            temperature=0.3,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        plan_text: str = plan_response.choices[0].message.content or ""
        if not plan_text:
            raise ValueError("LLM returned empty response for planning pass")

        plan = parse_llm_response(plan_text)
    except Exception as e:
        # --- Hook: on_plan_error ---
        pm.dispatch_on_plan_error(e)
        raise

    # --- Hook: after_plan (mutating) ---
    plan = pm.dispatch_after_plan(plan)

    # ------ Pass 2: Write content for each create/append action ------
    brain_dir = config.BRAIN_DIR
    write_actions = [a for a in plan["actions"] if a["type"] in ("create", "append")]

    for action in write_actions:
        target_path = brain_dir / action["target"]

        # Load existing file content for appends (and creates that hit existing files)
        existing_content = None
        if target_path.exists():
            existing_content = target_path.read_text()

        # --- Hook: before_write_action (mutating) ---
        action = pm.dispatch_before_write_action(action, existing_content)

        write_response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": WRITE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_write_user_prompt(
                        action,
                        existing_content,
                        timestamp,
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        content: str = write_response.choices[0].message.content or ""
        # Strip any accidental code fences the LLM might wrap around markdown
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:markdown|md)?\s*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
            content = content.strip()

        # ------ Pass 3: Review — catch writer overreach ------
        excerpt = action.get("excerpt", "").strip()
        excerpt_len = len(excerpt)

        # Safety check: if writer output is way too long, skip review
        # and fall back to a minimal version.
        if excerpt_len > 0 and len(content) > excerpt_len * _MAX_GROWTH_RATIO:
            content = _fallback_minimal(action, timestamp)
        elif excerpt_len > 0 and content:
            # Run the review pass
            try:
                review_response = client.chat.completions.create(
                    model=config.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": _build_review_user_prompt(
                                excerpt,
                                content,
                            ),
                        },
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                )

                reviewed: str = review_response.choices[0].message.content or ""
                reviewed = reviewed.strip()
                if reviewed.startswith("```"):
                    reviewed = re.sub(r"^```(?:markdown|md)?\s*\n?", "", reviewed)
                    reviewed = re.sub(r"\n?```\s*$", "", reviewed)
                    reviewed = reviewed.strip()

                if reviewed:
                    content = reviewed
            except Exception:
                # Review pass failed — keep the writer's output as-is.
                # Better to have slightly over-cleaned notes than nothing.
                pass

        action["content"] = content

        # --- Hook: after_write_action ---
        pm.dispatch_after_write_action(action)

    # --- Hook: after_process_dump ---
    pm.dispatch_after_process_dump(plan)

    return plan


def execute_actions(actions: dict) -> list[str]:
    """Execute the actions returned by the LLM.

    Returns list of summary strings describing what was done.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR
    brain_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    action_list = actions.get("actions", [])

    # --- Hook: before_execute_actions (mutating) ---
    action_list = pm.dispatch_before_execute_actions(action_list)

    # Collect all todo items first so we can batch-write them
    todo_items: list[str] = []

    for action in action_list:
        if action["type"] == "todo":
            # Summarize to a single clean line
            line = action["content"].strip().split("\n")[0].strip()
            # Remove leading "- [ ] " or "- " if the LLM added it
            line = re.sub(r"^-\s*(\[.\]\s*)?", "", line).strip()
            if line:
                todo_items.append(line)
            continue

        if action["type"] == "delete":
            # Soft-delete: append <!-- DELETE --> marker to matching lines
            target = brain_dir / action["target"]
            if not target.exists():
                summaries.append(f"SKIP (not found) -> {action['target']}")
                continue
            lines_to_delete: list[str] = action.get("lines", [])
            if not lines_to_delete:
                summaries.append(f"SKIP (no lines) -> {action['target']}")
                continue
            file_text = target.read_text()
            file_lines = file_text.splitlines()
            marked = 0
            for i, file_line in enumerate(file_lines):
                stripped = file_line.strip()
                # Skip lines already marked
                if stripped.endswith(DELETE_MARKER):
                    continue
                for del_line in lines_to_delete:
                    if stripped == del_line.strip():
                        file_lines[i] = file_line + "  " + DELETE_MARKER
                        marked += 1
                        break
            if marked:
                target.write_text("\n".join(file_lines) + "\n")
            summaries.append(f"DELETE -> {action['target']} ({marked} line(s) marked)")
            continue

        target = brain_dir / action["target"]
        content = action.get("content", "")

        if not content:
            summaries.append(f"SKIP (no content) -> {action['target']}")
            continue

        # --- Hook: before_write_file (mutating) ---
        content = pm.dispatch_before_write_file(action, target, content)

        summary = ""
        if action["type"] == "append":
            if target.exists():
                existing = target.read_text()
                target.write_text(existing.rstrip() + "\n\n" + content + "\n")
                summary = f"APPEND -> {action['target']}"
            else:
                # File doesn't exist despite match; create it instead
                target.write_text(content + "\n")
                summary = f"CREATE (fallback) -> {action['target']}"

        elif action["type"] == "create":
            if target.exists():
                # Avoid overwriting; append instead
                existing = target.read_text()
                target.write_text(existing.rstrip() + "\n\n" + content + "\n")
                summary = f"APPEND (exists) -> {action['target']}"
            else:
                target.write_text(content + "\n")
                summary = f"CREATE -> {action['target']}"

        summaries.append(summary)

        # Apply tags from the action to the file
        tags = action.get("tags", [])
        if tags and target.exists():
            from . import tags as tags_module

            for tag in tags:
                tags_module.add_tag_to_file(action["target"], tag, location="end")
            if tags:
                summary = f"{summary} (tags: {', '.join(tags)})"
                # Update the last summary with tag info
                summaries[-1] = summary

        # --- Hook: after_write_file ---
        pm.dispatch_after_write_file(action, target, summary)

    # Deduplicate todo items (case-insensitive) among themselves
    seen: set[str] = set()
    unique_todos: list[str] = []
    for item in todo_items:
        key = item.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_todos.append(item)
    todo_items = unique_todos

    # Write todos to todo.md
    if todo_items:
        # --- Hook: before_write_todos (mutating) ---
        todo_items = pm.dispatch_before_write_todos(todo_items)

    if todo_items:
        todo_path = config.TODO_FILE
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if todo_path.exists():
            existing = todo_path.read_text().rstrip()
        else:
            existing = "# Todo\n\nTasks extracted from brain dumps."

        # Deduplicate against existing todo.md items (exact match only)
        existing_items: set[str] = set()
        for eline in existing.splitlines():
            m = re.match(r"^- \[.\]\s*(.*)", eline)
            if m:
                existing_items.add(m.group(1).strip().lower())
        todo_items = [item for item in todo_items if item.strip().lower() not in existing_items]

        if not todo_items:
            summaries.append("TODO -> 0 task(s) (all duplicates)")
        else:
            new_lines = [f"\n\n## Added - {timestamp}"]
            for item in todo_items:
                new_lines.append(f"- [ ] {item}")

            todo_path.write_text(existing + "\n".join(new_lines) + "\n")
            summaries.append(f"TODO -> {len(todo_items)} task(s)")

            # --- Hook: after_write_todos ---
            pm.dispatch_after_write_todos(len(todo_items))

    # --- Hook: after_execute_actions ---
    pm.dispatch_after_execute_actions(summaries)

    return summaries


def clear_dump():
    """Clear the dump file after processing."""
    pm = get_manager()

    # --- Hook: before_clear_dump ---
    pm.dispatch_before_clear_dump()

    if config.DUMP_FILE.exists():
        config.DUMP_FILE.write_text("")

    # --- Hook: after_clear_dump ---
    pm.dispatch_after_clear_dump()
