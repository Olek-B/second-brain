# Configuration Reference

Second Brain uses a JSON config file at `~/.config/second_brain/config.json`.
All fields are optional -- the system auto-detects everything. Run
`second-brain setup` to generate a config interactively.

## Example Config

```json
{
  "paths": {
    "brain_dir": "/home/user/Documents/brain",
    "wallpaper_output": "/home/user/Pictures/active_brain_wallpaper.png"
  },
  "wallpaper": {
    "backend": "swww",
    "set_cmd": ["swww", "img", "{path}", "--transition-type", "fade"],
    "cache_files": [
      "/home/user/.cache/ml4w/hyprland-dotfiles/current_wallpaper"
    ]
  },
  "display": {
    "resolution": [1920, 1080],
    "font_imagemagick": "JetBrains-Mono-Regular-Nerd-Font-Complete",
    "font_graphviz": "JetBrainsMono Nerd Font"
  },
  "colors": {
    "colors": {
      "color0": "#1d2021",
      "color1": "#cc241d",
      "color15": "#ebdbb2"
    },
    "special": {
      "background": "#1d2021",
      "foreground": "#ebdbb2"
    }
  }
}
```

## Fields

### `paths`

| Key                | Type   | Default                          | Description                              |
|--------------------|--------|----------------------------------|------------------------------------------|
| `brain_dir`        | string | `~/Documents/brain`              | Directory containing markdown files      |
| `wallpaper_output` | string | `~/Pictures/active_brain_wallpaper.png` | Where composited wallpaper is saved |

### `wallpaper`

| Key          | Type     | Default       | Description                                    |
|--------------|----------|---------------|------------------------------------------------|
| `backend`    | string   | auto-detected | Wallpaper setter: swww, swaybg, hyprpaper, feh, nitrogen, gsettings |
| `set_cmd`    | string[] | auto          | Custom wallpaper set command. `{path}` is replaced with the image path |
| `cache_files`| string[] | auto-detected | DE cache files to update after setting wallpaper |

**Backend detection order**: swww > swaybg > hyprpaper > feh > nitrogen > gsettings

**Cache file auto-detection** checks for:
- `~/.cache/ml4w/hyprland-dotfiles/current_wallpaper` (ml4w dotfiles)
- `~/.config/nitrogen/bg-saved.cfg` (nitrogen, INI format)
- `~/.fehbg` (feh, shell script)

### `display`

| Key                | Type    | Default       | Description                             |
|--------------------|---------|---------------|-----------------------------------------|
| `resolution`       | [w, h]  | auto-detected | Monitor resolution in pixels            |
| `font_imagemagick` | string  | auto-detected | Font name for ImageMagick (`magick -list font`) |
| `font_graphviz`    | string  | auto-detected | Font name for Graphviz/fontconfig       |

**Resolution detection order**: hyprctl > swaymsg > wlr-randr > xrandr > 1920x1080

**Font detection**: scans ImageMagick's font list for monospace fonts, prefers:
1. JetBrainsMono Nerd Font
2. JetBrains Mono
3. FiraCode Nerd Font
4. FiraCode
5. DejaVu Sans Mono
6. Liberation Mono
7. Noto Mono
8. Any font with "mono", "code", or "courier" in its name
9. Courier (ultimate fallback)

### `colors`

Overrides the pywal color scheme. Must follow the pywal `colors.json` format
with `colors` and `special` sub-objects.

If not set, colors are loaded from `$XDG_CACHE_HOME/wal/colors.json` (pywal).
If pywal is unavailable, built-in gruvbox defaults are used.

## Groq API Key

The API key is loaded from (in order):
1. `$GROQ_API_KEY` environment variable
2. `~/.config/second_brain/groq_key` file (plain text, one line)

## XDG Base Directories

The following XDG variables are respected:
- `$XDG_CONFIG_HOME` -- defaults to `~/.config`
- `$XDG_CACHE_HOME` -- defaults to `~/.cache`
- `$XDG_DATA_HOME` -- defaults to `~/.local/share`

Cache files are stored in `$XDG_CACHE_HOME/second_brain/`:
- `original_wallpaper` -- cached path to the base wallpaper (prevents re-compositing loops)

## Brain Directory Structure

```
~/Documents/brain/
  dump.md          -- raw thoughts input (cleared after processing)
  todo.md          -- extracted tasks (auto-generated)
  *.md             -- knowledge base files (created by librarian)
  .janitor_log     -- janitor run history
```

Files named `dump.md` are excluded from the file list and graph.
All other `.md` files are treated as knowledge base entries.
