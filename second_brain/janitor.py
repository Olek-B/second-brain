"""The Janitor - AI cleanup for formatting and missing wikilinks.

Scans all brain files, splits them into token-budget batches, sends each
batch to the LLM, and gets back only formatting fixes and missing
[[wikilinks]].  No content changes, no merges, no deletions.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from groq import Groq

from . import config
from .librarian import _repair_json
from .plugins import get_manager
from .prompts import JANITOR_PROMPT

# Maximum tokens per batch (prompt + file contents).  Leaves headroom for
# the system prompt (~500 tokens) and output (~8K tokens).
_MAX_BATCH_TOKENS = 28000


def _build_janitor_input(
    files: dict[str, str],
    file_list: list[str],
) -> str:
    """Build the user prompt with file contents for a batch."""
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


def _build_batches(
    files: dict[str, str],
    file_list: list[str],
    max_tokens: int = _MAX_BATCH_TOKENS,
) -> list[dict[str, str]]:
    """Split files into batches that fit within the token budget.

    Each batch is a dict of {filename: content}.  The file list header
    (all filenames for wikilink awareness) is included in every batch's
    token estimate.

    Args:
        files: All brain files {filename: content}.
        file_list: All filenames (for the header / wikilink list).
        max_tokens: Maximum estimated tokens per batch.

    Returns:
        List of file dicts, one per batch.
    """
    # Fixed overhead: system prompt + file list header
    header = "## All files in knowledge base:\n" + ", ".join(file_list) + "\n"
    overhead = _estimate_tokens(JANITOR_PROMPT + header)

    budget = max_tokens - overhead
    if budget < 500:
        # Even the overhead alone is near the limit; send everything as one
        return [files]

    batches: list[dict[str, str]] = []
    current_batch: dict[str, str] = {}
    current_tokens = 0

    for fname, content in files.items():
        # Token cost: file markers + content
        file_tokens = _estimate_tokens(f"--- FILE: {fname} ---\n{content}\n--- END: {fname} ---\n")

        # If a single file exceeds the budget, it still gets its own batch
        if current_batch and (current_tokens + file_tokens) > budget:
            batches.append(current_batch)
            current_batch = {}
            current_tokens = 0

        current_batch[fname] = content
        current_tokens += file_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


def _apply_changes(
    changes: list[dict],
    brain_dir: Path,
    dry_run: bool,
    pm,
) -> list[str]:
    """Apply a list of janitor changes, returning summary strings.

    This is the safety-valve + write logic extracted so it can be reused
    for each batch.
    """
    summaries: list[str] = []

    for change in changes:
        fname = change.get("file", "")
        new_content = change.get("content", "")

        if not fname or not new_content:
            continue

        # Safety: only touch files that actually exist
        fpath = brain_dir / fname
        if not fpath.exists():
            summaries.append(f"SKIP {fname} (doesn't exist)")
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
        old_len = len(old_content)
        new_len = len(new_content)
        if new_len < old_len * 0.8:
            reason = f"content shrunk by {100 - int(new_len / old_len * 100)}% -- too aggressive"
            summaries.append(f"REJECT {fname} ({reason})")
            pm.dispatch_on_janitor_reject(fname, reason)
            continue

        # Safety: reject if content grew too much
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
                f"WOULD FIX {fname} (+{len(added)} -{len(removed)} lines, +{link_count} links)"
            )
        else:
            # --- Hook: before_janitor_write (mutating) ---
            new_content = pm.dispatch_before_janitor_write(
                fname,
                old_content,
                new_content,
            )

            fpath.write_text(new_content)
            link_count = len(re.findall(r"\[\[", new_content)) - len(
                re.findall(r"\[\[", old_content)
            )
            summaries.append(
                f"FIXED {fname} (+{len(added)} -{len(removed)} lines, +{link_count} links)"
            )

            # --- Hook: after_janitor_write ---
            pm.dispatch_after_janitor_write(fname)

    return summaries


def run_janitor(dry_run: bool = False) -> list[str]:
    """Run the janitor pass on all brain files.

    Files are automatically split into token-budget batches so large
    knowledge bases are processed without hitting API limits.

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

    # Split into batches
    batches = _build_batches(files, file_list)

    total_tokens = _estimate_tokens(JANITOR_PROMPT + _build_janitor_input(files, file_list))

    summaries: list[str] = []
    summaries.append(
        f"Scanning {len(files)} files (~{total_tokens} tokens) in {len(batches)} batch(es)"
    )

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    any_changes = False

    for batch_idx, batch_files in enumerate(batches, 1):
        batch_label = f"[batch {batch_idx}/{len(batches)}] " if len(batches) > 1 else ""

        user_input = _build_janitor_input(batch_files, file_list)

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
            summaries.append(f"{batch_label}LLM returned empty response.")
            continue

        # Parse response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            repaired = _repair_json(response_text)
            try:
                result = json.loads(repaired)
            except json.JSONDecodeError as e:
                summaries.append(f"{batch_label}Could not parse response: {e}")
                continue

        changes = result.get("changes", [])

        # --- Hook: after_janitor_llm (mutating) ---
        changes = pm.dispatch_after_janitor_llm(changes)

        if not changes:
            summaries.append(f"{batch_label}clean -- no changes needed.")
            continue

        any_changes = True
        batch_summaries = _apply_changes(changes, brain_dir, dry_run, pm)
        for s in batch_summaries:
            summaries.append(f"{batch_label}{s}")

    if not any_changes and len(summaries) == 1:
        summaries.append("Everything clean -- no changes needed.")

    # Log the run with rotation (keep last 50 entries)
    log_path = brain_dir / ".janitor_log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"[{timestamp}] {' | '.join(summaries)}"

    # Read existing log and keep last 50 non-empty entries
    existing_lines = []
    if log_path.exists():
        content = log_path.read_text()
        existing_lines = [line for line in content.splitlines() if line.strip()]
        existing_lines = existing_lines[-50:]

    # Write back with new entry
    existing_lines.append(log_entry)
    log_path.write_text("\n".join(existing_lines) + "\n")

    # --- Hook: after_janitor_run ---
    pm.dispatch_after_janitor_run(summaries)

    return summaries
