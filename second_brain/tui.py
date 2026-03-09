"""Second Brain TUI - Textual-based terminal interface."""

import os
import re
import subprocess

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)

from . import config
from .plugins import get_manager

# Pattern to find [[wikilinks]] including [[target|display text]] form.
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# Marker that the AI appends to lines it considers deleted.
# Lines ending with this marker are kept in the file but hidden in the preview.
DELETE_MARKER = "<!-- DELETE -->"
_DELETE_MARKER_RE = re.compile(r"\s*<!--\s*DELETE\s*-->\s*$")


def _filter_deleted_lines(text: str) -> str:
    """Remove lines marked with <!-- DELETE --> from display text.

    The marker can appear at the end of any line (with optional surrounding
    whitespace).  Marked lines are stripped entirely so the preview renders
    as if they don't exist, but the underlying file is untouched.
    """
    return "\n".join(line for line in text.splitlines() if not _DELETE_MARKER_RE.search(line))


def _wikilinks_to_md_links(text: str, valid_files: set[str] | None = None) -> str:
    """Convert ``[[target]]`` and ``[[target|label]]`` to markdown links.

    Internal links (matching existing files) use a ``wiki:`` pseudo-scheme
    for the click handler to navigate within the app.

    External links (no matching file) become Wikipedia links with proper
    URL encoding for special characters (C++, C#, .NET, etc.).
    """
    from urllib.parse import quote

    valid_files = valid_files or set()

    def _replace(m: re.Match) -> str:
        target = m.group(1).strip()
        label = (m.group(2) or target).strip()
        target_normalized = target.lower().replace(" ", "_")

        # Check if it matches an internal file
        if target_normalized in valid_files or target_normalized + ".md" in valid_files:
            return f"[{label}](wiki:{target})"

        # External link -> Wikipedia (URL-encoded for special chars)
        wikipedia_search = f"https://en.wikipedia.org/wiki/Special:Search?search={quote(target)}"
        return f"[{label}]({wikipedia_search})"

    return _WIKILINK_RE.sub(_replace, text)


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

    can_focus = True

    DEFAULT_CSS = """
    PreviewPane {
        height: 1fr;
        border: round $surface;
        padding: 1;
        overflow-y: auto;
    }

    PreviewPane > MarkdownLink {
        color: $accent;
        text-style: underline;
    }

    PreviewPane > MarkdownLink:hover {
        color: $secondary;
        background: $surface;
    }
    """

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
            # External wiki link - show feedback before opening browser
            # Extract the search term from the URL
            try:
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(event.href)
                query = parse_qs(parsed.query)
                search_term = query.get("search", ["topic"])[0]
                self.app.call_from_thread(self._set_status, f"Opening Wikipedia: {search_term}...")  # type: ignore[attr-defined]
            except Exception:
                pass
            # Let Textual handle opening the browser


