"""Configuration and paths for Second Brain.

Loads user config from ~/.config/second_brain/config.json, auto-detects
platform capabilities, and exposes module-level constants for backward
compatibility.

Config file is optional -- everything auto-detects. Run `second-brain setup`
to generate one interactively.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# XDG-aware base paths
# ---------------------------------------------------------------------------

_XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
_XDG_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
_XDG_DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

CONFIG_DIR = _XDG_CONFIG / "second_brain"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Groq
GROQ_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_config_cache: dict | None = None


def _load_config() -> dict:
    """Load user config from config.json, or return empty dict."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                _config_cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            _config_cache = {}
    else:
        _config_cache = {}
    return _config_cache


def reload_config() -> None:
    """Force reload of config from disk."""
    global _config_cache
    _config_cache = None
    _load_config()
    _apply_config()


def _get(key: str, default: Any = None) -> Any:
    """Get a config value by dot-separated key path."""
    cfg = _load_config()
    parts = key.split(".")
    val: Any = cfg
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return default
        if val is None:
            return default
    return val


# ---------------------------------------------------------------------------
# Path config (with sensible defaults)
# ---------------------------------------------------------------------------


def _default_brain_dir() -> Path:
    return Path.home() / "Documents" / "brain"


def _default_wallpaper_output() -> Path:
    return Path.home() / "Pictures" / "active_brain_wallpaper.png"


def _apply_config():
    """Apply loaded config to module-level constants."""
    global BRAIN_DIR, DUMP_FILE, TODO_FILE, GRAPH_OUTPUT, TODO_OVERLAY
    global WALLPAPER_OUTPUT, ORIGINAL_WALLPAPER_CACHE

    brain = _get("paths.brain_dir")
    BRAIN_DIR = Path(str(brain)) if brain else _default_brain_dir()
    DUMP_FILE = BRAIN_DIR / "dump.md"
    TODO_FILE = BRAIN_DIR / "todo.md"

    wp_out = _get("paths.wallpaper_output")
    WALLPAPER_OUTPUT = Path(str(wp_out)) if wp_out else _default_wallpaper_output()

    tmpdir = Path(tempfile.gettempdir())
    GRAPH_OUTPUT = tmpdir / "second_brain_graph_overlay.png"
    TODO_OVERLAY = tmpdir / "second_brain_todo_overlay.png"
    # Persistent cache — survives reboots (unlike /tmp)
    cache_dir = _XDG_CACHE / "second_brain"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ORIGINAL_WALLPAPER_CACHE = cache_dir / "original_wallpaper"

    # Migrate old /tmp cache if it exists
    old_cache = Path(tempfile.gettempdir()) / ".second_brain_original_wallpaper"
    if old_cache.exists() and not ORIGINAL_WALLPAPER_CACHE.exists():
        try:
            ORIGINAL_WALLPAPER_CACHE.write_text(old_cache.read_text())
            old_cache.unlink()
        except OSError:
            pass


# Initialize on import
BRAIN_DIR = _default_brain_dir()
DUMP_FILE = BRAIN_DIR / "dump.md"
TODO_FILE = BRAIN_DIR / "todo.md"
GRAPH_OUTPUT = Path(tempfile.gettempdir()) / "second_brain_graph_overlay.png"
TODO_OVERLAY = Path(tempfile.gettempdir()) / "second_brain_todo_overlay.png"
WALLPAPER_OUTPUT = _default_wallpaper_output()
_cache_dir = _XDG_CACHE / "second_brain"
_cache_dir.mkdir(parents=True, exist_ok=True)
ORIGINAL_WALLPAPER_CACHE = _cache_dir / "original_wallpaper"
_apply_config()


# ---------------------------------------------------------------------------
# Groq API key
# ---------------------------------------------------------------------------


