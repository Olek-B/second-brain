"""SecondBrainPlugin - Base class for all Second Brain plugins.

Override any hook method you care about. All hooks have default
no-op implementations so you only need to implement what you use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .brain_api import BrainAPI


class SecondBrainPlugin:
    """Base class for Second Brain plugins.

    Override any hook method you care about. All hooks have default
    no-op implementations so you only need to implement what you use.

    Attributes:
        name:   Plugin name (auto-set from filename if not overridden).
        config: Per-plugin config dict from config.json.
        ctx:    BrainAPI instance — set during on_load().
    """

    name: str = ""
    config: dict
    ctx: BrainAPI

    def __init__(self, plugin_config: dict | None = None) -> None:
        self.config = plugin_config or {}

    # -- lifecycle ----------------------------------------------------------

    def on_load(self, ctx: BrainAPI) -> None:
        """Called when the plugin is loaded. ctx is the BrainAPI instance."""
        pass

    def on_unload(self) -> None:
        """Called when the plugin is unloaded / application exits."""
        pass

    def run_background(self, ctx: BrainAPI) -> None:
        """Override for long-running plugins (bots, daemons).

        This method is called in a daemon thread. It should contain
        the main loop (e.g. polling for messages). The thread dies
        automatically when the main process exits.

        Only called if the method is actually overridden — the base
        implementation is a no-op and does NOT spawn a thread.
        """
        pass

    # -- librarian hooks ----------------------------------------------------

    def before_process_dump(self, dump_text: str) -> str | None:
        """Mutating: transform dump text before AI processing."""
        return None

    def after_plan(self, plan: dict) -> dict | None:
        """Mutating: inspect/modify/filter plan after Pass 1."""
        return None

    def before_write_action(
        self,
        action: dict,
        existing_content: str | None,
    ) -> dict | None:
        """Mutating: modify an action before Pass 2 (Write)."""
        return None

    def after_write_action(self, action: dict) -> None:
        """Observational: called after each write action gets its content."""
        pass

    def before_execute_actions(self, actions: list[dict]) -> list[dict] | None:
        """Mutating: modify/filter actions before they are written to disk."""
        return None

    def after_execute_actions(self, summaries: list[str]) -> None:
        """Observational: called after all actions are executed."""
        pass

    def before_write_file(
        self,
        action: dict,
        target: Path,
        content: str,
    ) -> str | None:
        """Mutating: transform content before it is written to a brain file."""
        return None

    def after_write_file(
        self,
        action: dict,
        target: Path,
        summary: str,
    ) -> None:
        """Observational: called after a brain file is written."""
        pass

    def before_write_todos(self, todo_items: list[str]) -> list[str] | None:
        """Mutating: filter/transform todo items before writing to todo.md."""
        return None

    def after_write_todos(self, count: int) -> None:
        """Observational: called after todos are written."""
        pass

    def before_clear_dump(self) -> None:
        """Observational: called before dump.md is cleared."""
        pass

    def after_clear_dump(self) -> None:
        """Observational: called after dump.md is cleared."""
        pass

    def on_plan_error(self, error: Exception) -> None:
        """Observational: called when planning pass fails."""
        pass

    def after_process_dump(self, actions: dict) -> None:
        """Observational: called after the full 2-pass pipeline completes."""
        pass

    # -- ask hooks ----------------------------------------------------------

    def before_ask(self, question: str) -> str | None:
        """Mutating: transform question before AI processes it."""
        return None

    def after_ask(self, question: str, answer: str) -> None:
        """Observational: called after the AI answers a question."""
        pass

    # -- graph hooks --------------------------------------------------------

    def before_scan_brain(self) -> None:
        """Observational: called before scanning brain for nodes/edges."""
        pass

    def after_scan_brain(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> tuple[list[str], list[tuple[str, str]]] | None:
        """Mutating: modify nodes/edges after brain scan."""
        return None

    def after_scan_brain_external(
        self,
        external_nodes: set[str],
    ) -> set[str] | None:
        """Mutating: modify external nodes (wiki links without files)."""
        return None

    def before_generate_dot(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> None:
        """Observational: called before DOT generation."""
        pass

    def on_dot_node(self, node: str, attrs: dict) -> dict | None:
        """Mutating: customize DOT attributes for a single node."""
        return None

    def on_dot_edge(
        self,
        src: str,
        tgt: str,
        attrs: dict,
    ) -> dict | None:
        """Mutating: customize DOT attributes for a single edge."""
        return None

    def on_dot_external_node(self, node: str, attrs: dict) -> dict | None:
        """Mutating: customize DOT attributes for external (Wikipedia) node."""
        return None

    def after_generate_dot(self, dot_source: str) -> str | None:
        """Mutating: transform the DOT source before rendering."""
        return None

    def before_render_graph(self, dot_source: str) -> str | None:
        """Mutating: final chance to modify DOT before Graphviz runs."""
        return None

    def after_render_graph(self, output_path: Path) -> None:
        """Observational: called after graph PNG is rendered."""
        pass

    # -- wallpaper hooks ----------------------------------------------------

    def before_parse_todos(self) -> None:
        """Observational: called before parsing todo.md for wallpaper."""
        pass

    def after_parse_todos(
        self,
        items: list[tuple[bool, str]],
    ) -> list[tuple[bool, str]] | None:
        """Mutating: filter/add todo items for the wallpaper overlay."""
        return None

    def before_render_todo_overlay(
        self,
        items: list[tuple[bool, str]],
    ) -> None:
        """Observational: called before rendering the todo overlay PNG."""
        pass

    def after_render_todo_overlay(self, output_path: Path | None) -> None:
        """Observational: called after todo overlay is rendered."""
        pass

    def before_composite(
        self,
        graph_path: Path,
        wallpaper_path: Path,
    ) -> None:
        """Observational: called before compositing layers onto wallpaper."""
        pass

    def after_composite(self, output_path: Path) -> None:
        """Observational: called after wallpaper is composited."""
        pass

    def before_set_wallpaper(self, wallpaper_path: Path) -> None:
        """Observational: called before setting the wallpaper."""
        pass

    def after_set_wallpaper(
        self,
        wallpaper_path: Path,
        success: bool,
    ) -> None:
        """Observational: called after wallpaper is set (or failed)."""
        pass

    def before_refresh_wallpaper(self) -> None:
        """Observational: called before the full wallpaper refresh pipeline."""
        pass

    def after_refresh_wallpaper(self, result: str) -> None:
        """Observational: called after wallpaper refresh completes."""
        pass

    # -- daily notes hooks --------------------------------------------------

    def before_daily_note_create(self, filename: str) -> None:
        """Observational: called before creating a new daily note."""
        pass

    def after_daily_note_create(
        self,
        note_path: Path,
        was_created: bool,
    ) -> None:
        """Observational: called after daily note is created/opened."""
        pass

    def after_daily_note_open(
        self,
        note_path: Path,
        was_created: bool,
    ) -> None:
        """Observational: called when opening existing daily note."""
        pass

    # -- tags hooks ---------------------------------------------------------

    def before_extract_tags(self, content: str) -> None:
        """Observational: called before extracting tags from content."""
        pass

    def after_extract_tags(self, tags: list[str]) -> list[str] | None:
        """Mutating: filter/transform extracted tags."""
        return None

    # -- duplicates hooks ---------------------------------------------------

    def before_find_duplicates(
        self,
        threshold: float,
        min_words: int,
    ) -> None:
        """Observational: called before finding duplicates."""
        pass

    def after_find_duplicates(
        self,
        pairs: list[tuple[str, str, float]],
    ) -> list[tuple[str, str, float]] | None:
        """Mutating: filter/transform duplicate pairs."""
        return None

    # -- janitor hooks ------------------------------------------------------

    def before_janitor_run(self, files: dict[str, str]) -> None:
        """Observational: called before janitor processes files."""
        pass

    def after_janitor_run(self, summaries: list[str]) -> None:
        """Observational: called after janitor completes."""
        pass

    def after_janitor_llm(self, changes: list[dict]) -> list[dict] | None:
        """Mutating: filter/veto janitor changes before writing."""
        return None

    def before_janitor_write(
        self,
        fname: str,
        old_content: str,
        new_content: str,
    ) -> str | None:
        """Mutating: transform content before janitor writes a file."""
        return None

    def after_janitor_write(self, fname: str) -> None:
        """Observational: called after janitor writes a file."""
        pass

    def on_janitor_reject(self, fname: str, reason: str) -> None:
        """Observational: called when janitor rejects a change (safety valve)."""
        pass

    def on_janitor_skip(self, fname: str, reason: str) -> None:
        """Observational: called when janitor skips a file."""
        pass

    # -- TUI hooks ----------------------------------------------------------

    def on_tui_start(self, app: Any) -> None:
        """Observational: called when the TUI app starts."""
        pass

    def on_tui_stop(self) -> None:
        """Observational: called when the TUI app stops."""
        pass

    def on_file_selected(self, fname: str) -> None:
        """Observational: called when a file is selected in the TUI."""
        pass

    def on_file_preview(
        self,
        fname: str,
        content: str,
    ) -> str | None:
        """Mutating: transform file content before displaying in preview."""
        return None

    def on_wikilink_clicked(self, target: str) -> None:
        """Observational: called when a wikilink is clicked in the TUI."""
        pass

    def before_tui_process_dump(self) -> None:
        """Observational: called before TUI triggers dump processing."""
        pass

    def after_tui_process_dump(self, summaries: list[str]) -> None:
        """Observational: called after TUI dump processing completes."""
        pass

    def before_tui_graph(self) -> None:
        """Observational: called before TUI triggers graph generation."""
        pass

    def after_tui_graph(self, result: str) -> None:
        """Observational: called after TUI graph generation completes."""
        pass

    def before_tui_janitor(self) -> None:
        """Observational: called before TUI triggers janitor."""
        pass

    def after_tui_janitor(self, summaries: list[str]) -> None:
        """Observational: called after TUI janitor completes."""
        pass

    def on_tui_refresh_list(self, files: list[str]) -> None:
        """Observational: called when the TUI file list is refreshed."""
        pass

    def on_tui_edit_file(self, fname: str) -> None:
        """Observational: called when a file is opened in $EDITOR from TUI."""
        pass
