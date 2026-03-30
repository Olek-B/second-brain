# Development Guide

## Setup

```bash
# Clone the repo
git clone https://github.com/Olek-B/second-brain.git
cd second-brain

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Set Groq API key (choose one)
export GROQ_API_KEY="gsk_..."
# or
mkdir -p ~/.config/second_brain && echo "gsk_..." > ~/.config/second_brain/groq_key
```

## Running Commands

```bash
# Launch TUI (default)
second-brain

# Auto-detect system and generate config
second-brain setup

# Process dump.md through AI librarian
second-brain process

# Generate knowledge graph and update wallpaper
second-brain graph
second-brain graph --no-wallpaper  # Skip wallpaper update

# Run janitor cleanup
second-brain janitor
second-brain janitor --dry-run  # Preview changes

# AI Q&A
second-brain ask "your question here"

# List brain files
second-brain list

# Check for broken/orphaned links
second-brain check-links

# Create/open today's daily note
second-brain daily

# Tag management
second-brain tags          # List all tags
second-brain tag dns       # Show files with #dns

# Find duplicates
second-brain duplicates

# Investment tracking
second-brain invest "{ale} allegro - 3 - 25.50"
second-brain invest --refresh  # Refresh all prices

# RSS management
second-brain rss             # List feeds
second-brain rss --add "Name" "URL"  # Add feed
second-brain rss --remove "Name"     # Remove feed

# Analytics
second-brain analytics       # Show dashboard
second-brain analytics --days 30     # Last 30 days
second-brain analytics --export json # Export as JSON
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=second_brain

# Run specific test file
pytest tests/test_config.py
pytest tests/test_librarian.py -v

# Run integration tests
pytest tests/test_rss_integration.py
pytest tests/test_wallpaper_integration.py
pytest tests/test_cli.py
```

## Linting and Type Checking

```bash
# Linting
ruff check second_brain/ tests/

# Formatting
ruff format second_brain/ tests/

# Type checking
mypy second_brain/
```

## Project Structure

```
second_brain/
  __init__.py          # Version string
  __main__.py          # CLI entry point (re-exports from cli/)
  
  cli/                 # CLI package
    __init__.py
    main.py           # Argument parsing, command dispatch
    commands.py       # All _run_* handlers
  
  tui/                 # TUI package
    __init__.py
    app.py            # BrainApp class
    widgets.py        # Custom widgets
    actions.py        # Action handlers
    styles.py         # CSS definitions
  
  wallpaper/           # Wallpaper package
    __init__.py
    overlays.py       # Render overlay PNGs
    composite.py      # Composite wallpaper
    setter.py         # Set wallpaper
    utils.py          # Helper functions
  
  config.py           # Configuration loading
  setup.py            # System detection
  librarian.py        # AI dump processor
  graph.py            # Knowledge graph
  ask.py              # AI Q&A
  daily_note.py       # Daily notes
  tags.py             # Tag system
  duplicates.py       # Duplicate detection
  investments.py      # Investment tracking
  analytics.py        # Personal analytics
  rss_reader.py       # RSS feed parsing
  plugins.py          # Plugin manager
  plugin_base.py      # Plugin base class
  plugin_manager.py   # Plugin dispatch
  prompts.py          # LLM prompts

tests/
  test_*.py           # Test modules

docs/
  architecture.md     # Architecture documentation
  configuration.md    # Configuration reference
```

## Adding New Features

1. **Create feature branch**: `git checkout -b feature/my-feature`

2. **Write tests first (TDD)**:
   - Add unit tests in `tests/test_<module>.py`
   - Add integration tests if needed

3. **Implement feature**:
   - Follow existing code patterns
   - Add type hints
   - Add docstrings

4. **Run quality checks**:
   ```bash
   ruff check second_brain/ tests/
   ruff format second_brain/ tests/
   mypy second_brain/
   pytest
   ```

5. **Commit with conventional commits**:
   ```bash
   git add .
   git commit -m "feat: add my new feature"
   ```

## Plugin Development

The plugin system provides hooks for extending Second Brain functionality.

### Available Hooks

**Lifecycle:**
- `on_load(ctx)` - Called when plugin loads
- `on_unload()` - Called when plugin unloads
- `run_background(ctx)` - Long-running background tasks

**Librarian:**
- `before_process_dump(dump_text)` - Transform dump text
- `after_plan(plan)` - Modify AI plan
- `before_write_action(action, existing_content)` - Modify action
- `after_write_action(action)` - Observe write
- `before_execute_actions(actions)` - Modify actions before write
- `after_execute_actions(actions, summaries)` - Observe execution

**Todos:**
- `before_write_todos(todo_items)` - Filter/transform todos
- `after_write_todos(count)` - Observe todo write

**Tags:**
- `before_extract_tags(content)` - Observe extraction
- `after_extract_tags(tags)` - Modify tags

**Wallpaper:**
- `before_parse_todos()` - Observe parse
- `after_parse_todos(items)` - Modify items
- `before_render_todo_overlay(items)` - Observe render
- `after_render_todo_overlay(output_path)` - Observe complete
- `before_set_wallpaper(wallpaper_path)` - Observe set
- `after_set_wallpaper(wallpaper_path, success)` - Observe result

**TUI:**
- `on_tui_start(app)` - Observe TUI start
- `on_file_preview(content)` - Modify preview
- `on_file_selected(filename)` - Observe selection
- `on_wikilink_clicked(target)` - Observe click

### Example Plugin

```python
# ~/.config/second_brain/plugins/my_plugin.py
from second_brain.plugin_base import SecondBrainPlugin


class MyPlugin(SecondBrainPlugin):
    name = "my_plugin"
    
    def on_load(self, ctx):
        print(f"Plugin {self.name} loaded!")
    
    def after_extract_tags(self, tags):
        # Add custom tags
        tags.append("auto-tagged")
        return tags
```

### Enable Plugin

Add to `~/.config/second_brain/config.json`:
```json
{
  "plugins": {
    "enabled": ["my_plugin"]
  }
}
```

## Debugging

```bash
# Enable verbose logging
second-brain --verbose process

# View plugin logs
journalctl --user -u second-brain-boot-sync.service

# Check current wallpaper
second-brain graph --no-wallpaper
```

## Common Issues

**"GROQ_API_KEY not set"**
- Export: `export GROQ_API_KEY="gsk_..."`
- Or create: `~/.config/second_brain/groq_key`

**"Wallpaper not set"**
- Run: `second-brain setup`
- Check backend: `swww status` or `gsettings get org.gnome.desktop.background picture-uri`

**"Module not found: feedparser"**
- Install: `pip install feedparser`

**"python-telegram-bot not installed"**
- Install: `pip install python-telegram-bot`