def get_groq_api_key() -> str:
    """Get Groq API key from environment or config file."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        key_file = CONFIG_DIR / "groq_key"
        if key_file.exists():
            key = key_file.read_text().strip()
    if not key:
        raise RuntimeError(
            f"GROQ_API_KEY not set. Export it or place it in {CONFIG_DIR / 'groq_key'}"
        )
    return key


# ---------------------------------------------------------------------------
# Wallpaper backend detection
# ---------------------------------------------------------------------------

# Supported wallpaper setters: (name, detect_cmd, set_cmd_template, query_cmd)
# set_cmd_template uses {path} as placeholder
_WALLPAPER_BACKENDS = [
    {
        "name": "swww",
        "detect": "swww",
        "set_cmd": [
            "swww",
            "img",
            "{path}",
            "--transition-type",
            "fade",
            "--transition-duration",
            "1",
        ],
        "query": "_query_swww",
    },
    {
        "name": "swaybg",
        "detect": "swaybg",
        "set_cmd": ["swaybg", "-i", "{path}", "-m", "fill"],
        "query": None,  # swaybg doesn't support querying
    },
    {
        "name": "hyprpaper",
        "detect": "hyprpaper",
        "set_cmd": "_set_hyprpaper",  # special: requires 2-step hyprctl calls
        "query": "_query_hyprpaper",
    },
    {
        "name": "feh",
        "detect": "feh",
        "set_cmd": ["feh", "--bg-fill", "{path}"],
        "query": "_query_feh",
    },
    {
        "name": "nitrogen",
        "detect": "nitrogen",
        "set_cmd": ["nitrogen", "--set-zoom-fill", "--save", "{path}"],
        "query": "_query_nitrogen",
    },
    {
        "name": "gsettings",  # GNOME / Budgie / Cinnamon
        "detect": "gsettings",
        "set_cmd": [
            "gsettings",
            "set",
            "org.gnome.desktop.background",
            "picture-uri-dark",
            "file://{path}",
        ],
        "query": "_query_gsettings",
    },
]


def _query_swww() -> Path | None:
    """Query current wallpaper from swww."""
    try:
        result = subprocess.run(
            ["swww", "query"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "image:" in line:
                path_str = line.split("image:")[-1].strip()
                p = Path(path_str)
                if p.exists():
                    return p
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _query_hyprpaper() -> Path | None:
    """Query current wallpaper from hyprpaper via hyprctl."""
    try:
        result = subprocess.run(
            ["hyprctl", "hyprpaper", "listloaded"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            p = Path(line.strip())
            if p.exists():
                return p
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _query_feh() -> Path | None:
    """Query current wallpaper from feh's ~/.fehbg file.

    feh writes a script like: feh --bg-fill '/path/to/wallpaper.png'
    """
    fehbg = Path.home() / ".fehbg"
    if not fehbg.exists():
        return None
    try:
        import re

        content = fehbg.read_text()
        # Match quoted or unquoted paths after --bg-fill/--bg-scale/--bg-max/etc.
        m = re.search(r"--bg-\w+\s+['\"]?([^'\"]+\.(png|jpg|jpeg|bmp|webp))", content)
        if m:
            p = Path(m.group(1))
            if p.exists():
                return p
    except OSError:
        pass
    return None


def _query_nitrogen() -> Path | None:
    """Query current wallpaper from nitrogen's bg-saved.cfg.

    The file uses INI format with entries like:
        [xin_-1]
        file=/path/to/wallpaper.png
        mode=5
    """
    cfg_path = _XDG_CONFIG / "nitrogen" / "bg-saved.cfg"
    if not cfg_path.exists():
        return None
    try:
        import configparser

        cp = configparser.ConfigParser()
        cp.read(cfg_path)
        # Return the first section's file= value
        for section in cp.sections():
            f = cp.get(section, "file", fallback=None)
            if f:
                p = Path(f)
                if p.exists():
                    return p
    except Exception:
        pass
    return None


def _query_gsettings() -> Path | None:
    """Query current wallpaper from GNOME gsettings."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "picture-uri-dark"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        uri = result.stdout.strip().strip("'\"")
        if uri.startswith("file://"):
            p = Path(uri[7:])
            if p.exists():
                return p
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_wallpaper_backend() -> str | None:
    """Get the configured or auto-detected wallpaper backend name."""
    configured = _get("wallpaper.backend")
    if configured and isinstance(configured, str):
        return configured

    # Auto-detect: return first available
    for backend in _WALLPAPER_BACKENDS:
        if shutil.which(backend["detect"]):
            return str(backend["name"])
    return None


def _get_backend_config(name: str) -> dict[str, Any] | None:
    """Get backend config dict by name."""
    for b in _WALLPAPER_BACKENDS:
        if b["name"] == name:
            return b  # type: ignore[return-value]
    return None


def get_wallpaper_set_cmd(wallpaper_path: Path) -> list[str] | None:
    """Get the command to set a wallpaper, with path substituted.

    Returns None if no backend is available or the backend needs special
    handling (e.g., hyprpaper which requires multiple commands).
    """
    # Check for user-configured custom command first
    custom = _get("wallpaper.set_cmd")
    if custom:
        return [part.replace("{path}", str(wallpaper_path)) for part in custom]

    backend_name = get_wallpaper_backend()
    if not backend_name:
        return None

    backend = _get_backend_config(backend_name)
    if not backend or not backend["set_cmd"]:
        return None

    set_cmd = backend["set_cmd"]
    # String values starting with _ are function references (special handling)
    if isinstance(set_cmd, str):
        return None

    return [part.replace("{path}", str(wallpaper_path)) for part in set_cmd]