class BrainApp(App):
    """Second Brain TUI Application."""

    TITLE = "Second Brain"
    SUB_TITLE = ""

    CSS = """
    Screen {
        layout: horizontal;
    }

    #sidebar {
        width: 30;
        dock: left;
        border-right: solid $accent;
        padding: 0 1;
    }

    #sidebar-title {
        text-style: bold;
        color: $accent;
        padding: 1 0;
        text-align: center;
    }

    #main {
        width: 1fr;
        padding: 1 2;
    }

    #preview-title {
        text-style: bold;
        color: $secondary;
        padding: 0 0 1 0;
    }

    #status-bar {
        dock: bottom;
        height: 3;
        padding: 0 1;
        border-top: solid $surface;
        color: $text-muted;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem > Label {
        width: 100%;
    }

    ListView > ListItem.--highlight {
        background: $accent 20%;
    }

    #ask-input {
        dock: bottom;
        margin: 0 1;
        display: none;
    }

    #ask-input.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("e", "edit_file", "Edit in $EDITOR"),
        Binding("g", "view_graph", "Refresh Graph"),
        Binding("p", "process_dump", "Process Dump"),
        Binding("j", "run_janitor", "Janitor"),
        Binding("r", "refresh_list", "Refresh List"),
        Binding("d", "open_dump", "Edit Dump"),
        Binding("t", "pull_telegram", "Pull Telegram"),
        Binding("T", "view_todos", "View Todos"),
        Binding("n", "daily_note", "New Daily Note"),
        Binding("#", "view_tags", "View Tags"),
        Binding("D", "view_duplicates", "View Duplicates"),
        Binding("a", "ask_brain", "Ask Brain"),
    ]

    def __init__(self):
        super().__init__()
        self._files: list[str] = []
        self._selected_file: str | None = None
        self.sub_title = str(config.BRAIN_DIR)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static(" brain files", id="sidebar-title")
                yield FileList(id="file-list")
            with Vertical(id="main"):
                yield Static("Select a file to preview", id="preview-title")
                yield PreviewPane(id="preview", valid_files=set())
                yield Input(
                    placeholder="Ask your brain a question...",
                    id="ask-input",
                )
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_file_list()
        self._set_status(
            "Ready. [e]dit | [g]raph | [p]rocess | [d]ump | [a]sk | [t]elegram | [r]efresh | [q]uit"
        )

        # --- Hook: on_tui_start ---
        pm = get_manager()
        pm.dispatch_on_tui_start(self)

        # Auto-pull Telegram and process dump on startup
        self._auto_pull_telegram()

    @work(thread=True, exclusive=True)
    def _auto_pull_telegram(self) -> None:
        """Automatically pull Telegram messages and process dump on TUI start."""
        pm = get_manager()

        # Find the telegram_pull plugin
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is None:
            # Plugin not loaded, skip auto-pull
            return

        try:
            count = pull_plugin.do_pull()  # type: ignore[attr-defined]
            if count:
                self.app.call_from_thread(
                    self._set_status,
                    f" Pulled {count} Telegram message(s). Processing...",
                )
                # Auto-process the dump
                self.app.call_from_thread(self._auto_process_dump)
            else:
                self.app.call_from_thread(
                    self._set_status,
                    "Ready. [e]dit | [g]raph | [p]rocess | [d]ump | [a]sk | [t]elegram | [r]efresh | [q]uit",
                )
        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Telegram pull error: {e}")

    @work(thread=True, exclusive=True)
    def _auto_process_dump(self) -> None:
        """Process dump.md through the Librarian (auto-called after Telegram pull)."""
        self.app.call_from_thread(self._set_status, " Processing Telegram dump with AI...")

        try:
            from .librarian import clear_dump, execute_actions, process_dump

            actions = process_dump()

            if "error" in actions:
                self.app.call_from_thread(self._set_status, f" {actions['error']}")
                return

            summaries = execute_actions(actions)
            clear_dump()

            summary = " | ".join(summaries) if summaries else "No actions taken"
            self.app.call_from_thread(self._set_status, f" {summary}. Ready.")
            self.app.call_from_thread(self._refresh_file_list)

        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Process error: {e}")

    def on_unmount(self) -> None:
        # --- Hook: on_tui_stop ---
        pm = get_manager()
        pm.dispatch_on_tui_stop()

    def _refresh_file_list(self) -> None:
        """Reload files from brain directory into the sidebar."""
        self._files = config.get_brain_files()
        file_list = self.query_one("#file-list", FileList)
        file_list.clear()
        for fname in self._files:
            item = ListItem(Label(f" {fname}"))
            file_list.append(item)

        # Also check for dump.md
        dump_exists = config.DUMP_FILE.exists() and config.DUMP_FILE.read_text().strip()
        if dump_exists:
            self._set_status(" dump.md has content! Press [p] to process it.")

        # --- Hook: on_tui_refresh_list ---
        pm = get_manager()
        pm.dispatch_on_tui_refresh_list(self._files)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection in sidebar."""
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._files):
            fname = self._files[idx]
            self._selected_file = fname
            self._show_preview(fname)

            # --- Hook: on_file_selected ---
            pm = get_manager()
            pm.dispatch_on_file_selected(fname)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show preview when highlighting changes."""
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._files):
            fname = self._files[idx]
            self._selected_file = fname
            self._show_preview(fname)

    @on(WikiLinkClicked)
    def _on_wikilink_clicked(self, event: WikiLinkClicked) -> None:
        """Navigate to a wikilinked file when clicked."""
        target_fname = event.target
        if not target_fname.endswith(".md"):
            target_fname += ".md"

        # --- Hook: on_wikilink_clicked ---
        pm = get_manager()
        pm.dispatch_on_wikilink_clicked(event.target)

        # Try to find and select the file in the sidebar
        try:
            idx = self._files.index(target_fname)
            file_list = self.query_one("#file-list", FileList)
            file_list.index = idx
            self._selected_file = target_fname
            self._show_preview(target_fname)
            self._set_status(f"Navigated to {target_fname}")
        except ValueError:
            # File not found - this is an external wiki link
            # Open Wikipedia search for this topic
            import webbrowser
            from urllib.parse import quote

            wikipedia_url = (
                f"https://en.wikipedia.org/wiki/Special:Search?search={quote(event.target)}"
            )
            self._set_status(f"Opening Wikipedia: {event.target}...")
            webbrowser.open(wikipedia_url)

    def _show_preview(self, fname: str) -> None:
        """Display file content in the preview pane."""
        fpath = config.BRAIN_DIR / fname
        preview = self.query_one("#preview", PreviewPane)
        title = self.query_one("#preview-title", Static)

        title.update(f" {fname}")

        # Update valid files for wiki link resolution
        valid_files = {f.removesuffix(".md") for f in self._files}
        preview.set_valid_files(valid_files)

        if fpath.exists():
            content = fpath.read_text()

            # --- Hook: on_file_preview (mutating) ---
            pm = get_manager()
            content = pm.dispatch_on_file_preview(fname, content)

            # Add tags section
            from .tags import get_tags_by_file

            tags = get_tags_by_file(fname)
            if tags:
                content += "\n\n---\n\n**Tags:** "
                content += ", ".join(f"#{t}" for t in sorted(tags))

            # Add backlinks section
            from .graph import get_backlinks

            backlinks = get_backlinks(fname)
            if backlinks:
                content += "\n\n---\n\n**Backlinks:** "
                content += ", ".join(f"[[{bl.removesuffix('.md')}]]" for bl in sorted(backlinks))

            preview.set_content(content)
        else:
            preview.set_content("File not found")

    def _set_status(self, msg: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(msg)

    def action_edit_file(self) -> None:
        """Open selected file in $EDITOR."""
        if self._selected_file is None:
            self._set_status(" No file selected")
            return

        editor = os.environ.get("EDITOR", "nvim")
        fpath = config.BRAIN_DIR / self._selected_file

        # --- Hook: on_tui_edit_file ---
        pm = get_manager()
        pm.dispatch_on_tui_edit_file(self._selected_file)

        with self.app.suspend():
            subprocess.run([editor, str(fpath)])

        # Refresh preview after editing
        self._show_preview(self._selected_file)
        self._set_status(f"Returned from {editor}")

    def action_open_dump(self) -> None:
        """Open dump.md in $EDITOR."""
        editor = os.environ.get("EDITOR", "nvim")
        dump_path = config.DUMP_FILE
        if not dump_path.exists():
            dump_path.write_text("# Dump\n\nWrite your raw thoughts here...\n")

        with self.app.suspend():
            subprocess.run([editor, str(dump_path)])

        self._set_status("Dump file edited. Press [p] to process.")

    @work(thread=True)
    def action_process_dump(self) -> None:
        """Process dump.md through the Librarian."""
        self._set_status(" Processing dump.md with AI...")

        # --- Hook: before_tui_process_dump ---
        pm = get_manager()
        pm.dispatch_before_tui_process_dump()

        try:
            from .librarian import clear_dump, execute_actions, process_dump

            actions = process_dump()

            if "error" in actions:
                self.app.call_from_thread(self._set_status, f" {actions['error']}")
                return

            summaries = execute_actions(actions)
            clear_dump()

            summary = " | ".join(summaries) if summaries else "No actions taken"
            self.app.call_from_thread(self._set_status, f" {summary}")
            self.app.call_from_thread(self._refresh_file_list)

            # --- Hook: after_tui_process_dump ---
            pm.dispatch_after_tui_process_dump(summaries)

        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Error: {e}")

    @work(thread=True)
    def action_view_graph(self) -> None:
        """Generate graph and refresh wallpaper."""
        self._set_status(" Generating knowledge graph...")

        # --- Hook: before_tui_graph ---
        pm = get_manager()
        pm.dispatch_before_tui_graph()

        try:
            from .wallpaper import refresh_wallpaper

            result = refresh_wallpaper()
            self.app.call_from_thread(self._set_status, f" {result}")

            # --- Hook: after_tui_graph ---
            pm.dispatch_after_tui_graph(result)
        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Graph error: {e}")

    def action_refresh_list(self) -> None:
        """Refresh the file list."""
        self._refresh_file_list()
        self._set_status(" File list refreshed")

    @work(thread=True)
    def action_pull_telegram(self) -> None:
        """Pull messages from Telegram inbox into dump.md."""
        self._set_status(" Pulling Telegram messages...")

        pm = get_manager()
        # Find the telegram_pull plugin
        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is None:
            self.app.call_from_thread(
                self._set_status,
                " telegram_pull plugin not loaded. Check config.",
            )
            return

        try:
            count = pull_plugin.do_pull()  # type: ignore[attr-defined]
            if count:
                self.app.call_from_thread(
                    self._set_status,
                    f" Pulled {count} message(s). Press [p] to process dump.",
                )
                # Refresh to show dump.md has content
                self.app.call_from_thread(self._refresh_file_list)
            else:
                self.app.call_from_thread(self._set_status, " No new Telegram messages")
        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Telegram pull error: {e}")

    @work(thread=True)
    def action_run_janitor(self) -> None:
        """Run the AI janitor to fix formatting and add missing links."""
        self._set_status(" Running janitor (formatting + links)...")

        # --- Hook: before_tui_janitor ---
        pm = get_manager()
        pm.dispatch_before_tui_janitor()

        try:
            from .janitor import run_janitor

            summaries = run_janitor(dry_run=False)
            summary = " | ".join(summaries)
            self.app.call_from_thread(self._set_status, f" {summary}")
            self.app.call_from_thread(self._refresh_file_list)

            # Refresh preview if a file is selected
            if self._selected_file:
                self.app.call_from_thread(self._show_preview, self._selected_file)

            # --- Hook: after_tui_janitor ---
            pm.dispatch_after_tui_janitor(summaries)

        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Janitor error: {e}")

    def action_ask_brain(self) -> None:
        """Show the ask input field."""
        ask_input = self.query_one("#ask-input", Input)
        ask_input.add_class("visible")
        ask_input.focus()
        self._set_status("Type your question and press Enter. Escape to cancel.")

    def action_view_todos(self) -> None:
        """Show the todo list in the preview pane."""
        from .wallpaper import _parse_todos

        title = self.query_one("#preview-title", Static)
        preview = self.query_one("#preview", PreviewPane)

        title.update(" Todo List")

        items = _parse_todos()
        if not items:
            preview.set_content(
                "*No todo items found.*\n\nTasks are automatically extracted from your dumps when you process them."
            )
            self._set_status(" Todo list is empty")
            return

        # Build markdown todo list
        content = "## Pending Tasks\n\n"
        pending = [text for done, text in items if not done]
        completed = [text for done, text in items if done]

        if pending:
            content += "### To Do\n\n"
            for text in pending:
                content += f"- [ ] {text}\n"
            content += "\n"

        if completed:
            content += "### Completed\n\n"
            for text in completed:
                content += f"- [x] {text}\n"

        content += "\n---\n\n*Tip: Press `d` to edit todo.md directly, or use any markdown editor to toggle tasks.*"

        preview.set_content(content)
        self._set_status(f" Showing {len(pending)} pending, {len(completed)} completed tasks")

    def action_daily_note(self) -> None:
        """Create or open today's daily note."""
        from .daily_note import create_daily_note, get_today_filename

        filename = get_today_filename()
        note_path, was_created = create_daily_note(open_editor=False)

        if was_created:
            self._set_status(f" Created daily note: {filename}")
        else:
            self._set_status(f" Opened: {filename}")

        # Refresh file list and select the daily note
        self._refresh_file_list()

        # Find and select the daily note in the sidebar
        try:
            idx = self._files.index(filename)
            file_list = self.query_one("#file-list", FileList)
            file_list.index = idx
            self._selected_file = filename
            self._show_preview(filename)
        except ValueError:
            pass  # File might not be in list yet

    def action_view_tags(self) -> None:
        """Show all tags in the preview pane."""
        from .tags import get_all_tags

        title = self.query_one("#preview-title", Static)
        preview = self.query_one("#preview", PreviewPane)

        title.update(" Tags")

        tag_index = get_all_tags()
        if not tag_index:
            preview.set_content(
                "*No tags found.*\n\nAdd #tags to your notes like:\n- #dns\n- #homelab\n- #todo\n\nTags are automatically extracted from all files."
            )
            self._set_status(" No tags found")
            return

        # Build markdown tag list
        content = "## All Tags\n\n"
        for tag in sorted(tag_index.keys()):
            files = tag_index[tag]
            content += f"### #{tag} ({len(files)} file{'s' if len(files) > 1 else ''})\n\n"
            for f in files:
                content += f"- [[{f.removesuffix('.md')}]]\n"
            content += "\n"

        preview.set_content(content)
        self._set_status(f" Showing {len(tag_index)} tags")

    def action_view_duplicates(self) -> None:
        """Show potential duplicates in the preview pane."""
        from .duplicates import find_duplicates

        title = self.query_one("#preview-title", Static)
        preview = self.query_one("#preview", PreviewPane)

        title.update(" Potential Duplicates")

        duplicates = find_duplicates(threshold=0.3)
        if not duplicates:
            preview.set_content(
                "*No potential duplicates found.*\n\nYour notes look unique! Files are compared using word overlap analysis."
            )
            self._set_status(" No duplicates found")
            return

        # Build markdown duplicates report
        content = "## Potential Duplicates\n\n"
        content += "Files with significant word overlap (may cover similar topics):\n\n"

        for file1, file2, similarity in duplicates:
            pct = int(similarity * 100)
            content += f"### {file1} + {file2} ({pct}% similar)\n\n"

            # Get common words
            from .duplicates import get_similar_words

            common = get_similar_words(file1, file2)
            if common:
                content += f"**Common topics:** {', '.join(common[:10])}\n\n"

            content += (
                "*Tip: Review these files and consider merging if they cover the same topic.*\n\n"
            )
            content += "---\n\n"

        preview.set_content(content)
        self._set_status(f" Found {len(duplicates)} potential duplicate pairs")

    @on(Input.Submitted, "#ask-input")
    def _on_ask_submitted(self, event: Input.Submitted) -> None:
        """Handle ask input submission."""
        question = event.value.strip()
        ask_input = self.query_one("#ask-input", Input)
        ask_input.value = ""
        ask_input.remove_class("visible")

        if not question:
            self._set_status("No question entered.")
            return

        self._do_ask(question)

    def on_key(self, event) -> None:
        """Handle escape key to dismiss ask input."""
        if event.key == "escape":
            ask_input = self.query_one("#ask-input", Input)
            if ask_input.has_class("visible"):
                ask_input.value = ""
                ask_input.remove_class("visible")
                self._set_status("Ask cancelled.")
                event.prevent_default()
                event.stop()

    @work(thread=True)
    def _do_ask(self, question: str) -> None:
        """Run the ask pipeline in a background thread."""
        self.app.call_from_thread(self._set_status, f" Searching brain for: {question}")

        try:
            from .ask import ask_brain

            answer = ask_brain(question)

            # Show the answer in the preview pane
            title = self.query_one("#preview-title", Static)
            preview = self.query_one("#preview", PreviewPane)

            self.app.call_from_thread(title.update, f" Answer: {question}")
            self.app.call_from_thread(preview.set_content, answer)
            self.app.call_from_thread(self._set_status, " Answer displayed in preview pane.")

        except Exception as e:
            self.app.call_from_thread(self._set_status, f" Ask error: {e}")


def run_tui():
    """Launch the TUI app."""
    app = BrainApp()
    app.run()
