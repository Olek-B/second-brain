# Librus Sync Plugin - Design Specification

**Date:** 2026-03-29  
**Status:** Draft → Pending Approval

## Overview

A Second Brain plugin that scrapes Librus Synergia (school gradebook) and automatically syncs:
- **Exams** → `todo.md` as dated task items
- **Grades** → `grades.md` with subject-wise tables and average calculations

## Problem Statement

The user needs to track school data (grades, exams) from Librus Synergia in their Second Brain knowledge base. Manual copying is tedious and error-prone. This plugin automates the sync process.

## Requirements

### Functional Requirements

1. **Authentication**
   - Username + password login to `https://synergia.librus.pl/`
   - Credentials stored in config: `plugins.config.librus_sync.username` and `password`

2. **Data Scraping**
   - Scrape exams from Librus calendar/exams page
   - Scrape grades from Librus grades page
   - Handle special Math teacher format: points system (e.g., "35p prawdopodobieństwo rozszerzenie")

3. **Data Writing**
   - **Exams:** Write to `todo.md` as `- [ ] YYYY-MM-DD: Subject exam - Description`
   - **Grades:** Write to `grades.md` with markdown tables per subject
   - **Math subject:** Special handling for points-only grades (show points + max points, calculate percentage)
   - **Other subjects:** Standard grades with weighted average calculation

4. **Sync Behavior**
   - **Replace mode:** Full replacement of exam todos and grades on each sync (single source of truth)
   - **Triggers:**
     - Manual: `second-brain librus` CLI command
     - TUI: Auto-sync when TUI opens (like Telegram pull)
     - Timer: Daily systemd timer at 8 AM

5. **Error Handling**
   - Invalid credentials → log error, show user message
   - Network errors → retry 3 times with exponential backoff
   - Scrape failures (HTML changed) → log error with debug info

### Non-Functional Requirements

1. **Security:** Credentials stored in config file (user responsible for file permissions)
2. **Performance:** Sync should complete in <10 seconds
3. **Reliability:** Graceful degradation — if grades fail, still sync exams and vice versa
4. **Maintainability:** Clear logging, modular scraper code

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Second Brain CLI/TUI                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │           librus_sync Plugin                        │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │    │
│  │  │ LibrusScraper│  │ GradeParser  │  │ ExamParser│ │    │
│  │  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘ │    │
│  │         │                 │                 │       │    │
│  │  ┌──────▼─────────────────▼─────────────────▼─────┐ │    │
│  │  │            LibrusSession (requests.Session)    │ │    │
│  │  └─────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  grades.md      │
                    │  todo.md        │
                    └─────────────────┘
```

### Module Structure

```
second_brain/
  librus_sync.py          # Main plugin module (new file)
  
~/.config/second_brain/plugins/
  librus_sync.py          # Plugin wrapper (symlink or copy)
```

### Data Flow

```
1. User opens TUI / runs CLI command
              │
              ▼
2. Plugin loads credentials from config
              │
              ▼
3. LibrusScraper.login(username, password)
              │
              ▼
4. LibrusScraper.fetch_exams() → List[Exam]
   LibrusScraper.fetch_grades() → List[Grade]
              │
              ▼
5. ExamParser.format_todo(exam) → "- [ ] YYYY-MM-DD: ..."
   GradeParser.format_markdown(grades) → markdown tables
              │
              ▼
6. Write to todo.md (replace exam entries)
   Write to grades.md (full replace)
```

## Implementation Details

### LibrusScraper Class

```python
class LibrusScraper:
    """Handles HTTP session and scraping Librus Synergia."""
    
    BASE_URL = "https://synergia.librus.pl/"
    
    def __init__(self, username: str, password: str):
        self.session = requests.Session()
        self.username = username
        self.password = password
        
    def login(self) -> bool:
        """POST to login endpoint, check for successful auth."""
        pass
        
    def fetch_exams(self) -> list[Exam]:
        """GET /exams page, parse HTML table, return Exam objects."""
        pass
        
    def fetch_grades(self) -> list[Grade]:
        """GET /grades page, parse HTML table, return Grade objects."""
        pass
