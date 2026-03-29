# Librus Sync Plugin

Automatically sync grades and exams from Librus Synergia to your Second Brain.

## Setup

### 1. Enable the Plugin

Add to `~/.config/second_brain/config.json`:

```json
{
  "plugins": {
    "enabled": ["librus_sync"],
    "config": {
      "librus_sync": {
        "username": "your-librus-username",
        "password": "your-librus-password",
        "auto_sync_on_tui": true
      }
    }
  }
}
```

### 2. Secure Your Credentials

Set restrictive file permissions:

```bash
chmod 600 ~/.config/second_brain/config.json
```

## Usage

### Manual Sync

```bash
second-brain librus
```

This fetches your latest grades and exams from Librus and updates:
- `grades.md` - Full grade history with averages
- `todo.md` - Upcoming exams (past exams auto-removed)

### Auto-Sync on TUI Open

By default, the plugin syncs when you open the TUI. Disable with:

```json
{
  "plugins": {
    "config": {
      "librus_sync": {
        "auto_sync_on_tui": false
      }
    }
  }
}
```

## Output Format

### grades.md

```markdown
# Grades Overview

## Math
| Date | Type | Points | Max Points | Description |
|------|------|--------|------------|-------------|
| 2026-03-15 | Points | 32 | 35 | prawdopodobieństwo rozszerzenie |

**Total: 60/70 (85.7%)**

## Physics
| Date | Type | Grade | Weight | Description |
|------|------|-------|--------|-------------|
| 2026-03-20 | Grade | 4.5 | 1x | Kinematics quiz |

**Average: 4.83**
```

### todo.md

```markdown
# Todos

## Librus Exams (auto-synced)
- [ ] 2026-04-05: Math sprawdzian - prawdopodobieństwo rozszerzenie
- [ ] 2026-04-08: Physics sprawdzian - Kinematics test

## Manual Todos
- [ ] Your manual todos here
```

## Troubleshooting

### Login Fails

- Verify credentials in config.json
- Check if your school uses SSO (not supported yet)
- Ensure internet connection

### No Data Synced

- Check logs: `journalctl -u second-brain` (if using systemd timer)
- Run manually with verbose logging: `second-brain --verbose librus`

### HTML Structure Changed

Librus may update their website. If scraping fails:
1. Check logs for parsing errors
2. Open an issue with the error message
3. Temporarily disable the plugin until fixed

## Security Notes

- Credentials stored in plaintext config file
- Set `chmod 600` on config.json
- All requests use HTTPS
- No credentials are logged
