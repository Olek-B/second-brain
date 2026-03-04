"""The Janitor - weekly AI cleanup for formatting and missing wikilinks.

Scans all brain files, sends them to the LLM in a single batch,
and gets back only formatting fixes and missing [[wikilinks]].
No content changes, no merges, no deletions.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from groq import Groq

from . import config
from .librarian import _repair_json
from .plugins import get_manager


JANITOR_PROMPT = """\
You are a knowledge base janitor. You receive a collection of Markdown files \
from a personal knowledge base. Your ONLY job is to:

1. FIX FORMATTING: Normalize markdown formatting issues:
   - Ensure headers have a blank line before and after them
   - Ensure list items are consistently formatted
   - Fix broken markdown syntax (unclosed bold/italic, bad links)
   - Do NOT change wording, tone, or meaning. Do NOT add or remove content.

2. ADD MISSING WIKILINKS: If a file mentions a concept that matches another \
file's name/topic but doesn't have a [[wikilink]] to it, add one naturally \
into the existing text. For example, if "networking.md" mentions "DNS" and \
"dns.md" exists, change "DNS" to "[[dns]]" (or "[[dns|DNS]]" if case matters).
   - Only link to files that exist in the provided file list.
   - Don't over-link: if a file is already linked once in a section, don't \
link every subsequent mention.
   - Use the filename stem (without .md) inside the brackets.

3. OUTPUT FORMAT: Return a JSON object with ONLY the files that changed. \
If a file needs no changes, do NOT include it.
   - Use \\n for newlines in content strings.
   - Schema:
{"changes": [{"file": "filename.md", "content": "full corrected file content"}]}
   - If nothing needs changing, return: {"changes": []}

CRITICAL RULES:
- Do NOT rewrite, summarize, expand, or reorganize content.
- Do NOT add advice, explanations, introductions, or conclusions.
- Do NOT change the meaning or wording of any text.
- Do NOT merge or split files.
- Do NOT rename files.
- Do NOT remove any content.
- Do NOT add content that wasn't there before (except wikilink brackets).
- The output file should be nearly identical to the input — only formatting \
fixes and [[wikilink]] brackets added around existing words.
- ONLY fix formatting and add missing wikilinks.
- Return ONLY valid JSON.\
"""


def _build_janitor_input(
    files: dict[str, str], file_list: list[str]
) -> str:
    """Build the user prompt with all file contents."""
    parts = [
        "## All files in knowledge base:",
        ", ".join(file_list),
        "",
    ]

    for fname, content in files.items():
        parts.append(f"--- FILE: {fname} ---")
        parts.append(content)
        parts.append(f"--- END: {fname} ---")
        parts.append("")

    parts.append("Review these files. Fix formatting and add missing wikilinks.")
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English text)."""
    return len(text) // 4


def run_janitor(dry_run: bool = False) -> list[str]:
    """Run the janitor pass on all brain files.

    Args:
        dry_run: If True, print what would change but don't write files.

    Returns:
        List of summary strings describing changes made.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR
    file_list = config.get_brain_files()

    if not file_list:
        return ["No files to clean."]

    # Read all files
    files: dict[str, str] = {}
    for fname in file_list:
        fpath = brain_dir / fname
        files[fname] = fpath.read_text()

    # --- Hook: before_janitor_run ---
    pm.dispatch_before_janitor_run(files)

    # Build the prompt and estimate cost
    user_input = _build_janitor_input(files, file_list)
    input_tokens = _estimate_tokens(JANITOR_PROMPT + user_input)

    summaries = []
    summaries.append(f"Scanning {len(files)} files (~{input_tokens} input tokens)")

    # Check if this is too large (safety valve at ~30K tokens)
    if input_tokens > 30000:
        return [
            f"Brain is too large for a single pass ({input_tokens} est. tokens). "
            "Consider splitting into batches."
        ]

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": JANITOR_PROMPT},
            {"role": "user", "content": user_input},
        ],
        temperature=0.1,
        max_tokens=8192,
        response_format={"type": "json_object"},
    )

    response_text: str = response.choices[0].message.content or ""
    if not response_text:
        return ["LLM returned empty response."]

    # Parse response
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        repaired = _repair_json(response_text)
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError as e:
            return [f"Could not parse janitor response: {e}"]

    changes = result.get("changes", [])

    # --- Hook: after_janitor_llm (mutating) ---
    changes = pm.dispatch_after_janitor_llm(changes)

    if not changes:
        summaries.append("Everything clean -- no changes needed.")
        # --- Hook: after_janitor_run ---
        pm.dispatch_after_janitor_run(summaries)
        return summaries

    for change in changes:
        fname = change.get("file", "")
        new_content = change.get("content", "")

        if not fname or not new_content:
            continue

        # Safety: only touch files that actually exist
        fpath = brain_dir / fname
        if not fpath.exists():
            summaries.append(f"SKIP {fname} (doesn't exist)")
            # --- Hook: on_janitor_skip ---
            pm.dispatch_on_janitor_skip(fname, "doesn't exist")
            continue

        old_content = fpath.read_text()

        # Check what actually changed
        if old_content.strip() == new_content.strip():
            continue

        # Count the diff
        old_lines = set(old_content.splitlines())
        new_lines = set(new_content.splitlines())
        added = new_lines - old_lines
        removed = old_lines - new_lines

        # Safety: reject if too much content was removed
        # (janitor should only add links and fix formatting)
        old_len = len(old_content)
        new_len = len(new_content)
        if new_len < old_len * 0.8:
            reason = (
                f"content shrunk by "
                f"{100 - int(new_len / old_len * 100)}% -- too aggressive"
            )
            summaries.append(f"REJECT {fname} ({reason})")
            # --- Hook: on_janitor_reject ---
            pm.dispatch_on_janitor_reject(fname, reason)
            continue

        # Safety: reject if content grew too much (janitor shouldn't expand)
        if old_len > 0 and new_len > old_len * 1.3:
            reason = (
                f"content grew by "
                f"{int(new_len / old_len * 100) - 100}% -- janitor should "
                f"not add content"
            )
            summaries.append(f"REJECT {fname} ({reason})")
            pm.dispatch_on_janitor_reject(fname, reason)
            continue

        if dry_run:
            link_count = len(re.findall(r"\[\[", new_content)) - len(
                re.findall(r"\[\[", old_content)
            )
            summaries.append(
                f"WOULD FIX {fname} "
                f"(+{len(added)} -{len(removed)} lines, "
                f"+{link_count} links)"
            )
        else:
            # --- Hook: before_janitor_write (mutating) ---
            new_content = pm.dispatch_before_janitor_write(
                fname, old_content, new_content,
            )

            fpath.write_text(new_content)
            link_count = len(re.findall(r"\[\[", new_content)) - len(
                re.findall(r"\[\[", old_content)
            )
            summaries.append(
                f"FIXED {fname} "
                f"(+{len(added)} -{len(removed)} lines, "
                f"+{link_count} links)"
            )

            # --- Hook: after_janitor_write ---
            pm.dispatch_after_janitor_write(fname)

    if len(summaries) == 1:
        summaries.append("Everything clean -- no changes needed.")

    # Log the run
    log_path = brain_dir / ".janitor_log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log_path, "a") as f:
        f.write(f"\n[{timestamp}] {' | '.join(summaries)}\n")

    # --- Hook: after_janitor_run ---
    pm.dispatch_after_janitor_run(summaries)

    return summaries
