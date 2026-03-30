"""Custom widgets for Second Brain TUI."""

import re
from urllib.parse import quote, urlparse, parse_qs

from textual.message import Message
from textual.widgets import ListView, ListItem, Label, Markdown

from ..plugins import get_manager
from .styles import PREVIEW_PANE_CSS

# Pattern to find [[wikilinks]] including [[target|display text]] form.
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# Pattern to find markdown links: [text](url)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Marker that the AI appends to lines it considers deleted.
DELETE_MARKER = "<!-- DELETE -->"
_DELETE_MARKER_RE = re.compile(r"\s*<!--\s*DELETE\s*-->\s*$")


def _filter_deleted_lines(text: str) -> str:
    """Remove lines marked with <!-- DELETE --> from display text."""
    return "\n".join(line for line in text.splitlines() if not _DELETE_MARKER_RE.search(line))


def _wikilinks_to_md_links(text: str, valid_files: set[str] | None = None) -> str:
    """Convert [[target]] and [[target|label]] to markdown links.

    Internal links (matching existing files) use a ``wiki:`` pseudo-scheme
    for the click handler to navigate within the app.

    External links (no matching file) become Wikipedia links with proper
    URL encoding for special characters (C++, C#, .NET, etc.).

    Also converts markdown [text](url) links to clickable format.
    """
    valid_files = valid_files or set()

    def _replace_wikilink(m: re.Match) -> str:
        target = m.group(1).strip()
        label = (m.group(2) or target).strip()
        target_normalized = target.lower().replace(" ", "_")

        if target_normalized in valid_files or target_normalized + ".md" in valid_files:
            return f"[{label}](wiki:{target})"

        wikipedia_search = f"https://en.wikipedia.org/wiki/Special:Search?search={quote(target)}"
        return f"[{label}]({wikipedia_search})"

    def _replace_markdown_link(m: re.Match) -> str:
        label = m.group(1).strip()
        url = m.group(2).strip()

        if url.startswith("wiki:"):
            return f"[{label}]({url})"

        if url.startswith(("http://", "https://")):
            return f"[{label}]({url})"

        return f"[{label}]({url})"

    text = _WIKILINK_RE.sub(_replace_wikilink, text)
    text = _MARKDOWN_LINK_RE.sub(_replace_markdown_link, text)

    return text


class FileList(ListView):
    """Sidebar list of brain markdown files."""

    pass


class WikiLinkClicked(Message):
    """Posted when a wikilink in the preview is clicked."""

    def __init__(self, target: str) -> None:
        self.target = target
        super().__init__()


class PreviewPane(Markdown):
    """Markdown-rendered file preview with clickable wikilinks."""

    DEFAULT_CSS = PREVIEW_PANE_CSS

    def __init__(self, valid_files: set[str] | None = None, **kwargs) -> None:
        super().__init__(open_links=False, **kwargs)
        self._valid_files = valid_files or set()

    def set_content(self, content: str) -> None:
        """Replace the preview content with rendered markdown.

        Lines marked with ``<!-- DELETE -->`` are filtered out before
        rendering so they are hidden from the user but remain in the
        underlying file on disk.
        """
        content = _filter_deleted_lines(content)
        md_content = _wikilinks_to_md_links(content, self._valid_files)
        self.update(md_content)

    def set_valid_files(self, valid_files: set[str]) -> None:
        """Update the set of valid internal files for link resolution."""
        self._valid_files = valid_files

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Intercept link clicks — navigate wikilinks, show feedback for external."""
        if event.href.startswith("wiki:"):
            target = event.href.removeprefix("wiki:")
            self.post_message(WikiLinkClicked(target))
            event.prevent_default()
            event.stop()
        elif "wikipedia.org" in event.href:
            try:
                parsed = urlparse(event.href)
                query = parse_qs(parsed.query)
                search_term = query.get("search", ["topic"])[0]
                self.app.call_from_thread(
                    self._set_status, f"Opening Wikipedia: {search_term}..."
                )  # type: ignore[attr-defined]
            except Exception:
                pass
        elif event.href.startswith(("http://", "https://")):
            try:
                parsed = urlparse(event.href)
                domain = parsed.netloc or parsed.path.split("/")[0]
                if domain.startswith("www."):
                    domain = domain[4:]
                self.app.call_from_thread(
                    self._set_status, f"Opening: {domain}"
                )  # type: ignore[attr-defined]

                pm = get_manager()
                pm.dispatch_on_external_link_clicked(event.href, domain)
            except Exception:
                pass