```

### Data Classes

```python
@dataclass
class Exam:
    date: datetime.date
    subject: str
    description: str
    type: str  # "exam", "quiz", "test", etc.

@dataclass
class Grade:
    date: datetime.date
    subject: str
    grade: str  # "4.5", "5p", etc.
    max_points: int | None  # For points-based grades
    description: str  # Teacher's comment
    weight: int  # Usually 1x, sometimes 2x for tests
```

### grades.md Format

```markdown
# Grades Overview

## Math
| Date | Type | Points | Max Points | Description |
|------|------|--------|------------|-------------|
| 2026-03-15 | Quiz | 32 | 35 | prawdopodobieństwo rozszerzenie |
| 2026-03-20 | Test | 28 | 35 | kombinatoryka |

**Total: 60/70 (85.7%)**

## Physics
| Date | Type | Grade | Weight | Description |
|------|------|-------|--------|-------------|
| 2026-03-15 | Quiz | 4.5 | 1x | Kinematics |
| 2026-03-20 | Test | 5.0 | 2x | Dynamics |

**Average: 4.83**
```

### todo.md Format

Exams are inserted at the top of `todo.md` with a header comment:

```markdown
# Todos

## Librus Exams (auto-synced)
- [ ] 2026-04-05: Math - prawdopodobieństwo rozszerzenie
- [ ] 2026-04-08: Physics - Kinematics test
- [ ] 2026-04-10: Chemistry - Organic chemistry

## Manual Todos
- [ ] Fix DNS config on homelab server
- [ ] Read chapter 5
```

On sync:
1. Remove all entries under "## Librus Exams" section
2. Filter out exams with date < today (auto-remove past exams)
3. Insert fresh exam list (only future/today exams)
4. Keep manual todos intact

**Note:** Past exams are silently removed — they don't go to any archive. If you want to keep a history, check `grades.md` which maintains full grade history.

### Plugin Hooks

| Hook | Purpose |
|------|---------|
| `on_load()` | Initialize scraper, validate config |
| `after_tui_start()` | Trigger auto-sync when TUI opens |
| `do_sync()` | Main sync method (CLI callable) |

### Configuration

Add to `~/.config/second_brain/config.json`:

```json
{
  "plugins": {
    "enabled": ["librus_sync"],
    "config": {
      "librus_sync": {
        "username": "your-username",
        "password": "your-password",
        "auto_sync_on_tui": true
      }
    }
  }
}
```

### CLI Command

Add to `__main__.py`:

```bash
second-brain librus          # Manual sync
second-brain librus --dry-run  # Preview without writing
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Invalid credentials | Log error, print user message, skip sync |
| Network timeout | Retry 3x with 5s, 10s, 20s delays |
| HTML structure changed | Log error with URL, skip affected data type |
| Write failure | Log error, preserve existing files |

## Testing Strategy

1. **Unit tests:**
   - `test_login_success()` / `test_login_failure()`
   - `test_parse_exam_table()`
   - `test_parse_grade_table()`
   - `test_format_math_points()`
   - `test_calculate_weighted_average()`

2. **Integration tests:**
   - Mock HTTP responses with sample Librus HTML
   - Test full sync flow with temp brain directory

3. **Manual testing:**
   - Run against real Librus account
   - Verify grades.md format matches spec
   - Verify todo.md exam entries are dated correctly

## Dependencies

Add to `pyproject.toml`:

```toml
[project.dependencies]
requests = "^2.31.0"
```

## Security Considerations

1. **Credentials in config:** User should set file permissions: `chmod 600 ~/.config/second_brain/config.json`
2. **No credential logging:** Never log password, only username for debug
3. **HTTPS only:** All requests to `https://synergia.librus.pl/`

## Future Enhancements (Out of Scope)

- Homework sync to `todo.md`
- Absence tracking to `daily_note.md`
- Teacher announcements to `dump.md`
- Push notifications for new grades
- Grade change detection (what changed since last sync)

## Open Questions

None — all requirements clarified with user.

---

## Approval

**Design approved by user:** [Pending]  
**Date:** [Pending]
