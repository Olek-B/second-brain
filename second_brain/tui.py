"""Second Brain TUI - Textual-based terminal interface."""

import os
import re
import subprocess

from rich.text import Text

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Click
from textual.message import Message
from textual.widgets import (
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from . import config
from .plugins import get_manager


class FileList(ListView):
    """Sidebar list of brain markdown files."""
    pass


class WikiLinkClicked(Message):
    """Posted when a wikilink in the preview is clicked."""
    def __init__(self, target: str) -> None:
        self.target = target
        super().__init__()


class PreviewLine(Static):
    """A single line in the preview with clickable wikilinks and word wrap."""

    DEFAULT_CSS = """
    PreviewLine {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, line: str) -> None:
        super().__init__()
        self._line = line
        self._links: list[tuple[int, int, str]] = []  # (start, end, target)

    def on_mount(self) -> None:
        text = Text()
        self._links.clear()
        parts = re.split(r"(\[\[[^\]]+\]\])", self._line)
        for part in parts:
            m = re.match(r"^\[\[([^\]]+)\]\]$", part)
            if m:
                target = m.group(1).strip()
                start = len(text)
                text.append(f"[[{target}]]", style="bold underline cyan")
                self._links.append((start, len(text), target))
            else:
                text.append(part)

        if not text.plain:
            text.append(" ")

        self.update(text)

    def on_click(self, event: Click) -> None:
        """Determine if a wikilink was clicked based on offset."""
        if not self._links:
            return
        # event.x is the column offset within this widget (after padding)
        # For wrapped text we need to account for the line the click landed on.
        # Each wrapped visual line has width = self.size.width.
        # The character offset into the plain text is:
        #   offset = event.y * self.size.width + event.x
        w = self.size.width
        if w <= 0:
            return
        offset = event.y * w + event.x
        for start, end, target in self._links:
            if start <= offset < end:
                self.post_message(WikiLinkClicked(target))
                return


class PreviewPane(VerticalScroll):
    """Scrollable file preview with clickable wikilinks."""

    DEFAULT_CSS = """
    PreviewPane {
        height: 1fr;
        border: round $surface;
        padding: 1;
    }
    """

    def set_content(self, content: str) -> None:
        """Replace the preview content."""
        self.remove_children()
        for line in content.splitlines():
            self.mount(PreviewLine(line))


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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("e", "edit_file", "Edit in $EDITOR"),
        Binding("g", "view_graph", "Refresh Graph"),
        Binding("p", "process_dump", "Process Dump"),
        Binding("j", "run_janitor", "Janitor"),
        Binding("r", "refresh_list", "Refresh List"),
        Binding("d", "open_dump", "Edit Dump"),
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
                yield PreviewPane(id="preview")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_file_list()
        self._set_status("Ready. [e]dit | [g]raph | [p]rocess dump | [d]ump | [r]efresh | [q]uit")

        # --- Hook: on_tui_start ---
        pm = get_manager()
        pm.dispatch_on_tui_start(self)

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
            self._set_status(f" {target_fname} not found in brain")

    def _show_preview(self, fname: str) -> None:
        """Display file content in the preview pane."""
        fpath = config.BRAIN_DIR / fname
        preview = self.query_one("#preview", PreviewPane)
        title = self.query_one("#preview-title", Static)

        title.update(f" {fname}")

        if fpath.exists():
            content = fpath.read_text()

            # --- Hook: on_file_preview (mutating) ---
            pm = get_manager()
            content = pm.dispatch_on_file_preview(fname, content)

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
            from .librarian import process_dump, execute_actions, clear_dump

            actions = process_dump()

            if "error" in actions:
                self.app.call_from_thread(
                    self._set_status, f" {actions['error']}"
                )
                return

            summaries = execute_actions(actions)
            clear_dump()

            summary = " | ".join(summaries) if summaries else "No actions taken"
            self.app.call_from_thread(
                self._set_status, f" {summary}"
            )
            self.app.call_from_thread(self._refresh_file_list)

            # --- Hook: after_tui_process_dump ---
            pm.dispatch_after_tui_process_dump(summaries)

        except Exception as e:
            self.app.call_from_thread(
                self._set_status, f" Error: {e}"
            )

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
            self.app.call_from_thread(
                self._set_status, f" Graph error: {e}"
            )

    def action_refresh_list(self) -> None:
        """Refresh the file list."""
        self._refresh_file_list()
        self._set_status(" File list refreshed")

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
            self.app.call_from_thread(
                self._set_status, f" Janitor error: {e}"
            )


def run_tui():
    """Launch the TUI app."""
    app = BrainApp()
    app.run()
