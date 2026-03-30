"""Second Brain TUI Application."""

import webbrowser
from urllib.parse import quote

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .. import config
from ..backlinks import get_backlinks_for_tui
from ..tags import get_tags_by_file
from ..plugins import get_manager
from .styles import MAIN_CSS
from .widgets import FileList, WikiLinkClicked, PreviewPane
from .actions import ActionMixin


class BrainApp(ActionMixin, App):
    """Second Brain TUI Application."""

    TITLE = "Second Brain"
    SUB_TITLE = ""

    CSS = MAIN_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("e", "edit_file", "Edit in $EDITOR"),
        Binding("g", "view_graph", "Refresh Graph"),
        Binding("p", "process_dump", "Process Dump"),
        Binding("j", "run_janitor", "Janitor"),
        Binding("R", "refresh_list", "Refresh List"),
        Binding("r", "view_rss", "RSS Feeds"),
        Binding("d", "open_dump", "Edit Dump"),
        Binding("t", "pull_telegram", "Pull Telegram"),
        Binding("T", "view_todos", "View Todos"),
        Binding("n", "daily_note", "New Daily Note"),
        Binding("#", "view_tags", "View Tags"),
        Binding("D", "view_duplicates", "View Duplicates"),
        Binding("a", "ask_brain", "Ask Brain"),
        Binding("i", "view_investments", "View Investments"),
        Binding("I", "refresh_investments", "Refresh Investments"),
        Binding("A", "view_analytics", "Analytics"),
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

        pm = get_manager()
        pm.dispatch_on_tui_start(self)

        self._auto_pull_telegram()
        self._do_refresh_rss()

    @work(thread=True, exclusive=True)
    def _auto_pull_telegram(self) -> None:
        """Automatically pull Telegram messages and process dump on TUI start."""
        pm = get_manager()

        pull_plugin = None
        for p in pm.plugins:
            if p.name == "telegram_pull":
                pull_plugin = p
                break

        if pull_plugin is None:
            return

        try:
            count = pull_plugin.do_pull()  # type: ignore[attr-defined]
            if count:
                self.app.call_from_thread(
                    self._set_status,
                    f" Pulled {count} Telegram message(s). Processing...",
                )
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
        """Process dump.md through the Librarian."""
        self.app.call_from_thread(self._set_status, " Processing Telegram dump with AI...")

        try:
            from ..librarian import clear_dump, execute_actions, process_dump

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

        dump_exists = config.DUMP_FILE.exists() and config.DUMP_FILE.read_text().strip()
        if dump_exists:
            self._set_status(" dump.md has content! Press [p] to process it.")

        pm = get_manager()
        pm.dispatch_on_tui_refresh_list(self._files)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection in sidebar."""
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._files):
            fname = self._files[idx]
            self._selected_file = fname
            self._show_preview(fname)

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

        pm = get_manager()
        pm.dispatch_on_wikilink_clicked(event.target)

        try:
            idx = self._files.index(target_fname)
            file_list = self.query_one("#file-list", FileList)
            file_list.index = idx
            self._selected_file = target_fname
            self._show_preview(target_fname)
            self._set_status(f"Navigated to {target_fname}")
        except ValueError:
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

        valid_files = {f.removesuffix(".md") for f in self._files}
        preview.set_valid_files(valid_files)

        if fpath.exists():
            content = fpath.read_text()

            pm = get_manager()
            content = pm.dispatch_on_file_preview(fname, content)

            backlinks_md, _ = get_backlinks_for_tui(fname)
            if backlinks_md:
                lines = content.splitlines()
                insert_at = 0

                if lines and lines[0].strip() == "---":
                    insert_at = 1
                    while insert_at < len(lines) and lines[insert_at].strip() != "---":
                        insert_at += 1
                    insert_at += 1

                while insert_at < len(lines) and lines[insert_at].strip() == "":
                    insert_at += 1

                if insert_at < len(lines) and lines[insert_at].startswith("#"):
                    insert_at += 1
                    while insert_at < len(lines) and lines[insert_at].strip() == "":
                        insert_at += 1

                if insert_at > 0:
                    backlinks_md = "\n" + backlinks_md
                if insert_at < len(lines):
                    backlinks_md = backlinks_md + "\n"

                lines = lines[:insert_at] + [backlinks_md] + lines[insert_at:]
                content = "\n".join(lines)

            tags = get_tags_by_file(fname)
            if tags:
                content += "\n\n---\n\n**Tags:** "
                content += ", ".join(f"#{t}" for t in sorted(tags))

            preview.set_content(content)
        else:
            preview.set_content("File not found")

    def _set_status(self, msg: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(msg)

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
            from ..ask import ask_brain

            answer = ask_brain(question)

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
