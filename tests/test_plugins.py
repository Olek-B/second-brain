"""Tests for second_brain.plugins module."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from second_brain.plugins import (
    BrainAPI,
    PluginManager,
    SecondBrainPlugin,
    _has_override,
    get_manager,
    reset_manager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure every test gets a fresh manager."""
    reset_manager()
    yield
    reset_manager()


@pytest.fixture
def manager():
    """Create a fresh PluginManager (not loaded)."""
    return PluginManager()


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a temp plugin directory."""
    d = tmp_path / "plugins"
    d.mkdir()
    return d


@pytest.fixture
def brain_dir(tmp_path):
    """Create a temp brain directory with some files."""
    d = tmp_path / "brain"
    d.mkdir()
    (d / "notes.md").write_text("# Notes\nSome notes here.")
    (d / "todo.md").write_text("# Todo\n- [ ] Test task\n- [x] Done task")
    (d / "dump.md").write_text("")
    return d


# ---------------------------------------------------------------------------
# SecondBrainPlugin base class
# ---------------------------------------------------------------------------


class TestSecondBrainPlugin:
    """Base class tests."""

    def test_default_name_is_empty(self):
        p = SecondBrainPlugin()
        assert p.name == ""

    def test_config_defaults_to_empty_dict(self):
        p = SecondBrainPlugin()
        assert p.config == {}

    def test_config_from_constructor(self):
        p = SecondBrainPlugin({"key": "value"})
        assert p.config == {"key": "value"}

    def test_on_load_is_noop(self):
        p = SecondBrainPlugin()
        api = BrainAPI()
        p.on_load(api)  # Should not raise

    def test_on_unload_is_noop(self):
        p = SecondBrainPlugin()
        p.on_unload()  # Should not raise

    def test_run_background_is_noop(self):
        p = SecondBrainPlugin()
        api = BrainAPI()
        p.run_background(api)  # Should not raise

    def test_all_mutating_hooks_return_none(self):
        """Every before_*/mutating hook should return None by default."""
        p = SecondBrainPlugin()
        assert p.before_process_dump("text") is None
        assert p.after_plan({"actions": []}) is None
        assert p.before_write_action({}, None) is None
        assert p.before_execute_actions([]) is None
        assert p.before_write_file({}, Path("/tmp/x"), "content") is None
        assert p.before_write_todos([]) is None
        assert p.after_scan_brain([], []) is None
        assert p.on_dot_node("node", {}) is None
        assert p.on_dot_edge("a", "b", {}) is None
        assert p.after_generate_dot("dot") is None
        assert p.before_render_graph("dot") is None
        assert p.after_parse_todos([]) is None
        assert p.after_janitor_llm([]) is None
        assert p.before_janitor_write("f", "old", "new") is None
        assert p.on_file_preview("f", "content") is None

    def test_all_observational_hooks_return_none(self):
        """Observational hooks should return None (void)."""
        p = SecondBrainPlugin()
        assert p.after_write_action({}) is None
        assert p.after_execute_actions([]) is None
        assert p.after_write_file({}, Path("/tmp/x"), "s") is None
        assert p.after_write_todos(0) is None
        assert p.before_clear_dump() is None
        assert p.after_clear_dump() is None
        assert p.on_plan_error(ValueError("x")) is None
        assert p.after_process_dump({}) is None
        assert p.before_scan_brain() is None
        assert p.before_generate_dot([], []) is None
        assert p.after_render_graph(Path("/tmp/x")) is None
        assert p.before_parse_todos() is None
        assert p.after_render_todo_overlay(None) is None
        assert p.before_composite(Path("/a"), Path("/b")) is None
        assert p.after_composite(Path("/a")) is None
        assert p.before_set_wallpaper(Path("/a")) is None
        assert p.after_set_wallpaper(Path("/a"), True) is None
        assert p.before_refresh_wallpaper() is None
        assert p.after_refresh_wallpaper("ok") is None
        assert p.before_janitor_run({}) is None
        assert p.after_janitor_run([]) is None
        assert p.after_janitor_write("f") is None
        assert p.on_janitor_reject("f", "reason") is None
        assert p.on_janitor_skip("f", "reason") is None

    def test_subclass_can_override_hooks(self):
        class MyPlugin(SecondBrainPlugin):
            def before_process_dump(self, dump_text):
                return dump_text.upper()

        p = MyPlugin()
        assert p.before_process_dump("hello") == "HELLO"


# ---------------------------------------------------------------------------
# _has_override helper
# ---------------------------------------------------------------------------


class TestHasOverride:
    def test_base_class_has_no_override(self):
        p = SecondBrainPlugin()
        assert not _has_override(p, "run_background")
        assert not _has_override(p, "before_process_dump")

    def test_subclass_with_override(self):
        class MyPlugin(SecondBrainPlugin):
            def run_background(self, ctx):
                pass

        p = MyPlugin()
        assert _has_override(p, "run_background")

    def test_subclass_without_override(self):
        class MyPlugin(SecondBrainPlugin):
            name = "test"

        p = MyPlugin()
        assert not _has_override(p, "run_background")


# ---------------------------------------------------------------------------
# BrainAPI
# ---------------------------------------------------------------------------


class TestBrainAPI:
    def test_brain_dir_is_path(self):
        api = BrainAPI()
        assert isinstance(api.brain_dir, Path)

    def test_config_dir_is_path(self):
        api = BrainAPI()
        assert isinstance(api.config_dir, Path)

    def test_dump_file_is_path(self):
        api = BrainAPI()
        assert isinstance(api.dump_file, Path)

    def test_todo_file_is_path(self):
        api = BrainAPI()
        assert isinstance(api.todo_file, Path)

    def test_get_brain_files_returns_list(self):
        api = BrainAPI()
        assert isinstance(api.get_brain_files(), list)

    def test_get_wal_colors_returns_dict(self):
        api = BrainAPI()
        result = api.get_wal_colors()
        assert isinstance(result, dict)
        assert "colors" in result

    def test_get_monitor_resolution_returns_tuple(self):
        api = BrainAPI()
        result = api.get_monitor_resolution()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_get_plugin_config_returns_dict(self):
        api = BrainAPI()
        result = api.get_plugin_config("nonexistent_plugin")
        assert isinstance(result, dict)
        assert result == {}

    def test_read_file(self, brain_dir):
        api = BrainAPI()
        from second_brain import config

        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = brain_dir
            content = api.read_file("notes.md")
            assert "Some notes here" in content
        finally:
            config.BRAIN_DIR = old_dir

    def test_read_file_not_found(self, brain_dir):
        api = BrainAPI()
        from second_brain import config

        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = brain_dir
            with pytest.raises(FileNotFoundError):
                api.read_file("nonexistent.md")
        finally:
            config.BRAIN_DIR = old_dir

    def test_write_file(self, brain_dir):
        api = BrainAPI()
        from second_brain import config

        old_dir = config.BRAIN_DIR
        try:
            config.BRAIN_DIR = brain_dir
            api.write_file("new_file.md", "# New\nContent")
            assert (brain_dir / "new_file.md").read_text() == "# New\nContent"
        finally:
            config.BRAIN_DIR = old_dir

    def test_log_does_not_raise(self):
        api = BrainAPI()
        api.log("test message")  # Should not raise


# ---------------------------------------------------------------------------
# PluginManager - Loading
# ---------------------------------------------------------------------------


class TestPluginManagerLoading:
    def test_empty_dir(self, manager, plugin_dir):
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    manager.load_all()
        assert manager.plugins == []

    def test_load_simple_plugin(self, manager, plugin_dir):
        plugin_file = plugin_dir / "test_plug.py"
        plugin_file.write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class TestPlug(SecondBrainPlugin):\n"
            "    name = 'test_plug'\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        assert len(manager.plugins) == 1
        assert manager.plugins[0].name == "test_plug"

    def test_plugin_receives_config(self, manager, plugin_dir):
        plugin_file = plugin_dir / "cfg_plug.py"
        plugin_file.write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class CfgPlug(SecondBrainPlugin):\n"
            "    name = 'cfg_plug'\n"
        )
        cfg = {"key": "value", "count": 42}
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value=cfg):
                        manager.load_all()
        assert manager.plugins[0].config == cfg

    def test_plugin_name_from_filename(self, manager, plugin_dir):
        """If plugin doesn't set name, it gets the filename stem."""
        plugin_file = plugin_dir / "auto_named.py"
        plugin_file.write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class MyPlugin(SecondBrainPlugin):\n"
            "    pass\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        assert manager.plugins[0].name == "auto_named"

    def test_plugin_gets_ctx(self, manager, plugin_dir):
        plugin_file = plugin_dir / "ctx_plug.py"
        plugin_file.write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class CtxPlug(SecondBrainPlugin):\n"
            "    pass\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        assert isinstance(manager.plugins[0].ctx, BrainAPI)

    def test_skip_underscore_files(self, manager, plugin_dir):
        (plugin_dir / "__init__.py").write_text("")
        (plugin_dir / "_helper.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class Helper(SecondBrainPlugin):\n"
            "    pass\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    manager.load_all()
        assert manager.plugins == []

    def test_skip_file_without_plugin_class(self, manager, plugin_dir):
        (plugin_dir / "no_class.py").write_text("x = 42\n")
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    manager.load_all()
        assert manager.plugins == []

    def test_skip_disabled_plugin(self, manager, plugin_dir):
        (plugin_dir / "disabled_plug.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class DisabledPlug(SecondBrainPlugin):\n"
            "    name = 'disabled_plug'\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch(
                    "second_brain.config.get_disabled_plugins", return_value=["disabled_plug"]
                ):
                    manager.load_all()
        assert manager.plugins == []

    def test_enabled_list_filters_plugins(self, manager, plugin_dir):
        (plugin_dir / "alpha.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class Alpha(SecondBrainPlugin):\n"
            "    name = 'alpha'\n"
        )
        (plugin_dir / "beta.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class Beta(SecondBrainPlugin):\n"
            "    name = 'beta'\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=["alpha"]):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        assert len(manager.plugins) == 1
        assert manager.plugins[0].name == "alpha"

    def test_on_load_failure_skips_plugin(self, manager, plugin_dir):
        (plugin_dir / "bad_load.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class BadLoad(SecondBrainPlugin):\n"
            "    def on_load(self, ctx):\n"
            "        raise RuntimeError('fail')\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        assert manager.plugins == []

    def test_syntax_error_skips_plugin(self, manager, plugin_dir):
        (plugin_dir / "broken.py").write_text("def this is broken\n")
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    manager.load_all()
        assert manager.plugins == []

    def test_load_all_only_once(self, manager, plugin_dir):
        """Calling load_all twice should not double-load plugins."""
        (plugin_dir / "once.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class Once(SecondBrainPlugin):\n"
            "    name = 'once'\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
                        manager.load_all()
        assert len(manager.plugins) == 1

    def test_nonexistent_plugin_dir(self, manager, tmp_path):
        """Missing plugin dir should not crash."""
        fake_dir = tmp_path / "nonexistent"
        with patch("second_brain.config.get_plugin_dir", return_value=fake_dir):
            manager.load_all()
        assert manager.plugins == []

    def test_multiple_plugins_load_order(self, manager, plugin_dir):
        """Plugins should load in sorted filename order."""
        for name in ["charlie", "alpha", "bravo"]:
            (plugin_dir / f"{name}.py").write_text(
                "from second_brain.plugins import SecondBrainPlugin\n"
                f"class {name.title()}(SecondBrainPlugin):\n"
                f"    name = '{name}'\n"
            )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()
        names = [p.name for p in manager.plugins]
        assert names == ["alpha", "bravo", "charlie"]


# ---------------------------------------------------------------------------
# PluginManager - Unloading
# ---------------------------------------------------------------------------


class TestPluginManagerUnloading:
    def test_unload_calls_on_unload(self, manager):
        mock_plugin = MagicMock(spec=SecondBrainPlugin)
        mock_plugin.name = "mock"
        manager._plugins.append(mock_plugin)
        manager._loaded = True

        manager.unload_all()
        mock_plugin.on_unload.assert_called_once()
        assert manager.plugins == []

    def test_unload_handles_errors(self, manager):
        mock_plugin = MagicMock(spec=SecondBrainPlugin)
        mock_plugin.name = "mock"
        mock_plugin.on_unload.side_effect = RuntimeError("fail")
        manager._plugins.append(mock_plugin)
        manager._loaded = True

        manager.unload_all()  # Should not raise
        assert manager.plugins == []


# ---------------------------------------------------------------------------
# PluginManager - Mutating dispatch
# ---------------------------------------------------------------------------


class TestMutatingDispatch:
    def test_no_plugins_passes_through(self, manager):
        result = manager.dispatch_before_process_dump("hello")
        assert result == "hello"

    def test_single_plugin_mutates(self, manager):
        class Upper(SecondBrainPlugin):
            def before_process_dump(self, text):
                return text.upper()

        manager._plugins.append(Upper())
        result = manager.dispatch_before_process_dump("hello")
        assert result == "HELLO"

    def test_plugin_returning_none_passes_through(self, manager):
        class Noop(SecondBrainPlugin):
            def before_process_dump(self, text):
                return None

        manager._plugins.append(Noop())
        result = manager.dispatch_before_process_dump("hello")
        assert result == "hello"

    def test_chain_multiple_plugins(self, manager):
        class AddPrefix(SecondBrainPlugin):
            def before_process_dump(self, text):
                return "prefix:" + text

        class AddSuffix(SecondBrainPlugin):
            def before_process_dump(self, text):
                return text + ":suffix"

        manager._plugins.extend([AddPrefix(), AddSuffix()])
        result = manager.dispatch_before_process_dump("hello")
        assert result == "prefix:hello:suffix"

    def test_error_mid_chain_continues(self, manager):
        class Explode(SecondBrainPlugin):
            name = "explode"

            def before_process_dump(self, text):
                raise RuntimeError("boom")

        class Upper(SecondBrainPlugin):
            name = "upper"

            def before_process_dump(self, text):
                return text.upper()

        manager._plugins.extend([Explode(), Upper()])
        result = manager.dispatch_before_process_dump("hello")
        assert result == "HELLO"

    def test_after_plan_mutation(self, manager):
        class FilterTodos(SecondBrainPlugin):
            def after_plan(self, plan):
                plan["actions"] = [a for a in plan["actions"] if a["type"] != "todo"]
                return plan

        manager._plugins.append(FilterTodos())
        plan = {
            "actions": [
                {"type": "todo", "content": "task"},
                {"type": "create", "target": "new.md"},
            ]
        }
        result = manager.dispatch_after_plan(plan)
        assert len(result["actions"]) == 1
        assert result["actions"][0]["type"] == "create"

    def test_before_write_todos_mutation(self, manager):
        class CapTodos(SecondBrainPlugin):
            def before_write_todos(self, items):
                return [i.upper() for i in items]

        manager._plugins.append(CapTodos())
        result = manager.dispatch_before_write_todos(["buy milk", "fix bug"])
        assert result == ["BUY MILK", "FIX BUG"]

    def test_before_write_file_mutation(self, manager):
        class AddFooter(SecondBrainPlugin):
            def before_write_file(self, action, target, content):
                return content + "\n---\nGenerated by plugin"

        manager._plugins.append(AddFooter())
        result = manager.dispatch_before_write_file({}, Path("/tmp/x"), "# Hello")
        assert result == "# Hello\n---\nGenerated by plugin"

    def test_before_execute_actions_mutation(self, manager):
        class DropCreates(SecondBrainPlugin):
            def before_execute_actions(self, actions):
                return [a for a in actions if a["type"] != "create"]

        manager._plugins.append(DropCreates())
        actions = [
            {"type": "create", "target": "new.md"},
            {"type": "append", "target": "old.md"},
        ]
        result = manager.dispatch_before_execute_actions(actions)
        assert len(result) == 1
        assert result[0]["type"] == "append"


# ---------------------------------------------------------------------------
# PluginManager - Observational dispatch
# ---------------------------------------------------------------------------


class TestObservationalDispatch:
    def test_no_plugins_no_crash(self, manager):
        manager.dispatch_after_execute_actions(["summary"])

    def test_calls_all_plugins(self, manager):
        calls = []

        class Logger1(SecondBrainPlugin):
            name = "l1"

            def after_execute_actions(self, summaries):
                calls.append(("l1", summaries))

        class Logger2(SecondBrainPlugin):
            name = "l2"

            def after_execute_actions(self, summaries):
                calls.append(("l2", summaries))

        manager._plugins.extend([Logger1(), Logger2()])
        manager.dispatch_after_execute_actions(["done"])
        assert len(calls) == 2
        assert calls[0] == ("l1", ["done"])
        assert calls[1] == ("l2", ["done"])

    def test_error_does_not_stop_other_plugins(self, manager):
        calls = []

        class Explode(SecondBrainPlugin):
            name = "explode"

            def after_execute_actions(self, summaries):
                raise RuntimeError("boom")

        class Logger(SecondBrainPlugin):
            name = "logger"

            def after_execute_actions(self, summaries):
                calls.append(summaries)

        manager._plugins.extend([Explode(), Logger()])
        manager.dispatch_after_execute_actions(["done"])
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# PluginManager - Graph dispatchers
# ---------------------------------------------------------------------------


class TestGraphDispatchers:
    def test_after_scan_brain_mutation(self, manager):
        class AddNode(SecondBrainPlugin):
            def after_scan_brain(self, nodes, edges):
                return nodes + ["extra"], edges

        manager._plugins.append(AddNode())
        nodes, edges = manager.dispatch_after_scan_brain(["a", "b"], [])
        assert "extra" in nodes

    def test_on_dot_node_mutation(self, manager):
        class BigNode(SecondBrainPlugin):
            def on_dot_node(self, node, attrs):
                attrs["width"] = "3.0"
                return attrs

        manager._plugins.append(BigNode())
        attrs = manager.dispatch_on_dot_node("test", {"label": "test"})
        assert attrs["width"] == "3.0"
        assert attrs["label"] == "test"

    def test_on_dot_edge_mutation(self, manager):
        class RedEdge(SecondBrainPlugin):
            def on_dot_edge(self, src, tgt, attrs):
                attrs["color"] = "red"
                return attrs

        manager._plugins.append(RedEdge())
        attrs = manager.dispatch_on_dot_edge("a", "b", {})
        assert attrs["color"] == "red"

    def test_after_generate_dot_mutation(self, manager):
        class InjectComment(SecondBrainPlugin):
            def after_generate_dot(self, dot):
                return "// Plugin was here\n" + dot

        manager._plugins.append(InjectComment())
        result = manager.dispatch_after_generate_dot("digraph {}")
        assert result.startswith("// Plugin was here")

    def test_before_render_graph_mutation(self, manager):
        class ModifyDot(SecondBrainPlugin):
            def before_render_graph(self, dot):
                return dot.replace("neato", "fdp")

        manager._plugins.append(ModifyDot())
        result = manager.dispatch_before_render_graph("layout=neato")
        assert "fdp" in result


# ---------------------------------------------------------------------------
# PluginManager - Wallpaper dispatchers
# ---------------------------------------------------------------------------


class TestWallpaperDispatchers:
    def test_after_parse_todos_mutation(self, manager):
        class AddTodo(SecondBrainPlugin):
            def after_parse_todos(self, items):
                return items + [(False, "Plugin reminder")]

        manager._plugins.append(AddTodo())
        items = manager.dispatch_after_parse_todos([(False, "existing")])
        assert len(items) == 2
        assert items[1] == (False, "Plugin reminder")

    def test_before_set_wallpaper_observational(self, manager):
        calls = []

        class WpWatcher(SecondBrainPlugin):
            def before_set_wallpaper(self, path):
                calls.append(str(path))

        manager._plugins.append(WpWatcher())
        manager.dispatch_before_set_wallpaper(Path("/tmp/wp.png"))
        assert len(calls) == 1

    def test_after_set_wallpaper_with_status(self, manager):
        calls = []

        class WpLogger(SecondBrainPlugin):
            def after_set_wallpaper(self, path, success):
                calls.append((str(path), success))

        manager._plugins.append(WpLogger())
        manager.dispatch_after_set_wallpaper(Path("/tmp/wp.png"), True)
        assert calls[0][1] is True


# ---------------------------------------------------------------------------
# PluginManager - Janitor dispatchers
# ---------------------------------------------------------------------------


class TestJanitorDispatchers:
    def test_after_janitor_llm_filters_changes(self, manager):
        class VetoAll(SecondBrainPlugin):
            def after_janitor_llm(self, changes):
                return []

        manager._plugins.append(VetoAll())
        changes = [{"file": "a.md", "content": "new"}]
        result = manager.dispatch_after_janitor_llm(changes)
        assert result == []

    def test_before_janitor_write_mutation(self, manager):
        class Stamp(SecondBrainPlugin):
            def before_janitor_write(self, fname, old, new):
                return new + "\n<!-- cleaned -->"

        manager._plugins.append(Stamp())
        result = manager.dispatch_before_janitor_write("test.md", "old content", "new content")
        assert result.endswith("<!-- cleaned -->")

    def test_on_janitor_reject_observational(self, manager):
        calls = []

        class RejectLogger(SecondBrainPlugin):
            def on_janitor_reject(self, fname, reason):
                calls.append((fname, reason))

        manager._plugins.append(RejectLogger())
        manager.dispatch_on_janitor_reject("test.md", "too aggressive")
        assert calls == [("test.md", "too aggressive")]


# ---------------------------------------------------------------------------
# PluginManager - TUI dispatchers
# ---------------------------------------------------------------------------


class TestTuiDispatchers:
    def test_on_file_preview_mutation(self, manager):
        class InjectBanner(SecondBrainPlugin):
            def on_file_preview(self, fname, content):
                return f"[{fname}]\n{content}"

        manager._plugins.append(InjectBanner())
        result = manager.dispatch_on_file_preview("test.md", "# Hello")
        assert result == "[test.md]\n# Hello"

    def test_on_file_selected_observational(self, manager):
        calls = []

        class SelectLogger(SecondBrainPlugin):
            def on_file_selected(self, fname):
                calls.append(fname)

        manager._plugins.append(SelectLogger())
        manager.dispatch_on_file_selected("notes.md")
        assert calls == ["notes.md"]

    def test_on_wikilink_clicked_observational(self, manager):
        calls = []

        class LinkLogger(SecondBrainPlugin):
            def on_wikilink_clicked(self, target):
                calls.append(target)

        manager._plugins.append(LinkLogger())
        manager.dispatch_on_wikilink_clicked("networking")
        assert calls == ["networking"]


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------


class TestBackgroundThreads:
    def test_background_thread_spawned(self, manager, plugin_dir):
        (plugin_dir / "bg.py").write_text(
            "import time\n"
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class Bg(SecondBrainPlugin):\n"
            "    name = 'bg'\n"
            "    def run_background(self, ctx):\n"
            "        time.sleep(60)\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()

        assert len(manager._threads) == 1
        assert manager._threads[0].daemon is True
        assert manager._threads[0].is_alive()

    def test_no_thread_for_base_class(self, manager, plugin_dir):
        (plugin_dir / "nobg.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class NoBg(SecondBrainPlugin):\n"
            "    name = 'nobg'\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()

        assert len(manager._threads) == 0

    def test_background_crash_does_not_propagate(self, manager, plugin_dir):
        (plugin_dir / "crashbg.py").write_text(
            "from second_brain.plugins import SecondBrainPlugin\n"
            "class CrashBg(SecondBrainPlugin):\n"
            "    name = 'crashbg'\n"
            "    def run_background(self, ctx):\n"
            "        raise RuntimeError('bg crash')\n"
        )
        with patch("second_brain.config.get_plugin_dir", return_value=plugin_dir):
            with patch("second_brain.config.get_enabled_plugins", return_value=None):
                with patch("second_brain.config.get_disabled_plugins", return_value=[]):
                    with patch("second_brain.config.get_plugin_config", return_value={}):
                        manager.load_all()

        # Give the thread time to crash
        time.sleep(0.2)
        # Plugin should still be in the list (it loaded fine)
        assert len(manager.plugins) == 1
        # Thread should have died from the error
        assert not manager._threads[0].is_alive()


# ---------------------------------------------------------------------------
# Singleton (get_manager / reset_manager)
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_manager_returns_same_instance(self):
        with patch("second_brain.config.get_plugin_dir", return_value=Path("/nonexistent")):
            m1 = get_manager()
            m2 = get_manager()
        assert m1 is m2

    def test_reset_manager_clears(self):
        with patch("second_brain.config.get_plugin_dir", return_value=Path("/nonexistent")):
            m1 = get_manager()
        reset_manager()
        with patch("second_brain.config.get_plugin_dir", return_value=Path("/nonexistent")):
            m2 = get_manager()
        assert m1 is not m2


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    def test_get_plugin_dir_default(self):
        from second_brain import config

        result = config.get_plugin_dir()
        assert result == config.CONFIG_DIR / "plugins"

    def test_get_enabled_plugins_none_by_default(self):
        from second_brain import config

        with patch.object(config, "_config_cache", {}):
            result = config.get_enabled_plugins()
        assert result is None

    def test_get_enabled_plugins_from_config(self):
        from second_brain import config

        with patch.object(config, "_config_cache", {"plugins": {"enabled": ["alpha", "beta"]}}):
            result = config.get_enabled_plugins()
        assert result == ["alpha", "beta"]

    def test_get_disabled_plugins_empty_by_default(self):
        from second_brain import config

        with patch.object(config, "_config_cache", {}):
            result = config.get_disabled_plugins()
        assert result == []

    def test_get_disabled_plugins_from_config(self):
        from second_brain import config

        with patch.object(config, "_config_cache", {"plugins": {"disabled": ["bad_plugin"]}}):
            result = config.get_disabled_plugins()
        assert result == ["bad_plugin"]

    def test_get_plugin_config_returns_dict(self):
        from second_brain import config

        with patch.object(
            config, "_config_cache", {"plugins": {"config": {"my_plug": {"token": "abc"}}}}
        ):
            result = config.get_plugin_config("my_plug")
        assert result == {"token": "abc"}

    def test_get_plugin_config_missing_returns_empty(self):
        from second_brain import config

        with patch.object(config, "_config_cache", {}):
            result = config.get_plugin_config("nonexistent")
        assert result == {}


# ---------------------------------------------------------------------------
# Integration: plugin modifying data through hooks
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_mutation_chain(self, manager):
        """Simulate a plugin that adds a watermark to all written files."""

        class Watermark(SecondBrainPlugin):
            name = "watermark"

            def before_write_file(self, action, target, content):
                return content + "\n\n<!-- watermark -->"

        class Counter(SecondBrainPlugin):
            name = "counter"

            def __init__(self, cfg=None):
                super().__init__(cfg)
                self.count = 0

            def after_write_file(self, action, target, summary):
                self.count += 1

        counter = Counter()
        manager._plugins.extend([Watermark(), counter])

        # Simulate dispatching a write
        content = manager.dispatch_before_write_file(
            {"type": "create"}, Path("/tmp/test.md"), "# Hello"
        )
        assert "<!-- watermark -->" in content

        manager.dispatch_after_write_file(
            {"type": "create"}, Path("/tmp/test.md"), "CREATE -> test.md"
        )
        assert counter.count == 1

    def test_multiple_mutators_chain_correctly(self, manager):
        """Two mutating plugins should chain their changes."""

        class Prefix(SecondBrainPlugin):
            name = "prefix"

            def before_process_dump(self, text):
                return "[PREFIX] " + text

        class Suffix(SecondBrainPlugin):
            name = "suffix"

            def before_process_dump(self, text):
                return text + " [SUFFIX]"

        manager._plugins.extend([Prefix(), Suffix()])
        result = manager.dispatch_before_process_dump("hello world")
        assert result == "[PREFIX] hello world [SUFFIX]"

    def test_plugin_can_veto_actions(self, manager):
        """Plugin can filter out actions via before_execute_actions."""

        class NoCreates(SecondBrainPlugin):
            name = "no_creates"

            def before_execute_actions(self, actions):
                return [a for a in actions if a.get("type") != "create"]

        manager._plugins.append(NoCreates())
        actions = [
            {"type": "create", "target": "new.md", "content": "stuff"},
            {"type": "append", "target": "old.md", "content": "more"},
            {"type": "todo", "content": "do thing"},
        ]
        result = manager.dispatch_before_execute_actions(actions)
        assert len(result) == 2
        assert all(a["type"] != "create" for a in result)
