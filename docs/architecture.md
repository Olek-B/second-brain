# Architecture

## Overview

Second Brain is a local-first, AI-augmented markdown knowledge base. All data
lives as plain `.md` files in `~/Documents/brain/`. The AI (Groq Llama 3.3 70B)
handles organization and cleanup but never has persistent access -- it runs
on-demand when you invoke a command.

## Data Flow

```
User writes raw thoughts
        |
        v
  ~/Documents/brain/dump.md
        |
        v
  [Librarian: Pass 1 - Plan]
  Reads dump + existing file list
  Returns JSON plan: {actions: [{type, target, description, excerpt, wikilinks}]}
        |
        v
  [Librarian: Pass 2 - Write]
  For each create/append action:
    Sends plan entry + target file content -> LLM
    Returns polished markdown
        |
        v
  brain/*.md files updated/created
  todo.md updated with extracted tasks
        |
        v
  [Graph Engine]
  Scans all .md files for [[wikilinks]]
  Generates DOT graph with pywal colors
  Renders PNG via graphviz
        |
        v
  [Wallpaper Compositor]
  Layers:  base wallpaper + todo panel (left 20%) + graph (right 76%)
  Sets via detected backend (swww/feh/nitrogen/etc.)
```

## Module Responsibilities

### `config.py` (673 lines)

The central configuration module. Handles:

- **XDG paths**: `$XDG_CONFIG_HOME/second_brain/`, `$XDG_CACHE_HOME/second_brain/`
- **Config file loading**: `config.json` with dot-path accessor (`_get("display.resolution")`)
- **Groq API key**: from `$GROQ_API_KEY` env var or `~/.config/second_brain/groq_key`
- **Wallpaper backend detection**: ordered chain of 6 backends (swww, swaybg, hyprpaper, feh, nitrogen, gsettings)
- **Wallpaper query functions**: backend-specific parsers for current wallpaper path (swww output, feh shell script, nitrogen INI, gsettings dconf, hyprpaper via hyprctl)
- **Wallpaper caching**: stores original wallpaper in `~/.cache/second_brain/original_wallpaper` to prevent re-compositing loops
- **Resolution detection**: hyprctl JSON > swaymsg > wlr-randr > xrandr regex > 1920x1080 fallback
- **Font detection**: scans `magick -list font` for monospace fonts, returns (imagemagick_name, graphviz_name)
- **Color loading**: pywal `colors.json` > config > gruvbox defaults
- **DE cache integration**: detects ml4w, nitrogen, feh cache files for wallpaper persistence across logins

### `setup.py` (218 lines)

System detection and config generation:

- Detects session type (Wayland/X11), compositor (Hyprland/Sway/GNOME/i3/etc.)
- Probes all wallpaper backends and resolution detectors
- Detects best available font
- Checks for required tools (magick, dot)
- Generates `config.json` with detected values
- Interactive mode lets user override the brain directory path

### `librarian.py` (477 lines)

The AI dump processor. Two-pass architecture:

**Pass 1 (Plan)**: Sends dump text + existing file list to the LLM. Returns a
lightweight JSON plan with action types (create/append/todo), targets,
descriptions, excerpts, and wikilink lists. Todos are fully resolved here
(just a one-liner task string).

**Pass 2 (Write)**: For each create/append action, sends the plan entry +
target file's existing content to the LLM. Gets back polished markdown that
fits the file's style.

Key components:
- `PLAN_SYSTEM_PROMPT` -- instructs LLM on action types and JSON schema
- `WRITE_SYSTEM_PROMPT` -- instructs LLM on markdown style and wikilinks
- `_repair_json()` -- character-by-character JSON repair for LLM output
  that contains unescaped newlines, quotes, trailing commas
- `parse_llm_response()` -- 3-stage parse: raw > strip fences > full repair
- `_validate_actions()` -- normalizes filenames to snake_case, ensures .md extension
- `execute_actions()` -- writes files, batches todo items into `todo.md`

### `graph.py` (209 lines)

Brain scanner and graph renderer:

- `scan_brain()` -- globs `*.md`, extracts `[[wikilinks]]` via regex,
  returns (nodes, edges) with deduplication
- `generate_dot()` -- builds DOT string with pywal-themed node colors,
  transparent background, neato layout, sized to right 76% of screen
- `render_graph()` -- writes DOT to temp file, renders via `dot -Tpng`,
  falls back to `neato` layout on failure

### `wallpaper.py` (331 lines)

Wallpaper overlay and compositor:

- `_parse_todos()` -- parses `todo.md` for `- [ ]` / `- [x]` checkboxes
- `render_todo_overlay()` -- renders pending todos as transparent PNG using
  ImageMagick (semi-transparent dark panel, pywal colors, truncation at 42 chars)
- `composite_wallpaper()` -- layers base wallpaper + todo panel (NorthWest) +
  graph (East) using ImageMagick composite operations
- `set_wallpaper()` -- sets via detected backend, handles hyprpaper 2-step
- `_update_wallpaper_caches()` -- updates DE-specific cache files (ml4w plain text,
  nitrogen INI, feh shell script) so wallpaper persists across logins
- `refresh_wallpaper()` -- full pipeline: render graph > composite > set

### `janitor.py` (214 lines)

Weekly AI cleanup:

- Sends all brain files in a single batch to the LLM
- LLM returns only changed files with formatting fixes and added `[[wikilinks]]`
- Safety valve: rejects changes that shrink content by >20%
- Token estimation (~4 chars/token) with 30K token limit
- Logs runs to `.janitor_log`

### `tui.py` (368 lines)

Textual TUI:

- `FileList` -- sidebar `ListView` of brain files
- `PreviewLine` -- `Static` subclass with `Rich.Text` objects for clickable wikilinks.
  Computes click targets via offset math (handles word wrapping by calculating
  `offset = event.y * widget_width + event.x`)
- `PreviewPane` -- `VerticalScroll` container mounting `PreviewLine` widgets
- `BrainApp` -- main app with keybindings, threaded workers for AI operations,
  `$EDITOR` integration via `app.suspend()`

### `__main__.py` (138 lines)

CLI with argparse. Commands: tui, setup, process, graph, janitor, list, dot.
Lazy imports per command to keep startup fast.

## Design Decisions

### 2-Pass Librarian

A single-pass approach often produces content that doesn't match the target
file's style or misses context. The 2-pass approach:
1. Pass 1 is cheap (small JSON output) and handles the hard decision of WHERE
2. Pass 2 has full file context and produces better content

### JSON Repair

LLMs frequently produce broken JSON with literal newlines inside strings,
unescaped quotes, and trailing commas. The `_repair_json()` function walks
character-by-character tracking string state and fixes these issues.
`response_format={"type": "json_object"}` on the Groq call helps but doesn't
eliminate the problem entirely.

### Platform Detection Chains

Each capability (wallpaper, resolution, font, colors) uses an ordered chain of
detection methods. The first one that works wins. Config file overrides skip
detection entirely. This makes the system work on Hyprland, Sway, i3, GNOME,
and anything else without code changes.

### Wallpaper Caching

The original wallpaper path is cached in `~/.cache/second_brain/original_wallpaper`
(not `/tmp`, which is lost on reboot). The system queries the live wallpaper
first, so changing wallpaper externally is detected and the cache updates.

### Rich.Text for Wikilinks

`RichLog` with `markup=True` interprets `[[` as Rich's escape sequence and
eats wikilinks. Using `Rich.Text` objects with explicit styles avoids this.
`Horizontal` layout doesn't word-wrap, so `PreviewLine` uses `Static` with
auto height and offset math for click targeting.
