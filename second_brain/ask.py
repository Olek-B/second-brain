"""AI Q&A - ask your Second Brain questions and get answers.

Two-pass approach with iterative file loading:
  Pass 1 (Relevance): Send the question + a compact index of all brain files
    to the LLM. It returns the most relevant filenames with scores.
  Pass 2 (Answer): Send the question + full content of the selected files
    to the LLM. It answers citing [[wikilinks]] to source files.
  Iteration: If the answer indicates more files are needed, load additional
    files and retry (up to max_iterations).
"""

import json
import re

from groq import Groq

from . import config
from .librarian import _repair_json
from .plugins import get_manager
from .prompts import ANSWER_PROMPT, RELEVANCE_PROMPT

# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

_INDEX_LINES = 5  # first N lines per file for the compact index
_MAX_ITERATIONS = 3  # Maximum times to fetch more files
_INITIAL_FILES = 5  # Initial number of files to load
_ADDITIONAL_FILES = 3  # Additional files to load per iteration


def _build_file_index(brain_dir, file_list: list[str]) -> str:
    """Build a compact index: filename + first few lines of each file."""
    parts = []
    for fname in file_list:
        fpath = brain_dir / fname
        if not fpath.exists():
            continue
        content = fpath.read_text()
        lines = content.splitlines()[:_INDEX_LINES]
        preview = "\n".join(lines)
        parts.append(f"--- {fname} ---\n{preview}")
    return "\n\n".join(parts)


def _build_answer_context(brain_dir, file_list: list[str]) -> str:
    """Build the full context for the answer pass."""
    parts = []
    for fname in file_list:
        fpath = brain_dir / fname
        if not fpath.exists():
            continue
        content = fpath.read_text()
        parts.append(f"--- FILE: {fname} ---\n{content}\n--- END: {fname} ---")
    return "\n\n".join(parts)


def _parse_relevance_response(relevance_text: str, all_files: list[str]) -> list[str]:
    """Parse the relevance response and return sorted file list.

    Handles both old format (just filenames) and new format (with scores).
    """
    try:
        relevance = json.loads(relevance_text)
    except json.JSONDecodeError:
        repaired = _repair_json(relevance_text)
        try:
            relevance = json.loads(repaired)
        except json.JSONDecodeError:
            # Fall back to using all files
            return list(all_files)

    files_data = relevance.get("files", [])

    # Handle new format with scores
    if files_data and isinstance(files_data[0], dict):
        # Sort by score descending
        scored_files = sorted(
            [f for f in files_data if isinstance(f, dict)],
            key=lambda x: x.get("score", 0),
            reverse=True,
        )
        return [f["file"] for f in scored_files if "file" in f]

    # Handle old format (just filenames)
    return [f for f in files_data if isinstance(f, str)]


def _extract_more_files_request(answer: str) -> str | None:
    """Check if the answer requests more files.

    Looks for the marker: [NEED_MORE_FILES: reason]
    Returns the reason if found, None otherwise.
    """
    match = re.search(r"\[NEED_MORE_FILES:\s*([^\]]+)\]", answer)
    if match:
        return match.group(1).strip()
    return None


def ask_brain(question: str, max_iterations: int = _MAX_ITERATIONS) -> str:
    """Ask the Second Brain a question and get an answer.

    Uses an iterative approach: if the AI indicates it needs more files,
    automatically load additional relevant files and retry.

    Args:
        question: The user's question.
        max_iterations: Maximum number of times to fetch more files.

    Returns:
        The AI's answer as a string.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR
    all_files = config.get_brain_files()

    if not all_files:
        return "Your brain is empty — no files to search."

    # --- Hook: before_ask (mutating) ---
    question = pm.dispatch_before_ask(question)

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    # Track which files we've already loaded
    loaded_files: set[str] = set()
    iteration = 0
    more_files_reason: str | None = None

    while iteration < max_iterations:
        iteration += 1

        # ------ Pass 1: Relevance scan ------
        # Get files we haven't loaded yet
        remaining_files = [f for f in all_files if f not in loaded_files]

        if not remaining_files:
            # No more files to load
            break

        file_index = _build_file_index(brain_dir, remaining_files)

        # Build the relevance prompt with context about already-loaded files
        relevance_user_msg = f"## Question:\n{question}\n\n## File Index:\n{file_index}"
        if loaded_files and more_files_reason:
            relevance_user_msg += (
                f"\n\n## Already Loaded Files:\n"
                f"The following files have already been loaded: {', '.join(sorted(loaded_files))}\n"
                f"\n## Additional Context:\n"
                f"Looking for: {more_files_reason}\n"
                f"Please prioritize files that might contain information about: {more_files_reason}"
            )

        relevance_response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": RELEVANCE_PROMPT},
                {"role": "user", "content": relevance_user_msg},
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        relevance_text = relevance_response.choices[0].message.content or ""
        relevant_files = _parse_relevance_response(relevance_text, remaining_files)

        # Select top files we haven't loaded yet
        if iteration == 1:
            # First iteration: load initial batch
            new_files = [f for f in relevant_files if f not in loaded_files][
                :_INITIAL_FILES
            ]
        else:
            # Subsequent iterations: load additional files
            new_files = [f for f in relevant_files if f not in loaded_files][
                :_ADDITIONAL_FILES
            ]

        if not new_files:
            # No new relevant files found
            if iteration == 1:
                # First iteration with no results - use all files as fallback
                new_files = all_files[:_INITIAL_FILES]
            else:
                # Later iteration with no results - stop iterating
                break

        loaded_files.update(new_files)

        # ------ Pass 2: Answer ------
        context = _build_answer_context(brain_dir, sorted(loaded_files))

        answer_response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {
                    "role": "user",
                    "content": (f"## Question:\n{question}\n\n## Relevant Files:\n{context}"),
                },
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        answer = answer_response.choices[0].message.content or ""
        answer = answer.strip()

        if not answer:
            answer = "The AI returned an empty response. Try rephrasing your question."
            break

        # Check if the answer requests more files
        more_files_reason = _extract_more_files_request(answer)
        if more_files_reason and iteration < max_iterations:
            # Remove the marker from the answer and continue iterating
            answer = re.sub(r"\[NEED_MORE_FILES:[^\]]+\]\s*", "", answer).strip()
            # Continue to next iteration to load more files
            continue
        else:
            # Answer is complete or we've hit max iterations
            break

    if not answer:
        answer = (
            "I couldn't find enough information in your brain to answer "
            "that question adequately. Try rephrasing or adding more notes "
            "about this topic."
        )

    # Add source attribution
    sources = ", ".join(f"[[{f.removesuffix('.md')}]]" for f in sorted(loaded_files))
    answer += f"\n\n---\n*Sources: {sources}*"

    if iteration > 1:
        answer += f"\n*Loaded {len(loaded_files)} files over {iteration} iterations.*"

    # --- Hook: after_ask ---
    pm.dispatch_after_ask(question, answer)

    return answer
