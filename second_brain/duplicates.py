"""Duplicate Detection - find potential duplicate notes using similarity analysis."""

import re

from . import config
from .plugins import get_manager


def compute_file_signature(content: str) -> set[str]:
    """Compute a signature (set of significant words) for a file.

    Args:
        content: File content.

    Returns:
        Set of lowercase words (excluding common stop words).
    """
    # Common English stop words to exclude
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
        "this",
        "but",
        "they",
        "have",
        "had",
        "what",
        "when",
        "where",
        "who",
        "which",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "can",
        "just",
        "should",
        "now",
        "i",
        "my",
        "me",
        "you",
        "your",
        "we",
        "our",
        "their",
        "them",
    }

    # Extract words (alphanumeric, at least 3 chars to avoid noise)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", content.lower())

    # Filter out stop words and return as set
    signature = {w for w in words if w not in stop_words}
    return signature


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Calculate Jaccard similarity between two sets.

    Args:
        set1: First set of words.
        set2: Second set of words.

    Returns:
        Similarity score between 0.0 (no overlap) and 1.0 (identical).
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def find_duplicates(
    threshold: float = 0.4,
    min_words: int = 10,
) -> list[tuple[str, str, float]]:
    """Find potential duplicate files in the brain directory.

    Args:
        threshold: Minimum similarity score to consider as duplicate (0.0-1.0).
        min_words: Minimum words in file to consider (skip very short files).

    Returns:
        List of (file1, file2, similarity_score) tuples, sorted by similarity.
    """
    pm = get_manager()
    brain_dir = config.BRAIN_DIR

    # --- Hook: before_find_duplicates ---
    pm.dispatch_before_find_duplicates(threshold, min_words)

    # Get all brain files
    md_files = sorted(f for f in brain_dir.glob("*.md") if f.name != "dump.md")

    # Compute signatures for all files
    signatures: dict[str, set[str]] = {}
    for md_file in md_files:
        content = md_file.read_text()
        words = re.findall(r"\b[a-zA-Z]+\b", content.lower())

        # Skip very short files
        if len(words) < min_words:
            continue

        signatures[md_file.name] = compute_file_signature(content)

    # Compare all pairs
    duplicates: list[tuple[str, str, float]] = []
    file_list = list(signatures.keys())

    for i, file1 in enumerate(file_list):
        for file2 in file_list[i + 1 :]:
            similarity = jaccard_similarity(
                signatures[file1],
                signatures[file2],
            )

            if similarity >= threshold:
                duplicates.append((file1, file2, similarity))

    # Sort by similarity (highest first)
    duplicates.sort(key=lambda x: x[2], reverse=True)

    # --- Hook: after_find_duplicates (mutating) ---
    result = pm.dispatch_after_find_duplicates(duplicates)
    if result is not None:
        duplicates = result

    return duplicates


def get_similar_words(
    file1: str,
    file2: str,
) -> list[str]:
    """Get the words that two files have in common.

    Args:
        file1: First filename.
        file2: Second filename.

    Returns:
        List of common words, sorted alphabetically.
    """
    brain_dir = config.BRAIN_DIR

    content1 = (brain_dir / file1).read_text()
    content2 = (brain_dir / file2).read_text()

    sig1 = compute_file_signature(content1)
    sig2 = compute_file_signature(content2)

    common = sig1 & sig2
    return sorted(common)


def suggest_merge(file1: str, file2: str) -> str:
    """Generate a suggested merge of two files.

    This is a simple concatenation with headers. For production use,
    a more sophisticated merge algorithm would be needed.

    Args:
        file1: First filename.
        file2: Second filename.

    Returns:
        Suggested merged content.
    """
    brain_dir = config.BRAIN_DIR

    content1 = (brain_dir / file1).read_text()
    content2 = (brain_dir / file2).read_text()

    # Simple merge: keep file1 as base, append file2 content under new header
    merged = f"{content1.rstrip()}\n\n---\n\n## Merged from {file2}\n\n{content2}\n"

    return merged