def set_wallpaper_special(wallpaper_path: Path) -> bool:
    """Handle wallpaper setting for backends that need multi-step commands.

    Currently handles: hyprpaper (requires preload + wallpaper via hyprctl).
    Returns True if handled successfully, False if backend doesn't need special handling.
    """
    backend_name = get_wallpaper_backend()
    if backend_name != "hyprpaper":
        return False

    try:
        # hyprpaper requires: preload image, then set it on all monitors
        subprocess.run(
            ["hyprctl", "hyprpaper", "preload", str(wallpaper_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        subprocess.run(
            ["hyprctl", "hyprpaper", "wallpaper", f",{wallpaper_path}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _detect_wallpaper() -> Path | None:
    """Detect the current wallpaper using the configured backend."""
    backend_name = get_wallpaper_backend()
    if not backend_name:
        return None

    backend = _get_backend_config(backend_name)
    if not backend or not backend["query"]:
        return None

    query_fn = backend["query"]
    # Resolve the function name to the actual function
    fn = globals().get(query_fn)
    if fn and callable(fn):
        return fn()
    return None


def get_current_wallpaper() -> Path | None:
    """Get the base wallpaper path, with caching to prevent re-compositing.

    If the user changes their wallpaper externally, the new wallpaper is
    detected and the cache is updated.
    """
    live = _detect_wallpaper()
    cached = None

    if ORIGINAL_WALLPAPER_CACHE.exists():
        cached = Path(ORIGINAL_WALLPAPER_CACHE.read_text().strip())
        if not cached.exists():
            cached = None

    if live and live != WALLPAPER_OUTPUT:
        if cached is None or live != cached:
            ORIGINAL_WALLPAPER_CACHE.write_text(str(live))
        return live

    if cached and cached != WALLPAPER_OUTPUT:
        return cached

    return live


# ---------------------------------------------------------------------------
# Wallpaper restore cache (desktop environment integration)
# ---------------------------------------------------------------------------


def _detect_wallpaper_cache_paths() -> list[Path]:
    """Detect wallpaper cache files used by various DE frameworks.

    These are files that store the current wallpaper path so the DE can
    restore it on login. We update them after compositing so our wallpaper
    persists across logins.
    """
    candidates = [
        # ml4w hyprland dotfiles
        _XDG_CACHE / "ml4w" / "hyprland-dotfiles" / "current_wallpaper",
        # nitrogen (INI format — handled specially in _update_wallpaper_caches)
        _XDG_CONFIG / "nitrogen" / "bg-saved.cfg",
        # feh (shell script — handled specially in _update_wallpaper_caches)
        Path.home() / ".fehbg",
    ]
    return [c for c in candidates if c.parent.exists()]


def get_wallpaper_cache_paths() -> list[Path]:
    """Get wallpaper cache file paths to update after setting wallpaper.

    Uses configured paths if set, otherwise auto-detects.
    """
    configured = _get("wallpaper.cache_files")
    if configured:
        return [Path(p) for p in configured]
    return _detect_wallpaper_cache_paths()


# ---------------------------------------------------------------------------
# Monitor resolution detection
# ---------------------------------------------------------------------------


def _detect_resolution_hyprctl() -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            ["hyprctl", "-j", "monitors"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        monitors = json.loads(result.stdout)
        if monitors:
            m = monitors[0]
            return m["width"], m["height"]
    except Exception:
        pass
    return None


def _detect_resolution_swaymsg() -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            ["swaymsg", "-t", "get_outputs", "--raw"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        outputs = json.loads(result.stdout)
        for out in outputs:
            if out.get("active"):
                mode = out.get("current_mode", {})
                w, h = mode.get("width"), mode.get("height")
                if w and h:
                    return w, h
    except Exception:
        pass
    return None


def _detect_resolution_wlr_randr() -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            ["wlr-randr", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        outputs = json.loads(result.stdout)
        for out in outputs:
            if out.get("enabled"):
                for mode in out.get("modes", []):
                    if mode.get("current"):
                        return mode["width"], mode["height"]
    except Exception:
        pass
    return None


def _detect_resolution_xrandr() -> tuple[int, int] | None:
    import re

    try:
        result = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            # Match lines like: "eDP-1 connected primary 1920x1080+0+0 ..."
            m = re.search(r"\bconnected\b.*?(\d+)x(\d+)\+", line)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


_RESOLUTION_DETECTORS = [
    ("hyprctl", _detect_resolution_hyprctl),
    ("swaymsg", _detect_resolution_swaymsg),
    ("wlr-randr", _detect_resolution_wlr_randr),
    ("xrandr", _detect_resolution_xrandr),
]


def get_monitor_resolution() -> tuple[int, int]:
    """Get primary monitor resolution. Uses config, then auto-detects."""
    configured = _get("display.resolution")
    if configured and isinstance(configured, list) and len(configured) == 2:
        return tuple(configured)

    # Try each detector in order
    for _name, detector in _RESOLUTION_DETECTORS:
        result = detector()
        if result:
            return result

    # Fallback
    return 1920, 1080


# ---------------------------------------------------------------------------
# Font detection
# ---------------------------------------------------------------------------

_PREFERRED_FONTS = [
    # (ImageMagick name, Graphviz/fontconfig name)
    ("JetBrains-Mono-Regular-Nerd-Font-Complete", "JetBrainsMono Nerd Font"),
    ("JetBrains-Mono-Regular", "JetBrains Mono"),
    ("FiraCode-Regular-Nerd-Font-Complete", "FiraCode Nerd Font"),
    ("FiraCode-Regular", "Fira Code"),
    ("DejaVu-Sans-Mono", "DejaVu Sans Mono"),
    ("Liberation-Mono", "Liberation Mono"),
    ("Noto-Mono", "Noto Mono"),
]


def _detect_font() -> tuple[str, str]:
    """Detect the best available monospace font.

    Returns (imagemagick_name, graphviz_name).
    """
    available: set[str] = set()
    try:
        result = subprocess.run(
            ["magick", "-list", "font"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Font:"):
                available.add(line.split(":", 1)[1].strip())
    except Exception:
        pass

    for im_name, gv_name in _PREFERRED_FONTS:
        if im_name in available:
            return im_name, gv_name

    # If no preferred font found, try to find any mono font
    for font in sorted(available):
        lower = font.lower()
        if "mono" in lower or "code" in lower or "courier" in lower:
            return font, font.replace("-", " ")

    # Ultimate fallback (ImageMagick will use its default)
    return "Courier", "Courier"


def get_font() -> tuple[str, str]:
    """Get the font to use for wallpaper and graph rendering.

    Returns (imagemagick_name, graphviz_name).
    """
    im = _get("display.font_imagemagick")
    gv = _get("display.font_graphviz")
    if im and gv and isinstance(im, str) and isinstance(gv, str):
        return im, gv

    return _detect_font()


# ---------------------------------------------------------------------------
# Colors (pywal or config)
# ---------------------------------------------------------------------------

_DEFAULT_COLORS = {
    "colors": {
        "color0": "#1d2021",
        "color1": "#cc241d",
        "color2": "#98971a",
        "color3": "#d79921",
        "color4": "#458588",
        "color5": "#b16286",
        "color6": "#689d6a",
        "color7": "#a89984",
        "color8": "#928374",
        "color9": "#fb4934",
        "color10": "#b8bb26",
        "color11": "#fabd2f",
        "color12": "#83a598",
        "color13": "#d3869b",
        "color14": "#8ec07c",
        "color15": "#ebdbb2",
    },
    "special": {
        "background": "#1d2021",
        "foreground": "#ebdbb2",
    },
}


def get_wal_colors() -> dict:
    """Load color scheme from pywal, config, or fallback defaults.

    Checks (in order):
    1. User-configured colors in config.json
    2. Pywal cache at $XDG_CACHE_HOME/wal/colors.json
    3. Built-in gruvbox-ish defaults
    """
    # 1. User config
    configured = _get("colors")
    if configured and isinstance(configured, dict) and "colors" in configured:
        return configured

    # 2. Pywal
    wal_path = _XDG_CACHE / "wal" / "colors.json"
    if wal_path.exists():
        try:
            with open(wal_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Defaults
    return _DEFAULT_COLORS


# ---------------------------------------------------------------------------
# Brain files
# ---------------------------------------------------------------------------


def get_brain_files() -> list[str]:
    """Return list of .md filenames in the brain directory."""
    if not BRAIN_DIR.exists():
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        return []
    return sorted(f.name for f in BRAIN_DIR.glob("*.md") if f.name != "dump.md")


# ---------------------------------------------------------------------------
# Plugin config
# ---------------------------------------------------------------------------


def get_plugin_dir() -> Path:
    """Return the plugin directory path."""
    configured = _get("plugins.dir")
    if configured and isinstance(configured, str):
        return Path(configured)
    return CONFIG_DIR / "plugins"


def get_enabled_plugins() -> list[str] | None:
    """Return list of enabled plugin names, or None if all are enabled."""
    enabled = _get("plugins.enabled")
    if enabled and isinstance(enabled, list):
        return [str(e) for e in enabled]
    return None


def get_disabled_plugins() -> list[str]:
    """Return list of explicitly disabled plugin names."""
    disabled = _get("plugins.disabled")
    if disabled and isinstance(disabled, list):
        return [str(d) for d in disabled]
    return []


def get_plugin_config(plugin_name: str) -> dict:
    """Return per-plugin config from config.json plugins.config section."""
    cfg = _get(f"plugins.config.{plugin_name}")
    if cfg and isinstance(cfg, dict):
        return cfg
    return {}
