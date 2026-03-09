"""AI Q&A - ask your Second Brain questions and get answers.

Two-pass approach:
  Pass 1 (Relevance): Send the question + a compact index of all brain files
    to the LLM. It returns the most relevant filenames.
  Pass 2 (Answer): Send the question + full content of the selected files
    to the LLM. It answers citing [[wikilinks]] to source files.
"""

import json

from groq import Groq

from . import config
from .librarian import _repair_json
from .plugins import get_manager
from .prompts import ANSWER_PROMPT, RELEVANCE_PROMPT

# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

_INDEX_LINES = 5  # first N lines per file for the compact index


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


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def ask_brain(question: str) -> str:
    """Ask the Second Brain a question and get an answer.

    Args:
        question: The user's question.

    Returns:
        The AI's answer as a string.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR
    file_list = config.get_brain_files()

    if not file_list:
        return "Your brain is empty — no files to search."

    # --- Hook: before_ask (mutating) ---
    question = pm.dispatch_before_ask(question)

    api_key = config.get_groq_api_key()
    client = Groq(api_key=api_key)

    # ------ Pass 1: Relevance scan ------
    file_index = _build_file_index(brain_dir, file_list)

    relevance_response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": RELEVANCE_PROMPT},
            {
                "role": "user",
                "content": (f"## Question:\n{question}\n\n## File Index:\n{file_index}"),
            },
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )

    relevance_text = relevance_response.choices[0].message.content or ""
    try:
        relevance = json.loads(relevance_text)
    except json.JSONDecodeError:
        repaired = _repair_json(relevance_text)
        try:
            relevance = json.loads(repaired)
        except json.JSONDecodeError:
            # Fall back to using all files
            relevance = {"files": file_list}

    relevant_files = relevance.get("files", [])

    # Validate: only keep files that actually exist
    relevant_files = [f for f in relevant_files if f in file_list]

    if not relevant_files:
        answer = (
            "I couldn't find any files in your brain that seem relevant "
            "to that question. Try rephrasing or adding notes about this topic."
        )
        pm.dispatch_after_ask(question, answer)
        return answer

    # ------ Pass 2: Answer ------
    context = _build_answer_context(brain_dir, relevant_files)

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

    # Add source attribution
    sources = ", ".join(f"[[{f.removesuffix('.md')}]]" for f in relevant_files)
    answer += f"\n\n---\n*Sources: {sources}*"

    # --- Hook: after_ask ---
    pm.dispatch_after_ask(question, answer)

    return answer
