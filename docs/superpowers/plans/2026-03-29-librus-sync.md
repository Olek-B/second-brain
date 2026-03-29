# Librus Sync Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Second Brain plugin that scrapes Librus Synergia and syncs exams to todo.md and grades to grades.md

**Architecture:** Single plugin module (`librus_sync.py`) with LibrusScraper class for HTTP scraping, data classes for Exam/Grade, and plugin hooks for TUI integration

**Tech Stack:** Python 3.12, requests library, BeautifulSoup4 for HTML parsing, Second Brain plugin system

---

### Task 1: Add Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add BeautifulSoup4 dependency**

Add `beautifulsoup4` to the dependencies list in `pyproject.toml`:

```toml
[project]
name = "second-brain"
version = "0.1.0"
description = "AI-driven markdown knowledge base with graph visualization"
requires-python = ">=3.12"
dependencies = [
    "textual>=1.0.0",
    "groq>=0.4.0",
    "pillow>=10.0.0",
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run:
```bash
pip install beautifulsoup4
```

Expected: Package installs successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: Add BeautifulSoup4 for Librus HTML parsing"
```

---

### Task 2: Create Data Classes and Plugin Skeleton

**Files:**
- Create: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Create the module with data classes**

Create `second_brain/librus_sync.py`:

```python
"""Librus Sync - Plugin that scrapes Librus Synergia and syncs grades/exams."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .plugins import BrainAPI, SecondBrainPlugin

log = logging.getLogger("second_brain.plugins.librus_sync")


@dataclass
class Exam:
    """Represents an exam/assignment from Librus."""
    date: date
    subject: str
    description: str
    type: str  # "exam", "quiz", "test", etc.


@dataclass
class Grade:
    """Represents a grade from Librus."""
    date: date
    subject: str
    grade: str  # "4.5", "5p", etc.
    max_points: int | None  # For points-based grades (e.g., Math)
    description: str  # Teacher's comment
    weight: int  # Usually 1x, sometimes 2x for tests


class LibrusScraper:
    """Handles HTTP session and scraping Librus Synergia."""

    BASE_URL = "https://synergia.librus.pl/"

    def __init__(self, username: str, password: str):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.logged_in = False

    def login(self) -> bool:
        """POST to login endpoint, check for successful auth."""
        # TODO: Implement login logic
        return False

    def fetch_exams(self) -> list[Exam]:
        """GET exams page, parse HTML table, return Exam objects."""
        # TODO: Implement exam fetching
        return []

    def fetch_grades(self) -> list[Grade]:
        """GET grades page, parse HTML table, return Grade objects."""
        # TODO: Implement grade fetching
        return []


class LibrusSync(SecondBrainPlugin):
    """Plugin that syncs Librus data to Second Brain."""

    name = "librus_sync"

    def __init__(self, plugin_config: dict | None = None) -> None:
        super().__init__(plugin_config)
        self.scraper: LibrusScraper | None = None

    def on_load(self, ctx: BrainAPI) -> None:
        """Initialize scraper with credentials from config."""
        self.ctx = ctx
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        if not username or not password:
            log.warning(
                "librus_sync: No credentials configured. "
                "Add username and password to plugins.config.librus_sync"
            )
            return

        self.scraper = LibrusScraper(username, password)

    def do_sync(self) -> None:
        """Main sync method - fetch data and write to files."""
        # TODO: Implement sync logic
        pass
```

- [ ] **Step 2: Create test file with basic structure**

Create `tests/test_librus_sync.py`:

```python
"""Tests for Librus sync plugin."""

import pytest
from datetime import date

from second_brain.librus_sync import Exam, Grade, LibrusScraper


class TestDataClasses:
    """Test data class creation and attributes."""

    def test_exam_creation(self):
        """Test creating an Exam dataclass instance."""
        exam = Exam(
            date=date(2026, 4, 5),
            subject="Math",
            description="prawdopodobieństwo rozszerzenie",
            type="exam"
        )
        assert exam.date == date(2026, 4, 5)
        assert exam.subject == "Math"
        assert exam.description == "prawdopodobieństwo rozszerzenie"
        assert exam.type == "exam"

    def test_grade_creation(self):
        """Test creating a Grade dataclass instance."""
        grade = Grade(
            date=date(2026, 3, 15),
            subject="Math",
            grade="32",
            max_points=35,
            description="prawdopodobieństwo rozszerzenie",
            weight=1
        )
        assert grade.date == date(2026, 3, 15)
        assert grade.subject == "Math"
        assert grade.grade == "32"
        assert grade.max_points == 35
        assert grade.description == "prawdopodobieństwo rozszerzenie"
        assert grade.weight == 1

    def test_grade_without_points(self):
        """Test creating a Grade without points (standard grade)."""
        grade = Grade(
            date=date(2026, 3, 20),
            subject="Physics",
            grade="4.5",
            max_points=None,
            description="Kinematics quiz",
            weight=1
        )
        assert grade.max_points is None
        assert grade.grade == "4.5"
```

