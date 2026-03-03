# Second Brain

AI-driven markdown knowledge base with graph visualization and wallpaper compositing.

Dump raw thoughts into `dump.md`, and the AI librarian organizes them into
interconnected markdown files with `[[wikilinks]]`. A Graphviz knowledge graph
and todo panel are composited onto your desktop wallpaper. A weekly janitor pass
fixes formatting and adds missing links.

## Features

- **AI Librarian** -- 2-pass architecture (Plan + Write) using Groq API (Llama 3.3 70B).
  Reads raw dumps, decides where content goes, then generates polished markdown
  with full context of the target file.
- **Todo extraction** -- any task-like language in your dumps is automatically
  extracted into `todo.md` as `- [ ] short one-liner` checkboxes.
- **Knowledge graph** -- scans `[[wikilinks]]` across all files, generates a
  Graphviz DOT graph, renders to PNG with pywal-themed colors.
- **Wallpaper compositor** -- layers the graph (right 76%) and todo panel
  (left 20%) onto your current wallpaper via ImageMagick.
- **Janitor** -- weekly AI cleanup that fixes markdown formatting and adds
  missing `[[wikilinks]]`. Safety valve rejects changes that shrink content >20%.
- **TUI** -- Textual terminal interface with sidebar file list, clickable
  wikilinks, and keybindings for all operations.
- **Platform-agnostic** -- auto-detects wallpaper backend, resolution, font,
  and color scheme on any Linux setup. Config file override available.

## Requirements

- Python >= 3.12
- [Graphviz](https://graphviz.org/) (`dot` command)
- [ImageMagick](https://imagemagick.org/) 7+ (`magick` command)
- A [Groq API key](https://console.groq.com/) (free tier works)
- A supported wallpaper backend (see below)

## Installation

```bash
# Clone the repo
git clone https://github.com/Olek-B/second-brain.git
cd second-brain

# Create a virtualenv (recommended on Arch / externally-managed Python)
python -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e .

# Set your Groq API key (pick one)
export GROQ_API_KEY="gsk_..."
# or
mkdir -p ~/.config/second_brain && echo "gsk_..." > ~/.config/second_brain/groq_key
```

## Quick Start

```bash
# Auto-detect your system and generate config
second-brain setup

# Write some raw thoughts
echo "Need to fix the DNS config on the homelab server" >> ~/Documents/brain/dump.md

# Process the dump through the AI librarian
second-brain process

# Generate the knowledge graph and update wallpaper
second-brain graph

# Launch the TUI
second-brain
```

## Commands

| Command   | Description                                        |
|-----------|----------------------------------------------------|
| `tui`     | Launch interactive TUI (default if no command)     |
| `setup`   | Auto-detect system config, generate `config.json`  |
| `process` | Process `dump.md` through the AI librarian         |
| `graph`   | Generate knowledge graph + update wallpaper        |
| `janitor` | AI cleanup pass (formatting + missing wikilinks)   |
| `list`    | List all brain files                               |
| `dot`     | Output raw DOT graph to stdout (for debugging)     |

### Flags

- `--no-wallpaper` -- generate graph PNG without setting wallpaper
- `--dry-run` -- preview janitor changes without writing files

## TUI Keybindings

| Key | Action                     |
|-----|----------------------------|
| `e` | Edit selected file in `$EDITOR` |
| `d` | Edit `dump.md`             |
| `p` | Process dump through AI    |
| `g` | Regenerate graph + wallpaper |
| `j` | Run janitor cleanup        |
| `r` | Refresh file list          |
| `q` | Quit                       |

Click any `[[wikilink]]` in the preview pane to navigate to that file.

## Supported Platforms

**Wallpaper backends** (auto-detected in order):

| Backend    | Session  | Notes                                  |
|------------|----------|----------------------------------------|
| swww       | Wayland  | Hyprland / wlroots compositors         |
| swaybg     | Wayland  | Sway default                           |
| hyprpaper  | Wayland  | 2-step set via `hyprctl`               |
| feh        | X11      | Reads/writes `~/.fehbg`               |
| nitrogen   | X11      | Reads/writes INI config                |
| gsettings  | X11/Wayland | GNOME / Budgie / Cinnamon           |

**Resolution detection**: hyprctl > swaymsg > wlr-randr > xrandr > fallback 1920x1080

**Font detection**: Scans ImageMagick font list for monospace fonts. Prefers
JetBrainsMono Nerd Font, falls back through FiraCode, DejaVu Sans Mono, etc.

**Color scheme**: pywal > config file > built-in gruvbox defaults.

## Architecture

```
dump.md  -->  [Librarian Pass 1: Plan]  -->  [Librarian Pass 2: Write]  -->  brain/*.md
                                                                               |
brain/*.md  -->  [Graph Engine]  -->  graph.png  --+                           |
                                                   |                           |
todo.md  -->  [Todo Renderer]  -->  todo.png  -----+--->  [Compositor]  -->  wallpaper
                                                   |
                                    base wallpaper -+
```

See [docs/architecture.md](docs/architecture.md) for details.

## Configuration

Config lives at `~/.config/second_brain/config.json`. Generate it with
`second-brain setup` or create manually.

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Systemd Timer

A systemd user timer runs the janitor every Sunday at 10:00 AM:

```bash
# Install the timer (files are in the repo)
cp second-brain-janitor.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now second-brain-janitor.timer
```

## Project Structure

```
second_brain/
  __init__.py      -- version string
  __main__.py      -- CLI entry point (argparse)
  config.py        -- XDG paths, config loading, auto-detection
  setup.py         -- system detection + interactive config generation
  librarian.py     -- 2-pass AI dump processor (Plan + Write)
  graph.py         -- brain scanner, DOT generator, PNG renderer
  wallpaper.py     -- todo overlay + wallpaper compositor + setter
  janitor.py       -- weekly AI formatting + wikilink cleanup
  tui.py           -- Textual TUI with clickable wikilinks
tests/
  test_config.py   -- config loading, path defaults, brain file listing
  test_graph.py    -- brain scanning, DOT generation
  test_librarian.py -- JSON repair, response parsing, action validation
  test_wallpaper.py -- todo parsing
  test_janitor.py  -- safety valve validation
```

## License

MIT
