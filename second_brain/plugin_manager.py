"""PluginManager - Loads plugins from disk and dispatches hook calls.

Provides the PluginManager class that handles plugin loading, lifecycle
management, and dispatching hook calls to all registered plugins.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Any

from .brain_api import brain_api
from .plugin_base import SecondBrainPlugin

log = logging.getLogger("second_brain.plugins")


def _log_error(plugin: SecondBrainPlugin, hook: str, error: Exception) -> None:
    """Log a plugin hook error without crashing."""
    log.error("Plugin '%s' error in %s: %s", plugin.name, hook, error)


def _has_override(plugin: SecondBrainPlugin, method_name: str) -> bool:
    """Check if a plugin actually overrides a method (not just inherits no-op)."""
    plugin_method = getattr(type(plugin), method_name, None)
    base_method = getattr(SecondBrainPlugin, method_name, None)
    return plugin_method is not base_method


class PluginManager:
    """Loads plugins from disk and dispatches hook calls."""

    def __init__(self) -> None:
        self._plugins: list[SecondBrainPlugin] = []
        self._threads: list[threading.Thread] = []
        self._loaded = False

    @property
    def plugins(self) -> list[SecondBrainPlugin]:
        return list(self._plugins)

    def load_all(self) -> None:
        """Scan the plugin directory and load all enabled plugins."""
        if self._loaded:
            return
        self._loaded = True

        from . import config

        plugin_dir = config.get_plugin_dir()
        if not plugin_dir.exists():
            return

        enabled = config.get_enabled_plugins()
        disabled = config.get_disabled_plugins()

        py_files = sorted(plugin_dir.glob("*.py"))
        for py_file in py_files:
            if py_file.name.startswith("_"):
                continue

            plugin_name = py_file.stem

            # Check enable/disable lists
            if enabled is not None and plugin_name not in enabled:
                log.debug("Plugin '%s' not in enabled list, skipping", plugin_name)
                continue
            if plugin_name in disabled:
                log.debug("Plugin '%s' is disabled, skipping", plugin_name)
                continue

            try:
                self._load_plugin(py_file, plugin_name)
            except Exception as e:
                log.error("Failed to load plugin '%s': %s", plugin_name, e)

    def _load_plugin(self, py_file: Path, plugin_name: str) -> None:
        """Import a single plugin file and instantiate its plugin class."""
        spec = importlib.util.spec_from_file_location(
            f"second_brain_plugin_{plugin_name}",
            py_file,
        )
        if spec is None or spec.loader is None:
            log.error("Could not create module spec for %s", py_file)
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # Find the SecondBrainPlugin subclass in the module
        plugin_cls = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, SecondBrainPlugin)
                and attr is not SecondBrainPlugin
            ):
                plugin_cls = attr
                break

        if plugin_cls is None:
            log.warning(
                "Plugin file '%s' has no SecondBrainPlugin subclass",
                py_file.name,
            )
            return

        # Get per-plugin config
        from . import config

        plugin_config = config.get_plugin_config(plugin_name)

        # Instantiate
        plugin = plugin_cls(plugin_config)
        if not plugin.name:
            plugin.name = plugin_name
        plugin.ctx = brain_api

        # on_load
        try:
            plugin.on_load(brain_api)
        except Exception as e:
            log.error("Plugin '%s' on_load() failed: %s", plugin.name, e)
            return

        self._plugins.append(plugin)
        log.info("Loaded plugin: %s", plugin.name)

        # Spawn background thread if run_background is overridden
        if _has_override(plugin, "run_background"):
            t = threading.Thread(
                target=self._run_background_safe,
                args=(plugin,),
                daemon=True,
                name=f"plugin-{plugin.name}",
            )
            t.start()
            self._threads.append(t)
            log.info("Started background thread for plugin: %s", plugin.name)

    def _run_background_safe(self, plugin: SecondBrainPlugin) -> None:
        """Run a plugin's background method with error handling."""
        try:
            plugin.run_background(brain_api)
        except Exception as e:
            log.error(
                "Plugin '%s' run_background() crashed: %s",
                plugin.name,
                e,
            )

    def unload_all(self) -> None:
        """Unload all plugins (call on_unload on each)."""
        for plugin in self._plugins:
            try:
                plugin.on_unload()
            except Exception as e:
                _log_error(plugin, "on_unload", e)
        self._plugins.clear()
        self._threads.clear()
        self._loaded = False

    # -------------------------------------------------------------------
    # Dispatch helpers
    # -------------------------------------------------------------------

    def _dispatch_mutating(
        self,
        hook_name: str,
        value: Any,
        *args: Any,
    ) -> Any:
        """Dispatch a mutating hook — chain return values through plugins.

        If a plugin returns None, the value passes through unchanged.
        """
        for plugin in self._plugins:
            fn = getattr(plugin, hook_name, None)
            if fn is None:
                continue
            try:
                result = fn(value, *args)
                if result is not None:
                    value = result
            except Exception as e:
                _log_error(plugin, hook_name, e)
        return value

    def _dispatch_observational(self, hook_name: str, *args: Any) -> None:
        """Dispatch an observational hook — fire and forget."""
        for plugin in self._plugins:
            fn = getattr(plugin, hook_name, None)
            if fn is None:
                continue
            try:
                fn(*args)
            except Exception as e:
                _log_error(plugin, hook_name, e)

    # -------------------------------------------------------------------
    # Librarian dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_process_dump(self, dump_text: str) -> str:
        return self._dispatch_mutating("before_process_dump", dump_text)

    def dispatch_after_plan(self, plan: dict) -> dict:
        return self._dispatch_mutating("after_plan", plan)

    def dispatch_before_write_action(
        self,
        action: dict,
        existing_content: str | None,
    ) -> dict:
        return self._dispatch_mutating(
            "before_write_action",
            action,
            existing_content,
        )

    def dispatch_after_write_action(self, action: dict) -> None:
        self._dispatch_observational("after_write_action", action)

    def dispatch_before_execute_actions(self, actions: list[dict]) -> list[dict]:
        return self._dispatch_mutating("before_execute_actions", actions)

    def dispatch_after_execute_actions(self, summaries: list[str]) -> None:
        self._dispatch_observational("after_execute_actions", summaries)

    def dispatch_before_write_file(
        self,
        action: dict,
        target: Path,
        content: str,
    ) -> str:
        # Custom loop: content is the mutated value, action/target are context.
        for plugin in self._plugins:
            fn = getattr(plugin, "before_write_file", None)
            if fn is None:
                continue
            try:
                result = fn(action, target, content)
                if result is not None:
                    content = result
            except Exception as e:
                _log_error(plugin, "before_write_file", e)
        return content

    def dispatch_after_write_file(
        self,
        action: dict,
        target: Path,
        summary: str,
    ) -> None:
        self._dispatch_observational("after_write_file", action, target, summary)

    def dispatch_before_write_todos(self, todo_items: list[str]) -> list[str]:
        return self._dispatch_mutating("before_write_todos", todo_items)

    def dispatch_after_write_todos(self, count: int) -> None:
        self._dispatch_observational("after_write_todos", count)

    def dispatch_before_clear_dump(self) -> None:
        self._dispatch_observational("before_clear_dump")

    def dispatch_after_clear_dump(self) -> None:
        self._dispatch_observational("after_clear_dump")

    def dispatch_on_plan_error(self, error: Exception) -> None:
        self._dispatch_observational("on_plan_error", error)

    def dispatch_after_process_dump(self, actions: dict) -> None:
        self._dispatch_observational("after_process_dump", actions)

    # -------------------------------------------------------------------
    # Ask dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_ask(self, question: str) -> str:
        return self._dispatch_mutating("before_ask", question)

    def dispatch_after_ask(self, question: str, answer: str) -> None:
        self._dispatch_observational("after_ask", question, answer)

    # -------------------------------------------------------------------
    # Graph dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_scan_brain(self) -> None:
        self._dispatch_observational("before_scan_brain")

    def dispatch_after_scan_brain(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        value = (nodes, edges)
        for plugin in self._plugins:
            try:
                result = plugin.after_scan_brain(value[0], value[1])
                if result is not None:
                    value = result
            except Exception as e:
                _log_error(plugin, "after_scan_brain", e)
        return value

    def dispatch_after_scan_brain_external(
        self,
        external_nodes: set[str],
    ) -> set[str]:
        for plugin in self._plugins:
            try:
                result = plugin.after_scan_brain_external(external_nodes)
                if result is not None:
                    external_nodes = result
            except Exception as e:
                _log_error(plugin, "after_scan_brain_external", e)
        return external_nodes

    def dispatch_before_generate_dot(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> None:
        self._dispatch_observational("before_generate_dot", nodes, edges)

    def dispatch_on_dot_node(self, node: str, attrs: dict) -> dict:
        for plugin in self._plugins:
            try:
                result = plugin.on_dot_node(node, attrs)
                if result is not None:
                    attrs = result
            except Exception as e:
                _log_error(plugin, "on_dot_node", e)
        return attrs

    def dispatch_on_dot_edge(self, src: str, tgt: str, attrs: dict) -> dict:
        for plugin in self._plugins:
            try:
                result = plugin.on_dot_edge(src, tgt, attrs)
                if result is not None:
                    attrs = result
            except Exception as e:
                _log_error(plugin, "on_dot_edge", e)
        return attrs

    def dispatch_on_dot_external_node(self, node: str, attrs: dict) -> dict:
        for plugin in self._plugins:
            try:
                result = plugin.on_dot_external_node(node, attrs)
                if result is not None:
                    attrs = result
            except Exception as e:
                _log_error(plugin, "on_dot_external_node", e)
        return attrs

    def dispatch_after_generate_dot(self, dot_source: str) -> str:
        return self._dispatch_mutating("after_generate_dot", dot_source)

    def dispatch_before_render_graph(self, dot_source: str) -> str:
        return self._dispatch_mutating("before_render_graph", dot_source)

    def dispatch_after_render_graph(self, output_path: Path) -> None:
        self._dispatch_observational("after_render_graph", output_path)

    # -------------------------------------------------------------------
    # Wallpaper dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_parse_todos(self) -> None:
        self._dispatch_observational("before_parse_todos")

    def dispatch_after_parse_todos(
        self,
        items: list[tuple[bool, str]],
    ) -> list[tuple[bool, str]]:
        return self._dispatch_mutating("after_parse_todos", items)

    def dispatch_before_render_todo_overlay(
        self,
        items: list[tuple[bool, str]],
    ) -> None:
        self._dispatch_observational("before_render_todo_overlay", items)

    def dispatch_after_render_todo_overlay(
        self,
        output_path: Path | None,
    ) -> None:
        self._dispatch_observational("after_render_todo_overlay", output_path)

    def dispatch_before_composite(
        self,
        graph_path: Path,
        wallpaper_path: Path,
    ) -> None:
        self._dispatch_observational("before_composite", graph_path, wallpaper_path)

    def dispatch_after_composite(self, output_path: Path) -> None:
        self._dispatch_observational("after_composite", output_path)

    def dispatch_before_set_wallpaper(self, wallpaper_path: Path) -> None:
        self._dispatch_observational("before_set_wallpaper", wallpaper_path)

    def dispatch_after_set_wallpaper(
        self,
        wallpaper_path: Path,
        success: bool,
    ) -> None:
        self._dispatch_observational("after_set_wallpaper", wallpaper_path, success)

    def dispatch_before_refresh_wallpaper(self) -> None:
        self._dispatch_observational("before_refresh_wallpaper")

    def dispatch_after_refresh_wallpaper(self, result: str) -> None:
        self._dispatch_observational("after_refresh_wallpaper", result)

    def dispatch_before_daily_note_create(self, filename: str) -> None:
        self._dispatch_observational("before_daily_note_create", filename)

    def dispatch_after_daily_note_create(
        self,
        note_path: Path,
        was_created: bool,
    ) -> None:
        self._dispatch_observational(
            "after_daily_note_create",
            note_path,
            was_created,
        )

    def dispatch_after_daily_note_open(
        self,
        note_path: Path,
        was_created: bool,
    ) -> None:
        self._dispatch_observational(
            "after_daily_note_open",
            note_path,
            was_created,
        )

    # -------------------------------------------------------------------
    # Tag dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_extract_tags(self, content: str) -> None:
        self._dispatch_observational("before_extract_tags", content)

    def dispatch_after_extract_tags(self, tags: list[str]) -> list[str]:
        return self._dispatch_mutating("after_extract_tags", tags)

    # -------------------------------------------------------------------
    # Duplicates dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_find_duplicates(
        self,
        threshold: float,
        min_words: int,
    ) -> None:
        self._dispatch_observational(
            "before_find_duplicates",
            threshold,
            min_words,
        )

    def dispatch_after_find_duplicates(
        self,
        pairs: list[tuple[str, str, float]],
    ) -> list[tuple[str, str, float]]:
        return self._dispatch_mutating("after_find_duplicates", pairs)

    # -------------------------------------------------------------------
    # Janitor dispatchers
    # -------------------------------------------------------------------

    def dispatch_before_janitor_run(self, files: dict[str, str]) -> None:
        self._dispatch_observational("before_janitor_run", files)

    def dispatch_after_janitor_run(self, summaries: list[str]) -> None:
        self._dispatch_observational("after_janitor_run", summaries)

    def dispatch_after_janitor_llm(self, changes: list[dict]) -> list[dict]:
        return self._dispatch_mutating("after_janitor_llm", changes)

    def dispatch_before_janitor_write(
        self,
        fname: str,
        old_content: str,
        new_content: str,
    ) -> str:
        # Custom loop: new_content is the mutated value, fname/old_content
        # are context.
        for plugin in self._plugins:
            fn = getattr(plugin, "before_janitor_write", None)
            if fn is None:
                continue
            try:
                result = fn(fname, old_content, new_content)
                if result is not None:
                    new_content = result
            except Exception as e:
                _log_error(plugin, "before_janitor_write", e)
        return new_content

    def dispatch_after_janitor_write(self, fname: str) -> None:
        self._dispatch_observational("after_janitor_write", fname)

    def dispatch_on_janitor_reject(self, fname: str, reason: str) -> None:
        self._dispatch_observational("on_janitor_reject", fname, reason)

    def dispatch_on_janitor_skip(self, fname: str, reason: str) -> None:
        self._dispatch_observational("on_janitor_skip", fname, reason)

    # -------------------------------------------------------------------
    # TUI dispatchers
    # -------------------------------------------------------------------

    def dispatch_on_tui_start(self, app: Any) -> None:
        self._dispatch_observational("on_tui_start", app)

    def dispatch_on_tui_stop(self) -> None:
        self._dispatch_observational("on_tui_stop")

    def dispatch_on_file_selected(self, fname: str) -> None:
        self._dispatch_observational("on_file_selected", fname)

    def dispatch_on_file_preview(self, fname: str, content: str) -> str:
        # Custom loop: content is the mutated value, fname is context.
        for plugin in self._plugins:
            fn = getattr(plugin, "on_file_preview", None)
            if fn is None:
                continue
            try:
                result = fn(fname, content)
                if result is not None:
                    content = result
            except Exception as e:
                _log_error(plugin, "on_file_preview", e)
        return content

    def dispatch_on_wikilink_clicked(self, target: str) -> None:
        self._dispatch_observational("on_wikilink_clicked", target)

    def dispatch_before_tui_process_dump(self) -> None:
        self._dispatch_observational("before_tui_process_dump")

    def dispatch_after_tui_process_dump(self, summaries: list[str]) -> None:
        self._dispatch_observational("after_tui_process_dump", summaries)

    def dispatch_before_tui_graph(self) -> None:
        self._dispatch_observational("before_tui_graph")

    def dispatch_after_tui_graph(self, result: str) -> None:
        self._dispatch_observational("after_tui_graph", result)

    def dispatch_before_tui_janitor(self) -> None:
        self._dispatch_observational("before_tui_janitor")

    def dispatch_after_tui_janitor(self, summaries: list[str]) -> None:
        self._dispatch_observational("after_tui_janitor", summaries)

    def dispatch_on_tui_refresh_list(self, files: list[str]) -> None:
        self._dispatch_observational("on_tui_refresh_list", files)

    def dispatch_on_tui_edit_file(self, fname: str) -> None:
        self._dispatch_observational("on_tui_edit_file", fname)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: PluginManager | None = None


def get_manager() -> PluginManager:
    """Get or create the global PluginManager singleton.

    On first call, loads all plugins from the plugin directory.
    """
    global _manager
    if _manager is None:
        _manager = PluginManager()
        _manager.load_all()
    return _manager


def reset_manager() -> None:
    """Reset the global manager (mainly for testing)."""
    global _manager
    if _manager is not None:
        _manager.unload_all()
    _manager = None