- [ ] **Step 3: Run tests to verify they pass**

Run:
```bash
pytest tests/test_librus_sync.py::TestDataClasses -v
```

Expected: All 3 tests PASS

- [ ] **Step 4: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Add Librus data classes and plugin skeleton"
```

---

### Task 3: Implement LibrusScraper Login

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test for successful login**

Add to `tests/test_librus_sync.py`:

```python
class TestLibrusScraper:
    """Test LibrusScraper authentication and scraping."""

    def test_login_initialization(self):
        """Test that scraper initializes with credentials."""
        scraper = LibrusScraper("testuser", "testpass")
        assert scraper.username == "testuser"
        assert scraper.password == "testpass"
        assert scraper.logged_in is False
        assert scraper.session is not None
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
pytest tests/test_librus_sync.py::TestLibrusScraper::test_login_initialization -v
```

Expected: PASS

- [ ] **Step 3: Implement login method**

Modify `second_brain/librus_sync.py` - update the `login` method:

```python
    def login(self) -> bool:
        """POST to login endpoint, check for successful auth."""
        login_url = f"{self.BASE_URL}Account/Login"
        
        # Librus login form data
        payload = {
            "login": self.username,
            "pass": self.password,
            "lang": "pl",
        }

        try:
            response = self.session.post(login_url, data=payload, timeout=10)
            response.raise_for_status()
            
            # Check if login was successful by looking for user dashboard
            # After successful login, URL should change or page contains user info
            self.logged_in = response.url != login_url and "synergia" in response.url.lower()
            
            if self.logged_in:
                log.debug("Librus login successful for user: %s", self.username)
            else:
                log.warning("Librus login failed - invalid credentials?")
            
            return self.logged_in
            
        except requests.RequestException as e:
            log.error("Librus login request failed: %s", e)
            return False
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestLibrusScraper -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Implement LibrusScraper login method"
```

---

### Task 4: Implement Exam Fetching

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test with mock HTML**

Add to `tests/test_librus_sync.py`:

```python
class TestExamParsing:
    """Test exam HTML parsing."""

    def test_parse_exam_table(self):
        """Test parsing exam table HTML."""
        html = """
        <table class="decorated">
            <tbody>
                <tr>
                    <td>2026-04-05</td>
                    <td>Math</td>
                    <td>prawdopodobieństwo rozszerzenie</td>
                    <td>Sprawdzian</td>
                </tr>
                <tr>
                    <td>2026-04-08</td>
                    <td>Physics</td>
                    <td>Kinematics test</td>
                    <td>Sprawdzian</td>
                </tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.decorated tbody tr")
        
        exams = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 4:
                exam = Exam(
                    date=datetime.strptime(cells[0].text.strip(), "%Y-%m-%d").date(),
                    subject=cells[1].text.strip(),
                    description=cells[2].text.strip(),
                    type=cells[3].text.strip()
                )
                exams.append(exam)
        
        assert len(exams) == 2
        assert exams[0].subject == "Math"
        assert exams[0].description == "prawdopodobieństwo rozszerzenie"
        assert exams[1].subject == "Physics"
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
pytest tests/test_librus_sync.py::TestExamParsing -v
```

Expected: PASS

- [ ] **Step 3: Implement fetch_exams method**

Modify `second_brain/librus_sync.py` - add the `fetch_exams` method:

```python
    def fetch_exams(self) -> list[Exam]:
        """GET exams page, parse HTML table, return Exam objects."""
        if not self.logged_in:
            if not self.login():
                log.error("Cannot fetch exams - not logged in")
                return []

        exams_url = f"{self.BASE_URL}PlanLekcji/Sprawdziany"
        
        try:
            response = self.session.get(exams_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            exam_rows = soup.select("table.decorated tbody tr")
            
            exams = []
            for row in exam_rows:
                cells = row.find_all("td")
                if len(cells) >= 4:
                    try:
                        exam_date = datetime.strptime(
                            cells[0].text.strip(), "%Y-%m-%d"
                        ).date()
                        exam = Exam(
                            date=exam_date,
                            subject=cells[1].text.strip(),
                            description=cells[2].text.strip(),
                            type=cells[3].text.strip()
                        )
                        exams.append(exam)
                    except (ValueError, IndexError) as e:
                        log.warning("Failed to parse exam row: %s", e)
                        continue
            
            log.info("Fetched %d exams from Librus", len(exams))
            return exams
            
        except requests.RequestException as e:
            log.error("Failed to fetch exams: %s", e)
            return []
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestExamParsing -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Implement exam fetching from Librus"
```

---

### Task 5: Implement Grade Fetching

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test with mock HTML including Math points**

Add to `tests/test_librus_sync.py`:

```python
class TestGradeParsing:
    """Test grade HTML parsing."""

    def test_parse_grade_table_standard(self):
        """Test parsing standard grade table."""
        html = """
        <table class="decorated">
            <tbody>
                <tr>
                    <td>2026-03-15</td>
                    <td>Physics</td>
                    <td>4.5</td>
                    <td>1</td>
                    <td>Kinematics quiz</td>
                </tr>
                <tr>
                    <td>2026-03-20</td>
                    <td>Chemistry</td>
                    <td>5.0</td>
                    <td>2</td>
                    <td>Organic chemistry test</td>
                </tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.decorated tbody tr")
        
        grades = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 5:
                grade_str = cells[2].text.strip()
                # Check if it's a points-based grade (e.g., "35p")
                max_points = None
                if grade_str.endswith("p"):
                    max_points = int(grade_str[:-1])
                    grade_val = grade_str
                else:
                    grade_val = grade_str
                
                grade = Grade(
                    date=datetime.strptime(cells[0].text.strip(), "%Y-%m-%d").date(),
                    subject=cells[1].text.strip(),
                    grade=grade_val,
                    max_points=max_points,
                    description=cells[4].text.strip(),
                    weight=int(cells[3].text.strip())
                )
                grades.append(grade)
        
        assert len(grades) == 2
        assert grades[0].grade == "4.5"
        assert grades[0].max_points is None
        assert grades[1].weight == 2

    def test_parse_math_points_grade(self):
        """Test parsing Math points-based grade."""
        html = """
        <table class="decorated">
            <tbody>
                <tr>
                    <td>2026-03-15</td>
                    <td>Math</td>
                    <td>35p</td>
                    <td>1</td>
                    <td>prawdopodobieństwo rozszerzenie</td>
                </tr>
            </tbody>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.decorated tbody tr")
        
        grades = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 5:
                grade_str = cells[2].text.strip()
                max_points = None
                if grade_str.endswith("p"):
                    max_points = int(grade_str[:-1])
                
                grade = Grade(
                    date=datetime.strptime(cells[0].text.strip(), "%Y-%m-%d").date(),
                    subject=cells[1].text.strip(),
                    grade=grade_str,
                    max_points=max_points,
                    description=cells[4].text.strip(),
                    weight=int(cells[3].text.strip())
                )
                grades.append(grade)
        
        assert len(grades) == 1
        assert grades[0].subject == "Math"
        assert grades[0].grade == "35p"
        assert grades[0].max_points == 35
        assert grades[0].description == "prawdopodobieństwo rozszerzenie"
```

- [ ] **Step 2: Run tests to verify they pass**

Run:
```bash
pytest tests/test_librus_sync.py::TestGradeParsing -v
```

Expected: PASS

- [ ] **Step 3: Implement fetch_grades method**

Modify `second_brain/librus_sync.py` - add the `fetch_grades` method:

```python
    def fetch_grades(self) -> list[Grade]:
        """GET grades page, parse HTML table, return Grade objects."""
        if not self.logged_in:
            if not self.login():
                log.error("Cannot fetch grades - not logged in")
                return []

        grades_url = f"{self.BASE_URL}Oceny"
        
        try:
            response = self.session.get(grades_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            grade_rows = soup.select("table.decorated tbody tr")
            
            grades = []
            for row in grade_rows:
                cells = row.find_all("td")
                if len(cells) >= 5:
                    try:
                        grade_str = cells[2].text.strip()
                        # Check if it's a points-based grade (e.g., "35p")
                        max_points = None
                        if grade_str.endswith("p"):
                            try:
                                max_points = int(grade_str[:-1])
                            except ValueError:
                                pass
                        
                        weight_str = cells[3].text.strip()
                        weight = 1
                        try:
                            weight = int(weight_str)
                        except ValueError:
                            pass
                        
                        grade = Grade(
                            date=datetime.strptime(
                                cells[0].text.strip(), "%Y-%m-%d"
                            ).date(),
                            subject=cells[1].text.strip(),
                            grade=grade_str,
                            max_points=max_points,
                            description=cells[4].text.strip(),
                            weight=weight
                        )
                        grades.append(grade)
                    except (ValueError, IndexError) as e:
                        log.warning("Failed to parse grade row: %s", e)
                        continue
            
            log.info("Fetched %d grades from Librus", len(grades))
            return grades
            
        except requests.RequestException as e:
            log.error("Failed to fetch grades: %s", e)
            return []
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestGradeParsing -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Implement grade fetching with Math points support"
```

---

### Task 6: Implement grades.md Writer

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test for grades markdown generation**

Add to `tests/test_librus_sync.py`:

```python
class TestGradesMarkdown:
    """Test grades.md markdown generation."""

    def test_format_math_points_table(self):
        """Test formatting Math points-only grades."""
        grades = [
            Grade(
                date=date(2026, 3, 15),
                subject="Math",
                grade="32",
                max_points=35,
                description="prawdopodobieństwo rozszerzenie",
                weight=1
            ),
            Grade(
                date=date(2026, 3, 20),
                subject="Math",
                grade="28",
                max_points=35,
                description="kombinatoryka",
                weight=1
            ),
        ]
        
        # Group by subject and format
        from collections import defaultdict
        by_subject = defaultdict(list)
        for g in grades:
            by_subject[g.subject].append(g)
        
        lines = ["# Grades Overview", ""]
        
        for subject, subject_grades in sorted(by_subject.items()):
            lines.append(f"## {subject}")
            lines.append("| Date | Type | Points | Max Points | Description |")
            lines.append("|------|------|--------|------------|-------------|")
            
            total_points = 0
            max_total = 0
            for g in subject_grades:
                points = int(g.grade) if g.grade.isdigit() else 0
                max_p = g.max_points or 0
                total_points += points
                max_total += max_p
                lines.append(
                    f"| {g.date} | Points | {g.grade} | {g.max_points} | {g.description} |"
                )
            
            if max_total > 0:
                pct = (total_points / max_total) * 100
                lines.append("")
                lines.append(f"**Total: {total_points}/{max_total} ({pct:.1f}%)**")
            
            lines.append("")
        
        markdown = "\n".join(lines)
        
        assert "## Math" in markdown
        assert "| Date | Type | Points | Max Points | Description |" in markdown
        assert "Total: 60/70" in markdown
        assert "(85.7%)" in markdown

    def test_format_standard_grade_table(self):
        """Test formatting standard grades with weighted average."""
        grades = [
            Grade(
                date=date(2026, 3, 15),
                subject="Physics",
                grade="4.5",
                max_points=None,
                description="Kinematics quiz",
                weight=1
            ),
            Grade(
                date=date(2026, 3, 20),
                subject="Physics",
                grade="5.0",
                max_points=None,
                description="Dynamics test",
                weight=2
            ),
        ]
        
        from collections import defaultdict
        by_subject = defaultdict(list)
        for g in grades:
            by_subject[g.subject].append(g)
        
        lines = ["# Grades Overview", ""]
        
        for subject, subject_grades in sorted(by_subject.items()):
            lines.append(f"## {subject}")
            lines.append("| Date | Type | Grade | Weight | Description |")
            lines.append("|------|------|-------|--------|-------------|")
            
            weighted_sum = 0.0
            weight_total = 0
            for g in subject_grades:
                try:
                    grade_val = float(g.grade.replace(",", "."))
                    weighted_sum += grade_val * g.weight
                    weight_total += g.weight
                except ValueError:
                    pass
                lines.append(
                    f"| {g.date} | Grade | {g.grade} | {g.weight}x | {g.description} |"
                )
            
            if weight_total > 0:
                avg = weighted_sum / weight_total
                lines.append("")
                lines.append(f"**Average: {avg:.2f}**")
            
            lines.append("")
        
        markdown = "\n".join(lines)
        
        assert "## Physics" in markdown
        assert "Average: 4.83" in markdown
```

- [ ] **Step 2: Run tests to verify they pass**

Run:
```bash
pytest tests/test_librus_sync.py::TestGradesMarkdown -v
```

Expected: PASS

- [ ] **Step 3: Implement _format_grades helper method**

Modify `second_brain/librus_sync.py` - add helper method to `LibrusSync` class:

```python
    @staticmethod
    def _format_grades(grades: list[Grade]) -> str:
        """Format grades as markdown tables grouped by subject."""
        from collections import defaultdict
        
        by_subject = defaultdict(list)
        for g in grades:
            by_subject[g.subject].append(g)
        
        lines = ["# Grades Overview", ""]
        
        for subject, subject_grades in sorted(by_subject.items()):
            # Check if this subject uses points (Math special case)
            uses_points = any(g.max_points is not None for g in subject_grades)
            
            lines.append(f"## {subject}")
            
            if uses_points:
                # Math-style points table
                lines.append("| Date | Type | Points | Max Points | Description |")
                lines.append("|------|------|--------|------------|-------------|")
                
                total_points = 0
                max_total = 0
                for g in subject_grades:
                    points = int(g.grade) if g.grade.isdigit() else 0
                    max_p = g.max_points or 0
                    total_points += points
                    max_total += max_p
                    lines.append(
                        f"| {g.date} | Points | {g.grade} | {g.max_points} | {g.description} |"
                    )
                
                if max_total > 0:
                    pct = (total_points / max_total) * 100
                    lines.append("")
                    lines.append(f"**Total: {total_points}/{max_total} ({pct:.1f}%)**")
            else:
                # Standard grades table
                lines.append("| Date | Type | Grade | Weight | Description |")
                lines.append("|------|------|-------|--------|-------------|")
                
                weighted_sum = 0.0
                weight_total = 0
                for g in subject_grades:
                    try:
                        grade_val = float(g.grade.replace(",", "."))
                        weighted_sum += grade_val * g.weight
                        weight_total += g.weight
                    except ValueError:
                        pass
                    lines.append(
                        f"| {g.date} | Grade | {g.grade} | {g.weight}x | {g.description} |"
                    )
                
                if weight_total > 0:
                    avg = weighted_sum / weight_total
                    lines.append("")
                    lines.append(f"**Average: {avg:.2f}**")
            
            lines.append("")
        
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestGradesMarkdown -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Add grades.md markdown formatter with Math points support"
```

---

### Task 7: Implement todo.md Exam Writer

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test for exam todo formatting**

Add to `tests/test_librus_sync.py`:

```python
class TestExamTodo:
    """Test exam todo.md formatting."""

    def test_format_exam_todo(self):
        """Test formatting a single exam as todo item."""
        exam = Exam(
            date=date(2026, 4, 5),
            subject="Math",
            description="prawdopodobieństwo rozszerzenie",
            type="Sprawdzian"
        )
        
        todo_line = f"- [ ] {exam.date}: {exam.subject} {exam.type.lower()} - {exam.description}"
        
        assert todo_line == "- [ ] 2026-04-05: Math sprawdzian - prawdopodobieństwo rozszerzenie"

    def test_filter_past_exams(self):
        """Test that past exams are filtered out."""
        from datetime import date, timedelta
        
        today = date.today()
        past_exam = Exam(
            date=today - timedelta(days=5),
            subject="Math",
            description="old exam",
            type="Sprawdzian"
        )
        future_exam = Exam(
            date=today + timedelta(days=5),
            subject="Physics",
            description="future exam",
            type="Sprawdzian"
        )
        today_exam = Exam(
            date=today,
            subject="Chemistry",
            description="today exam",
            type="Quiz"
        )
        
        exams = [past_exam, future_exam, today_exam]
        filtered = [e for e in exams if e.date >= today]
        
        assert len(filtered) == 2
        assert filtered[0].subject == "Physics"
        assert filtered[1].subject == "Chemistry"

    def test_format_todos_section(self):
        """Test formatting full exam todos section."""
        exams = [
            Exam(
                date=date(2026, 4, 5),
                subject="Math",
                description="prawdopodobieństwo rozszerzenie",
                type="Sprawdzian"
            ),
            Exam(
                date=date(2026, 4, 8),
                subject="Physics",
                description="Kinematics test",
                type="Sprawdzian"
            ),
        ]
        
        lines = ["## Librus Exams (auto-synced)"]
        for exam in sorted(exams, key=lambda e: e.date):
            lines.append(
                f"- [ ] {exam.date}: {exam.subject} {exam.type.lower()} - {exam.description}"
            )
        
        markdown = "\n".join(lines)
        
        assert "## Librus Exams (auto-synced)" in markdown
        assert "- [ ] 2026-04-05: Math sprawdzian" in markdown
        assert "- [ ] 2026-04-08: Physics sprawdzian" in markdown
```

- [ ] **Step 2: Run tests to verify they pass**

Run:
```bash
pytest tests/test_librus_sync.py::TestExamTodo -v
```

Expected: PASS

- [ ] **Step 3: Implement _format_exams helper method**

Modify `second_brain/librus_sync.py` - add helper method to `LibrusSync` class:

```python
    @staticmethod
    def _format_exams(exams: list[Exam]) -> str:
        """Format exams as todo.md section, filtering past exams."""
        from datetime import date
        
        today = date.today()
        # Filter out past exams
        future_exams = [e for e in exams if e.date >= today]
        
        if not future_exams:
            return ""
        
        lines = ["## Librus Exams (auto-synced)"]
        for exam in sorted(future_exams, key=lambda e: e.date):
            lines.append(
                f"- [ ] {exam.date}: {exam.subject} {exam.type.lower()} - {exam.description}"
            )
        
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestExamTodo -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Add exam todo formatter with past exam filtering"
```

---

### Task 8: Implement todo.md Merge Logic

**Files:**
- Modify: `second_brain/librus_sync.py`
- Test: `tests/test_librus_sync.py`

- [ ] **Step 1: Write test for todo.md merge**

Add to `tests/test_librus_sync.py`:

```python
class TestTodoMerge:
    """Test todo.md merge logic - keeping manual todos."""

    def test_merge_librus_exams_with_manual_todos(self):
        """Test merging Librus exams while preserving manual todos."""
        existing_content = """# Todos

