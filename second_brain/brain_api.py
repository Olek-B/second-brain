"""BrainAPI - Stable API surface for plugins to invoke core operations.

Thin wrappers around internal modules. If the internals are refactored,
the API stays the same — plugins never break.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("second_brain.plugins")


class BrainAPI:
    """Stable API surface for plugins to invoke core operations.

    Thin wrappers around internal modules. If the internals are
    refactored the API stays the same — plugins never break.
    """

    # -- config / paths -----------------------------------------------------

    @property
    def brain_dir(self) -> Path:
        from . import config

        return config.BRAIN_DIR

    @property
    def config_dir(self) -> Path:
        from . import config

        return config.CONFIG_DIR

    @property
    def dump_file(self) -> Path:
        from . import config

        return config.DUMP_FILE

    @property
    def todo_file(self) -> Path:
        from . import config

        return config.TODO_FILE

    def get_brain_files(self) -> list[str]:
        from . import config

        return config.get_brain_files()

    def get_wal_colors(self) -> dict:
        from . import config

        return config.get_wal_colors()

    def get_monitor_resolution(self) -> tuple[int, int]:
        from . import config

        return config.get_monitor_resolution()

    def get_plugin_config(self, plugin_name: str) -> dict:
        """Return the per-plugin config dict from config.json."""
        from . import config

        return config.get_plugin_config(plugin_name)

    # -- librarian ----------------------------------------------------------

    def process_dump(self, dump_text: str | None = None) -> dict:
        from .librarian import process_dump

        return process_dump(dump_text)

    def execute_actions(self, actions: dict) -> list[str]:
        from .librarian import execute_actions

        return execute_actions(actions)

    def clear_dump(self) -> None:
        from .librarian import clear_dump

        clear_dump()

    # -- graph --------------------------------------------------------------

    def scan_brain(self) -> tuple[list[str], list[tuple[str, str]], list[str]]:
        from .graph import scan_brain

        return scan_brain()

    def render_graph(self, output_path: Path | None = None) -> Path:
        from .graph import render_graph

        return render_graph(output_path)

    # -- wallpaper ----------------------------------------------------------

    def refresh_wallpaper(self) -> str:
        from .wallpaper import refresh_wallpaper

        return refresh_wallpaper()

    def set_wallpaper(self, path: Path | None = None) -> bool:
        from .wallpaper import set_wallpaper

        return set_wallpaper(path)

    # -- janitor ------------------------------------------------------------

    def run_janitor(self, dry_run: bool = False) -> list[str]:
        from .janitor import run_janitor

        return run_janitor(dry_run)

    # -- ask ----------------------------------------------------------------

    def ask_brain(self, question: str) -> str:
        from .ask import ask_brain

        return ask_brain(question)

    # -- utility ------------------------------------------------------------

    def read_file(self, fname: str) -> str:
        """Read a brain file by name (e.g. 'networking.md')."""
        path = self.brain_dir / fname
        if not path.exists():
            raise FileNotFoundError(f"{fname} not found in {self.brain_dir}")
        return path.read_text()

    def write_file(self, fname: str, content: str) -> None:
        """Write content to a brain file."""
        path = self.brain_dir / fname
        path.write_text(content)

    def log(self, message: str) -> None:
        """Log a message from a plugin."""
        log.info(message)


# Singleton API instance — shared across all plugins
brain_api = BrainAPI()