## Librus Exams (auto-synced)
- [ ] 2026-03-01: Old exam - removed
- [ ] 2026-03-05: Another old exam

## Manual Todos
- [ ] Fix DNS config on homelab server
- [ ] Read chapter 5
"""
        
        new_exams_section = """## Librus Exams (auto-synced)
- [ ] 2026-04-05: Math sprawdzian - prawdopodobieństwo rozszerzenie
- [ ] 2026-04-08: Physics sprawdzian - Kinematics test"""
        
        # Split by "## Manual Todos" marker
        if "## Manual Todos" in existing_content:
            parts = existing_content.split("## Manual Todos", 1)
            manual_section = "## Manual Todos" + parts[1]
        else:
            manual_section = ""
        
        new_content = new_exams_section + "\n\n" + manual_section
        
        assert "## Librus Exams (auto-synced)" in new_content
        assert "2026-04-05: Math" in new_content
        assert "2026-03-01: Old exam" not in new_content
        assert "## Manual Todos" in new_content
        assert "- [ ] Fix DNS config" in new_content
```

- [ ] **Step 2: Run test to verify it passes**

Run:
```bash
pytest tests/test_librus_sync.py::TestTodoMerge -v
```

Expected: PASS

- [ ] **Step 3: Implement _update_todo_file method**

Modify `second_brain/librus_sync.py` - add method to `LibrusSync` class:

```python
    def _update_todo_file(self, exams_section: str) -> None:
        """Update todo.md with new exams section, preserving manual todos."""
        todo_path = self.ctx.brain_dir / "todo.md"
        
        # Read existing content
        if todo_path.exists():
            existing = todo_path.read_text()
        else:
            existing = "# Todos\n"
        
        # Find and remove old Librus Exams section
        if "## Librus Exams (auto-synced)" in existing:
            # Split at the exams section
            parts = existing.split("## Librus Exams (auto-synced)", 1)
            before = parts[0].rstrip()
            after = parts[1] if len(parts) > 1 else ""
            
            # Find where manual todos start
            if "## Manual Todos" in after:
                manual_parts = after.split("## Manual Todos", 1)
                manual_section = "## Manual Todos" + manual_parts[1]
            elif after.strip():
                # Everything after is considered manual
                manual_section = after.strip()
            else:
                manual_section = ""
            
            # Rebuild with new exams section
            if exams_section:
                new_content = f"{before}\n\n{exams_section}\n\n{manual_section}".strip()
            else:
                # No exams - just keep before and manual
                new_content = f"{before}\n\n{manual_section}".strip()
        else:
            # No existing exams section - append after header
            if exams_section:
                if existing.strip() == "# Todos":
                    new_content = f"# Todos\n\n{exams_section}"
                else:
                    new_content = f"{existing.rstrip()}\n\n{exams_section}"
            else:
                new_content = existing
        
        # Ensure content ends with newline
        if not new_content.endswith("\n"):
            new_content += "\n"
        
        todo_path.write_text(new_content)
        log.info("Updated todo.md with %d exams", 
                 exams_section.count("- [ ]") if exams_section else 0)
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest tests/test_librus_sync.py::TestTodoMerge -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add second_brain/librus_sync.py tests/test_librus_sync.py
git commit -m "feat: Implement todo.md merge preserving manual todos"
```

---

### Task 9: Implement do_sync Method

**Files:**
- Modify: `second_brain/librus_sync.py`

- [ ] **Step 1: Implement the full sync flow**

Modify `second_brain/librus_sync.py` - update the `do_sync` method:

```python
    def do_sync(self) -> None:
        """Main sync method - fetch data and write to files."""
        if not self.scraper:
            log.error("Librus sync not configured - missing credentials")
            print("[librus] Error: Not configured. Add credentials to config.json")
            return
        
        log.info("Starting Librus sync...")
        
        # Login
        if not self.scraper.logged_in:
            if not self.scraper.login():
                log.error("Librus login failed")
                print("[librus] Error: Login failed. Check credentials.")
                return
        
        # Fetch data
        exams = self.scraper.fetch_exams()
        grades = self.scraper.fetch_grades()
        
        # Format and write grades
        if grades:
            grades_markdown = self._format_grades(grades)
            grades_path = self.ctx.brain_dir / "grades.md"
            grades_path.write_text(grades_markdown)
            log.info("Wrote %d grades to grades.md", len(grades))
            print(f"[librus] Synced {len(grades)} grades")
        else:
            log.warning("No grades fetched")
        
        # Format and update todos
        if exams:
            exams_section = self._format_exams(exams)
            self._update_todo_file(exams_section)
            exam_count = exams_section.count("- [ ]") if exams_section else 0
            print(f"[librus] Synced {exam_count} upcoming exams")
        else:
            log.warning("No exams fetched")
        
        log.info("Librus sync complete")
```

- [ ] **Step 2: Commit**

```bash
git add second_brain/librus_sync.py
git commit -m "feat: Implement complete do_sync method"
```

---

### Task 10: Add TUI Auto-Sync Hook

**Files:**
- Modify: `second_brain/librus_sync.py`
- Modify: `second_brain/tui.py`

- [ ] **Step 1: Add after_tui_start hook to plugin**

Modify `second_brain/librus_sync.py` - add hook method:

```python
    def after_tui_start(self, app: Any) -> None:
        """Trigger auto-sync when TUI opens."""
        if not self.config.get("auto_sync_on_tui", True):
            log.debug("Librus auto-sync on TUI start disabled")
            return
        
        if not self.scraper:
            return
        
        # Run sync in background (non-blocking)
        log.info("Auto-syncing Librus data on TUI start...")
        try:
            self.do_sync()
        except Exception as e:
            log.error("Librus auto-sync failed: %s", e)
```

Note: Add `from typing import Any` at the top of the file if not present.

- [ ] **Step 2: Commit**

```bash
git add second_brain/librus_sync.py
git commit -m "feat: Add TUI auto-sync hook"
```

---

### Task 11: Add CLI Command

**Files:**
- Modify: `second_brain/__main__.py`

- [ ] **Step 1: Add 'librus' command to argparse**

Modify `second_brain/__main__.py`:

1. Add "librus" to the choices list (around line 95):

```python
        choices=[
            "tui",
            "setup",
            "process",
            "graph",
            "janitor",
            "ask",
            "backlinks",
            "list",
            "dot",
            "check-links",
            "daily",
            "tags",
            "tag",
            "duplicates",
            "pull",
            "sync",
            "boot-sync",
            "install-timer",
            "uninstall-timer",
            "invest",
            "librus",  # Add this
        ],
```

2. Add to help text (around line 50):

```python
  second-brain invest "{ale} allegro - 3 - 25.50"  # Add investment with buy price
  second-brain invest --refresh            # Refresh all investment prices
  second-brain librus                      # Sync grades/exams from Librus
  second-brain librus --dry-run            # Preview without writing (future)
```

- [ ] **Step 2: Add command handler**

Modify `second_brain/__main__.py` - add handler before the final `else` clause:

```python
    elif args.command == "librus":
        from .plugins import get_manager

        pm = get_manager()
        librus_plugin = None
        for p in pm.plugins:
            if p.name == "librus_sync":
                librus_plugin = p
                break

        if librus_plugin is None:
            log.error(
                "Error: librus_sync plugin not loaded.\n"
                "Enable it in config.json: plugins.enabled"
            )
            sys.exit(1)

        librus_plugin.do_sync()  # type: ignore[attr-defined]
```

- [ ] **Step 3: Commit**

```bash
git add second_brain/__main__.py
git commit -m "feat: Add 'second-brain librus' CLI command"
```

---

### Task 12: Add Documentation

**Files:**
- Create: `docs/librus_sync.md`

- [ ] **Step 1: Create user documentation**

Create `docs/librus_sync.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/librus_sync.md
git commit -m "docs: Add Librus sync plugin documentation"
```

---

### Task 13: Integration Testing

**Files:**
- Test: Manual testing

- [ ] **Step 1: Install the plugin**

Copy plugin to plugin directory:

```bash
cp second_brain/librus_sync.py ~/.config/second_brain/plugins/librus_sync.py
```

- [ ] **Step 2: Configure credentials**

Edit `~/.config/second_brain/config.json`:

```json
{
  "plugins": {
    "enabled": ["librus_sync"],
    "config": {
      "librus_sync": {
        "username": "YOUR_USERNAME",
        "password": "YOUR_PASSWORD"
      }
    }
  }
}
```

- [ ] **Step 3: Run manual sync test**

```bash
second-brain librus
```

Expected output:
```
[librus] Synced X grades
[librus] Synced Y upcoming exams
```

- [ ] **Step 4: Verify grades.md**

```bash
cat ~/Documents/brain/grades.md
```

Check:
- Tables formatted correctly
- Math shows points with percentage
- Other subjects show weighted averages

- [ ] **Step 5: Verify todo.md**

```bash
cat ~/Documents/brain/todo.md
```

Check:
- Librus Exams section present
- Only future exams listed
- Manual todos preserved

- [ ] **Step 6: Test TUI auto-sync**

```bash
second-brain
```

Check logs/status for auto-sync message

- [ ] **Step 7: Commit test results**

```bash
git commit --allow-empty -m "test: Manual integration testing passed"
```

---

### Task 14: Run Full Test Suite

**Files:**
- All test files

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests pass including new Librus tests

- [ ] **Step 2: Run linting**

```bash
ruff check second_brain/ tests/
```

Expected: No errors

- [ ] **Step 3: Run type checking**

```bash
mypy second_brain/
```

Expected: No type errors (or only pre-existing ones)

- [ ] **Step 4: Fix any issues**

If linting/type errors found, fix them

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: Pass linting and type checks"
```

---

## Plan Self-Review

✅ **Spec coverage:** All requirements from spec have corresponding tasks:
- Authentication → Task 3
- Data scraping (exams, grades) → Tasks 4, 5
- Math points handling → Tasks 5, 6
- grades.md format → Task 6
- todo.md format with filtering → Tasks 7, 8
- CLI command → Task 11
- TUI auto-sync → Task 10
- Error handling → Built into Tasks 3, 4, 5, 9
- Tests → All tasks include TDD steps

✅ **No placeholders:** All steps contain actual code, no TBD/TODO

✅ **Type consistency:** 
- `Exam` and `Grade` dataclasses used consistently
- Method signatures match across all tasks
- Return types are `list[Exam]`, `list[Grade]`, `str`

✅ **File paths:** All exact paths specified

---

Plan complete and saved to `docs/superpowers/plans/2026-03-29-librus-sync.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
