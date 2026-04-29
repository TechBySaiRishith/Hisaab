# Badminton Splitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Badminton Splitter web app — a Pi-hosted FastAPI + HTMX app that computes per-player session costs (slot-based court split, pro-rata shuttle) and generates `wa.me` payment-request links.

**Architecture:** Clean layered Python app (domain / persistence / services / api / web). Pure-function cost calculator at the core. SQLite + Alembic + Litestream for storage. Server-rendered HTMX UI with Tailwind v4. Single-container Docker deploy on ARM64 with a Litestream sidecar.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic, SQLite (aiosqlite), Jinja2, HTMX, Tailwind v4, Lucide icons, structlog, pytest + Hypothesis, Playwright, ruff, mypy strict, pre-commit, Docker buildx (linux/arm64), GitHub Actions.

**Source spec:** `docs/superpowers/specs/2026-04-29-badminton-splitter-design.md` — read it once before starting.

---

## File structure (created by this plan)

```
badminton-splitter/
├── pyproject.toml                       # Python project, deps, ruff, mypy, pytest config
├── alembic.ini                          # Alembic config
├── .pre-commit-config.yaml              # ruff, mypy, end-of-file-fixer, etc.
├── .gitignore                           # Python, IDE, /data, /backup
├── .python-version                      # 3.12
├── .dockerignore
├── Makefile                             # build, test, lint, pi-deploy, etc.
├── README.md                            # quickstart
├── .github/workflows/ci.yml             # lint → type → test → e2e → docker build
├── docker/
│   ├── Dockerfile                       # multi-stage (tailwind build + runtime)
│   ├── docker-compose.yml               # app + litestream
│   └── litestream.yml                   # litestream config
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                        # migrations land here
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app factory + uvicorn entrypoint
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                  # Pydantic Settings (DATABASE_URL, LOG_LEVEL, TZ, UPI_ID, …)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py                    # frozen dataclasses: PlayerRef, SlotInput, CourtInput, SessionInput, PlayerResult, SessionResult
│   │   ├── rounding.py                  # round_to_5
│   │   └── calculator.py                # calculate_session pure function
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── database.py                  # async engine + session factory
│   │   ├── orm.py                       # SQLAlchemy ORM models
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── player.py
│   │       ├── venue.py
│   │       └── session.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── player_service.py
│   │   ├── venue_service.py
│   │   ├── session_service.py           # orchestrates create-draft / finalize / load-aggregate
│   │   └── messaging.py                 # build_message_text + build_wa_me_url
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                      # FastAPI dependencies (DB session, settings)
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── player.py
│   │   │   ├── venue.py
│   │   │   └── session.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── home.py                  # GET / → sessions list
│   │       ├── players.py
│   │       ├── venues.py
│   │       ├── sessions.py              # wizard + result page + finalize
│   │       └── settings.py
│   └── web/
│       ├── templates/
│       │   ├── base.html
│       │   ├── _macros.html
│       │   ├── home.html
│       │   ├── sessions/
│       │   │   ├── list.html
│       │   │   ├── new_setup.html
│       │   │   ├── new_players.html
│       │   │   ├── new_courts.html
│       │   │   ├── new_slots.html
│       │   │   ├── new_shuttles.html
│       │   │   ├── review.html
│       │   │   └── result.html
│       │   ├── players/
│       │   │   ├── list.html
│       │   │   └── form.html
│       │   ├── venues/
│       │   │   ├── list.html
│       │   │   └── form.html
│       │   ├── settings/
│       │   │   └── form.html
│       │   └── partials/                # HTMX response fragments
│       │       ├── slot_cell.html
│       │       ├── player_chip.html
│       │       └── flash.html
│       └── static/
│           ├── css/
│           │   ├── tailwind.input.css
│           │   └── tailwind.output.css  # built by Tailwind CLI; gitignored
│           ├── js/
│           │   └── htmx.min.js          # vendored
│           └── fonts/                   # Inter + JetBrains Mono (self-hosted)
└── tests/
    ├── __init__.py
    ├── conftest.py                      # shared fixtures (db, client, factories)
    ├── factories.py                     # factory-boy factories
    ├── domain/
    │   ├── __init__.py
    │   ├── test_rounding.py
    │   ├── test_calculator.py
    │   └── test_calculator_properties.py
    ├── persistence/
    │   ├── __init__.py
    │   ├── test_migrations.py
    │   └── repositories/
    │       ├── test_player.py
    │       ├── test_venue.py
    │       └── test_session.py
    ├── services/
    │   ├── __init__.py
    │   ├── test_session_service.py
    │   └── test_messaging.py
    ├── api/
    │   ├── __init__.py
    │   ├── test_players.py
    │   ├── test_venues.py
    │   └── test_sessions.py
    └── e2e/
        ├── __init__.py
        └── test_happy_path.py            # Playwright
```

Each file has one responsibility. Domain is pure (no I/O, no framework imports). Persistence is the only place that touches the DB. Services orchestrate. API and web layers are thin.

---

## Phases (each phase is a logical checkpoint)

1. **Phase A — Project foundation.** Repo, tooling, CI skeleton. Ends with `make test` passing on an empty test suite.
2. **Phase B — Domain layer.** Cost calculator with full unit + property tests. Pure Python, no framework.
3. **Phase C — Persistence layer.** ORM, migrations, repositories.
4. **Phase D — Services layer.** Session orchestration, messaging.
5. **Phase E — API layer.** FastAPI routers + Pydantic schemas. JSON-responding endpoints first.
6. **Phase F — Web UI.** Templates, Tailwind, HTMX, design system.
7. **Phase G — Deployment + E2E.** Dockerfile, compose, Litestream, Playwright happy path, Pi deploy.

Commit at the end of every task. Tests must be green before commit. Run `make ci` (full local run of CI checks) before any commit that modifies code.

---

# Phase A — Project foundation

## Task A1: Initialize git repo, create .gitignore, README scaffold

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `.dockerignore`
- Create: `README.md`

- [ ] **Step 1: Init repo (if not already)**

```bash
cd "D:/Projects/Badminton Splitter"
git init -b main
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
.Python
.venv/
venv/
env/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
.coverage.*
htmlcov/
dist/
build/

# IDEs
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# App data (mounted in Docker)
/data/
/backup/

# Built CSS
app/web/static/css/tailwind.output.css

# Env
.env
.env.local
```

- [ ] **Step 3: Write `.python-version`**

```
3.12
```

- [ ] **Step 4: Write `.dockerignore`**

```dockerignore
.git
.venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
.coverage*
tests/
docs/
*.md
!README.md
.github
```

- [ ] **Step 5: Write `README.md`**

```markdown
# Badminton Splitter

Computes per-player badminton session costs (court + shuttle, slot-based) and generates `wa.me` payment-request links. Self-hosted on Raspberry Pi.

## Quickstart (development)

```bash
make install      # create venv, install deps, install pre-commit
make tailwind     # build CSS once
make dev          # run app at http://localhost:8080
```

## Deployment

See `docker/docker-compose.yml`. Use `make pi-deploy` from a workstation with SSH access to the Pi.

## Architecture

See `docs/superpowers/specs/2026-04-29-badminton-splitter-design.md`.
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore .python-version .dockerignore README.md docs/
git commit -m "chore: initialize repo with spec, plan, and config scaffolding"
```

---

## Task A2: Set up `pyproject.toml` with all dependencies and tool configs

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "badminton-splitter"
version = "0.1.0"
description = "Compute per-player badminton session costs and dispatch WhatsApp payment requests."
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "sqlalchemy[asyncio]>=2.0.30",
    "aiosqlite>=0.20",
    "alembic>=1.13",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "phonenumbers>=8.13",
    "structlog>=24.1",
    "prometheus-client>=0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "hypothesis>=6.100",
    "httpx>=0.27",
    "factory-boy>=3.3",
    "ruff>=0.5",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "playwright>=1.44",
]

[build-system]
requires = ["setuptools>=70"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "TCH", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = false
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_decorators = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-q --strict-markers --strict-config"
testpaths = ["tests"]
markers = [
    "e2e: end-to-end tests (slow, require running app)",
]

[tool.coverage.run]
branch = true
source = ["app"]
omit = ["app/main.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

- [ ] **Step 2: Create venv and install**

```bash
python -m venv .venv
.venv/Scripts/activate    # Windows
pip install -e ".[dev]"
```

- [ ] **Step 3: Verify install**

```bash
ruff --version && mypy --version && pytest --version
```

Expected: each prints a version. No errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: configure project deps and tooling (ruff, mypy strict, pytest)"
```

---

## Task A3: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: ["--maxkb=500"]
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.7
          - sqlalchemy>=2.0.30
        files: ^app/(domain|services)/
        args: [--strict]
```

- [ ] **Step 2: Install hooks**

```bash
pre-commit install
pre-commit run --all-files
```

Expected: hooks may auto-fix some files; commit those changes if any. Then re-run; expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks (ruff, mypy strict on domain+services)"
```

---

## Task A4: Makefile with developer targets

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Write `Makefile`**

```makefile
.PHONY: install dev tailwind test lint type ci clean docker-build pi-deploy

install:
	python -m venv .venv
	.venv/Scripts/pip install -e ".[dev]"
	.venv/Scripts/pre-commit install

dev:
	.venv/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

tailwind:
	tailwindcss -i app/web/static/css/tailwind.input.css -o app/web/static/css/tailwind.output.css --minify

tailwind-watch:
	tailwindcss -i app/web/static/css/tailwind.input.css -o app/web/static/css/tailwind.output.css --watch

test:
	.venv/Scripts/pytest --cov=app --cov-report=term-missing -m "not e2e"

test-e2e:
	.venv/Scripts/pytest -m e2e

lint:
	.venv/Scripts/ruff check .
	.venv/Scripts/ruff format --check .

type:
	.venv/Scripts/mypy app/domain app/services

ci: lint type test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
	find . -name __pycache__ -type d -exec rm -rf {} +

docker-build:
	docker buildx build --platform linux/arm64 -t badminton-splitter:latest -f docker/Dockerfile .

pi-deploy:
	@echo "Replace with: ssh pi 'cd /opt/badminton && docker compose pull && docker compose up -d'"
```

- [ ] **Step 2: Verify**

```bash
make lint
```

Expected: no errors (codebase is empty modulo the spec/plan files).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile with developer targets"
```

---

## Task A5: GitHub Actions CI skeleton

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-type-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -e ".[dev]"
      - name: Lint
        run: |
          ruff check .
          ruff format --check .
      - name: Type-check
        run: mypy app/domain app/services
      - name: Unit + service + api tests
        run: pytest --cov=app --cov-report=xml -m "not e2e"
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
        continue-on-error: true

  docker-build:
    runs-on: ubuntu-latest
    needs: lint-type-test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (arm64)
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile
          platforms: linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions workflow (lint, type, test, docker build)"
```

---

# Phase B — Domain layer (cost calculator)

This is the heart of the app. TDD throughout. Pure Python — no framework imports.

## Task B1: Frozen dataclasses for domain types

**Files:**
- Create: `app/__init__.py` (empty)
- Create: `app/domain/__init__.py` (empty)
- Create: `app/domain/models.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/domain/__init__.py` (empty)
- Create: `tests/domain/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/domain/test_models.py`:

```python
from decimal import Decimal

from app.domain.models import (
    CourtInput,
    PlayerRef,
    SessionInput,
    ShuttleContributionInput,
    SlotInput,
)


def test_session_input_constructs() -> None:
    alice = PlayerRef(player_id=1, name="Alice")
    bob = PlayerRef(player_id=2, name="Bob")
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("50"),
        courts=[
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=60,
                slots=[
                    SlotInput(slot_index=0, player_ids={1, 2}),
                    SlotInput(slot_index=1, player_ids={1, 2}),
                ],
            ),
        ],
        shuttle_contributions=[
            ShuttleContributionInput(owner_player_id=1, total_minutes=60),
        ],
        participants={alice, bob},
    )
    assert session.court_rate_per_hour == Decimal("400")
    assert len(session.courts) == 1
    assert session.courts[0].slots[0].player_ids == {1, 2}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/domain/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.models'`.

- [ ] **Step 3: Write the dataclasses**

`app/domain/models.py`:

```python
"""Pure domain types for the cost calculator. No I/O, no framework imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PlayerRef:
    player_id: int
    name: str

    def __hash__(self) -> int:
        return hash(self.player_id)


@dataclass(frozen=True, slots=True)
class SlotInput:
    slot_index: int
    player_ids: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Allow callers to pass a regular set; freeze it.
        if not isinstance(self.player_ids, frozenset):
            object.__setattr__(self, "player_ids", frozenset(self.player_ids))


@dataclass(frozen=True, slots=True)
class CourtInput:
    court_id: int
    booker_player_id: int
    duration_minutes: int
    slots: tuple[SlotInput, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0 or self.duration_minutes % 30 != 0:
            raise ValueError(
                f"court duration_minutes must be positive multiple of 30, got {self.duration_minutes}"
            )
        if not isinstance(self.slots, tuple):
            object.__setattr__(self, "slots", tuple(self.slots))
        expected = self.duration_minutes // 30
        if len(self.slots) != expected:
            raise ValueError(
                f"court {self.court_id} has {len(self.slots)} slots but duration implies {expected}"
            )


@dataclass(frozen=True, slots=True)
class ShuttleContributionInput:
    owner_player_id: int
    total_minutes: int

    def __post_init__(self) -> None:
        if self.total_minutes < 0 or self.total_minutes % 30 != 0:
            raise ValueError(
                f"shuttle total_minutes must be non-negative multiple of 30, got {self.total_minutes}"
            )


@dataclass(frozen=True, slots=True)
class SessionInput:
    court_rate_per_hour: Decimal
    shuttle_rate_per_hour: Decimal
    courts: tuple[CourtInput, ...]
    shuttle_contributions: tuple[ShuttleContributionInput, ...]
    participants: frozenset[PlayerRef]

    def __post_init__(self) -> None:
        if self.court_rate_per_hour < 0:
            raise ValueError("court_rate_per_hour must be >= 0")
        if self.shuttle_rate_per_hour < 0:
            raise ValueError("shuttle_rate_per_hour must be >= 0")
        if not isinstance(self.courts, tuple):
            object.__setattr__(self, "courts", tuple(self.courts))
        if not isinstance(self.shuttle_contributions, tuple):
            object.__setattr__(self, "shuttle_contributions", tuple(self.shuttle_contributions))
        if not isinstance(self.participants, frozenset):
            object.__setattr__(self, "participants", frozenset(self.participants))


@dataclass(frozen=True, slots=True)
class PlayerResult:
    player_id: int
    name: str
    play_minutes: int
    owes_court: int       # rounded ₹
    owes_shuttle: int
    credit_court: int
    credit_shuttle: int
    owes_total: int
    credit_total: int
    net: int              # positive = player owes; negative = player is owed


@dataclass(frozen=True, slots=True)
class SessionResult:
    per_player: tuple[PlayerResult, ...]
    court_rate_per_hour: Decimal
    shuttle_rate_per_hour: Decimal
    total_court_cost: Decimal
    total_shuttle_cost: Decimal
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/domain/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/__init__.py app/domain/ tests/__init__.py tests/domain/
git commit -m "feat(domain): add frozen dataclasses for session inputs and results"
```

---

## Task B2: `round_to_5` helper with exhaustive tests

**Files:**
- Create: `app/domain/rounding.py`
- Create: `tests/domain/test_rounding.py`

- [ ] **Step 1: Write the failing test**

`tests/domain/test_rounding.py`:

```python
from decimal import Decimal

import pytest

from app.domain.rounding import round_to_5


@pytest.mark.parametrize(
    "amount,expected",
    [
        (Decimal("0"), 0),
        (Decimal("2.49"), 0),
        (Decimal("2.5"), 5),
        (Decimal("87"), 85),
        (Decimal("87.4"), 85),
        (Decimal("87.5"), 90),
        (Decimal("88.6"), 90),
        (Decimal("90"), 90),
        (Decimal("92.4"), 90),
        (Decimal("92.5"), 95),
        (Decimal("100"), 100),
        (Decimal("-2.5"), -5),
        (Decimal("-87.6"), -90),
    ],
)
def test_round_to_5(amount: Decimal, expected: int) -> None:
    assert round_to_5(amount) == expected


def test_round_to_5_rejects_floats() -> None:
    with pytest.raises(TypeError):
        round_to_5(2.5)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/domain/test_rounding.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write the implementation**

`app/domain/rounding.py`:

```python
"""Rounding helpers."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_to_5(amount: Decimal) -> int:
    """Round HALF UP to nearest 5. 88.6→90, 87→85, 87.5→90, 92.4→90."""
    if not isinstance(amount, Decimal):
        raise TypeError(f"round_to_5 requires Decimal, got {type(amount).__name__}")
    return int((amount / 5).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 5)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/domain/test_rounding.py -v
```

Expected: PASS (13 cases).

- [ ] **Step 5: Commit**

```bash
git add app/domain/rounding.py tests/domain/test_rounding.py
git commit -m "feat(domain): add round_to_5 helper with HALF_UP rounding"
```

---

## Task B3: Calculator — court costs only (TDD)

We build the calculator incrementally. This task: a calculator that handles court splits only and returns zero shuttle figures. Subsequent tasks add shuttle and assembly.

**Files:**
- Create: `app/domain/calculator.py`
- Create: `tests/domain/test_calculator.py`

- [ ] **Step 1: Write the failing test for a single-court single-slot session**

`tests/domain/test_calculator.py`:

```python
from decimal import Decimal

from app.domain.calculator import calculate_session
from app.domain.models import (
    CourtInput,
    PlayerRef,
    SessionInput,
    SlotInput,
)


def alice() -> PlayerRef:
    return PlayerRef(player_id=1, name="Alice")


def bob() -> PlayerRef:
    return PlayerRef(player_id=2, name="Bob")


def test_single_court_single_slot_two_players_split_equally() -> None:
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("0"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=30,
                slots=(SlotInput(slot_index=0, player_ids=frozenset({1, 2})),),
            ),
        ),
        shuttle_contributions=(),
        participants=frozenset({alice(), bob()}),
    )
    result = calculate_session(session)

    by_id = {p.player_id: p for p in result.per_player}
    # Court is 30 min @ ₹400/hr = ₹200. Split among 2 = ₹100 each.
    assert by_id[1].owes_court == 100
    assert by_id[2].owes_court == 100
    # Booker (Alice, id=1) is credited the full ₹200.
    assert by_id[1].credit_court == 200
    assert by_id[2].credit_court == 0
    # No shuttles in this session.
    assert by_id[1].owes_shuttle == 0
    assert by_id[2].owes_shuttle == 0
    assert result.total_shuttle_cost == Decimal("0")
    assert result.total_court_cost == Decimal("200")
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/domain/test_calculator.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write minimal calculator (court-only first)**

`app/domain/calculator.py`:

```python
"""Pure cost calculator for badminton sessions.

Reads a SessionInput and returns a SessionResult. No I/O, no framework.
See docs/superpowers/specs/2026-04-29-badminton-splitter-design.md §4.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.domain.models import PlayerResult, SessionInput, SessionResult
from app.domain.rounding import round_to_5


def calculate_session(session: SessionInput) -> SessionResult:
    court_owe: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    court_credit: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    total_court_cost = Decimal("0")

    # ── Court costs ────────────────────────────────────────────────────────────
    for court in session.courts:
        court_total = (Decimal(court.duration_minutes) / Decimal(60)) * session.court_rate_per_hour
        total_court_cost += court_total
        court_credit[court.booker_player_id] += court_total

        per_slot = court_total / Decimal(len(court.slots))
        for slot in court.slots:
            n = len(slot.player_ids)
            if n == 0:
                court_owe[court.booker_player_id] += per_slot
                continue
            share = per_slot / Decimal(n)
            for pid in slot.player_ids:
                court_owe[pid] += share

    # ── Assemble results (shuttle = 0 for now; B4 fills it in) ─────────────────
    per_player: list[PlayerResult] = []
    for ref in session.participants:
        owes_c = court_owe.get(ref.player_id, Decimal("0"))
        cred_c = court_credit.get(ref.player_id, Decimal("0"))
        per_player.append(
            PlayerResult(
                player_id=ref.player_id,
                name=ref.name,
                play_minutes=0,  # B5 fills
                owes_court=round_to_5(owes_c),
                owes_shuttle=0,
                credit_court=round_to_5(cred_c),
                credit_shuttle=0,
                owes_total=round_to_5(owes_c),
                credit_total=round_to_5(cred_c),
                net=round_to_5(owes_c - cred_c),
            )
        )

    return SessionResult(
        per_player=tuple(per_player),
        court_rate_per_hour=session.court_rate_per_hour,
        shuttle_rate_per_hour=session.shuttle_rate_per_hour,
        total_court_cost=total_court_cost,
        total_shuttle_cost=Decimal("0"),
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/domain/test_calculator.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/domain/calculator.py tests/domain/test_calculator.py
git commit -m "feat(domain): add calculator (court costs, slot-based split)"
```

---

## Task B4: Calculator — handle empty slots, multiple courts, swap-in/swap-out

**Files:**
- Modify: `tests/domain/test_calculator.py` (add tests)
- Modify: `app/domain/calculator.py` (no changes expected — verify existing logic handles)

- [ ] **Step 1: Add tests for swap and empty slot**

Append to `tests/domain/test_calculator.py`:

```python
def test_player_swap_mid_session() -> None:
    """1.5hr session, 1 court. Slots 1-2: A,B,C,D. Slot 3: A,B,C,E (D leaves, E joins)."""
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("0"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=90,
                slots=(
                    SlotInput(slot_index=0, player_ids=frozenset({1, 2, 3, 4})),
                    SlotInput(slot_index=1, player_ids=frozenset({1, 2, 3, 4})),
                    SlotInput(slot_index=2, player_ids=frozenset({1, 2, 3, 5})),
                ),
            ),
        ),
        shuttle_contributions=(),
        participants=frozenset({
            PlayerRef(1, "A"),
            PlayerRef(2, "B"),
            PlayerRef(3, "C"),
            PlayerRef(4, "D"),
            PlayerRef(5, "E"),
        }),
    )
    result = calculate_session(session)
    by_id = {p.player_id: p for p in result.per_player}

    # Each slot: 30min/60 * 400 = 200. Each slot split among 4 = 50.
    # A,B,C: 3 slots × 50 = 150 each
    # D: 2 slots × 50 = 100
    # E: 1 slot × 50 = 50
    assert by_id[1].owes_court == 150
    assert by_id[2].owes_court == 150
    assert by_id[3].owes_court == 150
    assert by_id[4].owes_court == 100
    assert by_id[5].owes_court == 50
    # Booker A: credited full 600
    assert by_id[1].credit_court == 600


def test_empty_slot_charges_booker() -> None:
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("0"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=60,
                slots=(
                    SlotInput(slot_index=0, player_ids=frozenset({1, 2})),
                    SlotInput(slot_index=1, player_ids=frozenset()),  # empty
                ),
            ),
        ),
        shuttle_contributions=(),
        participants=frozenset({PlayerRef(1, "A"), PlayerRef(2, "B")}),
    )
    result = calculate_session(session)
    by_id = {p.player_id: p for p in result.per_player}
    # Slot 1 (₹200) split between A,B = 100 each.
    # Slot 2 (₹200) charged to booker A.
    # A: 100 + 200 = 300; B: 100.
    assert by_id[1].owes_court == 300
    assert by_id[2].owes_court == 100


def test_multiple_courts() -> None:
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("0"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=30,
                slots=(SlotInput(slot_index=0, player_ids=frozenset({1, 2})),),
            ),
            CourtInput(
                court_id=11,
                booker_player_id=3,
                duration_minutes=30,
                slots=(SlotInput(slot_index=0, player_ids=frozenset({3, 4})),),
            ),
        ),
        shuttle_contributions=(),
        participants=frozenset({
            PlayerRef(1, "A"), PlayerRef(2, "B"),
            PlayerRef(3, "C"), PlayerRef(4, "D"),
        }),
    )
    result = calculate_session(session)
    by_id = {p.player_id: p for p in result.per_player}
    assert by_id[1].owes_court == 100
    assert by_id[2].owes_court == 100
    assert by_id[3].owes_court == 100
    assert by_id[4].owes_court == 100
    assert by_id[1].credit_court == 200
    assert by_id[3].credit_court == 200
    assert result.total_court_cost == Decimal("400")
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/domain/test_calculator.py -v
```

Expected: PASS (all tests). The existing calculator handles these cases.

- [ ] **Step 3: Commit**

```bash
git add tests/domain/test_calculator.py
git commit -m "test(domain): cover swap-in/swap-out, empty slots, multiple courts"
```

---

## Task B5: Calculator — shuttle costs (TDD)

**Files:**
- Modify: `tests/domain/test_calculator.py` (add shuttle tests)
- Modify: `app/domain/calculator.py` (add shuttle logic)

- [ ] **Step 1: Add failing test for shuttle distribution**

Append to `tests/domain/test_calculator.py`:

```python
def test_shuttle_split_pro_rata_by_play_minutes() -> None:
    session = SessionInput(
        court_rate_per_hour=Decimal("0"),  # zero out court for clarity
        shuttle_rate_per_hour=Decimal("50"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=90,
                slots=(
                    SlotInput(slot_index=0, player_ids=frozenset({1, 2, 3})),
                    SlotInput(slot_index=1, player_ids=frozenset({1, 2, 3})),
                    SlotInput(slot_index=2, player_ids=frozenset({1, 2})),  # 3 leaves
                ),
            ),
        ),
        shuttle_contributions=(
            ShuttleContributionInput(owner_player_id=1, total_minutes=90),
        ),
        participants=frozenset({
            PlayerRef(1, "A"), PlayerRef(2, "B"), PlayerRef(3, "C"),
        }),
    )
    result = calculate_session(session)
    by_id = {p.player_id: p for p in result.per_player}

    # Total shuttle cost = 1.5h × ₹50 = ₹75
    # Play minutes: A=90, B=90, C=60 → total 240
    # A share = 75 × 90/240 = 28.125 → 30
    # B share = 75 × 90/240 = 28.125 → 30
    # C share = 75 × 60/240 = 18.75  → 20
    assert by_id[1].owes_shuttle == 30
    assert by_id[2].owes_shuttle == 30
    assert by_id[3].owes_shuttle == 20
    assert by_id[1].credit_shuttle == 75
    assert by_id[2].credit_shuttle == 0
    assert result.total_shuttle_cost == Decimal("75")


def test_shuttle_owner_did_not_play() -> None:
    """Owner contributed shuttles but didn't play themselves — credited but doesn't owe shuttle."""
    session = SessionInput(
        court_rate_per_hour=Decimal("0"),
        shuttle_rate_per_hour=Decimal("50"),
        courts=(
            CourtInput(
                court_id=10,
                booker_player_id=1,
                duration_minutes=30,
                slots=(SlotInput(slot_index=0, player_ids=frozenset({2, 3})),),
            ),
        ),
        shuttle_contributions=(
            ShuttleContributionInput(owner_player_id=1, total_minutes=30),
        ),
        participants=frozenset({
            PlayerRef(1, "A"), PlayerRef(2, "B"), PlayerRef(3, "C"),
        }),
    )
    result = calculate_session(session)
    by_id = {p.player_id: p for p in result.per_player}
    # A didn't play → 0 minutes → owes 0 shuttle
    assert by_id[1].play_minutes == 0
    assert by_id[1].owes_shuttle == 0
    # A is credited the shuttle cost (0.5h × 50 = 25)
    assert by_id[1].credit_shuttle == 25


def test_zero_shuttle_rate_yields_zero() -> None:
    session = SessionInput(
        court_rate_per_hour=Decimal("400"),
        shuttle_rate_per_hour=Decimal("0"),
        courts=(
            CourtInput(
                court_id=10, booker_player_id=1, duration_minutes=30,
                slots=(SlotInput(slot_index=0, player_ids=frozenset({1, 2})),),
            ),
        ),
        shuttle_contributions=(
            ShuttleContributionInput(owner_player_id=1, total_minutes=30),
        ),
        participants=frozenset({PlayerRef(1, "A"), PlayerRef(2, "B")}),
    )
    result = calculate_session(session)
    assert result.total_shuttle_cost == Decimal("0")
    for p in result.per_player:
        assert p.owes_shuttle == 0
        assert p.credit_shuttle == 0
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/domain/test_calculator.py -v
```

Expected: shuttle tests FAIL (calculator doesn't compute shuttle yet).

- [ ] **Step 3: Replace calculator with the full implementation**

Overwrite `app/domain/calculator.py`:

```python
"""Pure cost calculator for badminton sessions.

Reads a SessionInput and returns a SessionResult. No I/O, no framework.
See docs/superpowers/specs/2026-04-29-badminton-splitter-design.md §4.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.domain.models import PlayerResult, SessionInput, SessionResult
from app.domain.rounding import round_to_5


def calculate_session(session: SessionInput) -> SessionResult:
    court_owe: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    court_credit: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    shuttle_owe: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    shuttle_credit: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    play_minutes: dict[int, int] = defaultdict(int)

    total_court_cost = Decimal("0")

    # ── Court costs (slot-based, equal split per slot) ─────────────────────────
    for court in session.courts:
        court_total = (Decimal(court.duration_minutes) / Decimal(60)) * session.court_rate_per_hour
        total_court_cost += court_total
        court_credit[court.booker_player_id] += court_total

        per_slot = court_total / Decimal(len(court.slots))
        for slot in court.slots:
            for pid in slot.player_ids:
                play_minutes[pid] += 30
            n = len(slot.player_ids)
            if n == 0:
                court_owe[court.booker_player_id] += per_slot
                continue
            share = per_slot / Decimal(n)
            for pid in slot.player_ids:
                court_owe[pid] += share

    # ── Shuttle costs (pro-rata by play minutes) ──────────────────────────────
    total_shuttle_cost = Decimal("0")
    for c in session.shuttle_contributions:
        cost = (Decimal(c.total_minutes) / Decimal(60)) * session.shuttle_rate_per_hour
        shuttle_credit[c.owner_player_id] += cost
        total_shuttle_cost += cost

    total_play = sum(play_minutes.values())
    if total_play > 0 and total_shuttle_cost > 0:
        for pid, mins in play_minutes.items():
            shuttle_owe[pid] += total_shuttle_cost * Decimal(mins) / Decimal(total_play)

    # ── Assemble results ───────────────────────────────────────────────────────
    per_player: list[PlayerResult] = []
    for ref in session.participants:
        owes_c = court_owe.get(ref.player_id, Decimal("0"))
        owes_s = shuttle_owe.get(ref.player_id, Decimal("0"))
        cred_c = court_credit.get(ref.player_id, Decimal("0"))
        cred_s = shuttle_credit.get(ref.player_id, Decimal("0"))
        owes_total = owes_c + owes_s
        cred_total = cred_c + cred_s
        per_player.append(
            PlayerResult(
                player_id=ref.player_id,
                name=ref.name,
                play_minutes=play_minutes.get(ref.player_id, 0),
                owes_court=round_to_5(owes_c),
                owes_shuttle=round_to_5(owes_s),
                credit_court=round_to_5(cred_c),
                credit_shuttle=round_to_5(cred_s),
                owes_total=round_to_5(owes_total),
                credit_total=round_to_5(cred_total),
                net=round_to_5(owes_total - cred_total),
            )
        )

    return SessionResult(
        per_player=tuple(per_player),
        court_rate_per_hour=session.court_rate_per_hour,
        shuttle_rate_per_hour=session.shuttle_rate_per_hour,
        total_court_cost=total_court_cost,
        total_shuttle_cost=total_shuttle_cost,
    )
```

- [ ] **Step 4: Run all calculator tests**

```bash
pytest tests/domain/test_calculator.py -v
```

Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add app/domain/calculator.py tests/domain/test_calculator.py
git commit -m "feat(domain): add shuttle cost calculation (pro-rata by play minutes)"
```

---

## Task B6: Calculator — Hypothesis property tests

**Files:**
- Create: `tests/domain/test_calculator_properties.py`

- [ ] **Step 1: Write the property tests**

`tests/domain/test_calculator_properties.py`:

```python
"""Property-based tests for the cost calculator using Hypothesis."""
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.calculator import calculate_session
from app.domain.models import (
    CourtInput,
    PlayerRef,
    SessionInput,
    ShuttleContributionInput,
    SlotInput,
)


@st.composite
def session_strategy(draw: st.DrawFn) -> SessionInput:
    n_players = draw(st.integers(min_value=2, max_value=8))
    player_ids = list(range(1, n_players + 1))
    refs = frozenset(PlayerRef(pid, f"P{pid}") for pid in player_ids)

    court_rate = Decimal(draw(st.integers(min_value=0, max_value=2000)))
    shuttle_rate = Decimal(draw(st.integers(min_value=0, max_value=200)))

    n_courts = draw(st.integers(min_value=1, max_value=3))
    courts = []
    for cid in range(10, 10 + n_courts):
        n_slots = draw(st.integers(min_value=1, max_value=6))
        slots = tuple(
            SlotInput(
                slot_index=i,
                player_ids=frozenset(
                    draw(st.sets(st.sampled_from(player_ids), min_size=0, max_size=n_players))
                ),
            )
            for i in range(n_slots)
        )
        booker = draw(st.sampled_from(player_ids))
        courts.append(
            CourtInput(
                court_id=cid,
                booker_player_id=booker,
                duration_minutes=n_slots * 30,
                slots=slots,
            )
        )

    n_contribs = draw(st.integers(min_value=0, max_value=3))
    contribs = tuple(
        ShuttleContributionInput(
            owner_player_id=draw(st.sampled_from(player_ids)),
            total_minutes=draw(st.integers(min_value=0, max_value=12)) * 30,
        )
        for _ in range(n_contribs)
    )

    return SessionInput(
        court_rate_per_hour=court_rate,
        shuttle_rate_per_hour=shuttle_rate,
        courts=tuple(courts),
        shuttle_contributions=contribs,
        participants=refs,
    )


@given(session_strategy())
@settings(max_examples=300, deadline=None)
def test_property_credits_equal_court_bills(session: SessionInput) -> None:
    """Sum of court credits equals sum of all court bills (pre-rounding)."""
    result = calculate_session(session)
    sum_credits = sum(p.credit_court for p in result.per_player)
    # rounding may introduce ±5 per player slack
    n = max(1, len(result.per_player))
    expected = int(result.total_court_cost)
    assert abs(sum_credits - expected) <= 5 * n


@given(session_strategy())
@settings(max_examples=300, deadline=None)
def test_property_non_negativity(session: SessionInput) -> None:
    result = calculate_session(session)
    for p in result.per_player:
        assert p.owes_court >= 0
        assert p.owes_shuttle >= 0
        assert p.credit_court >= 0
        assert p.credit_shuttle >= 0


@given(session_strategy())
@settings(max_examples=300, deadline=None)
def test_property_zero_shuttle_rate(session: SessionInput) -> None:
    if session.shuttle_rate_per_hour != Decimal("0"):
        return  # filter not enforced; skip
    result = calculate_session(session)
    for p in result.per_player:
        assert p.owes_shuttle == 0
        assert p.credit_shuttle == 0


@given(session_strategy())
@settings(max_examples=300, deadline=None)
def test_property_conservation(session: SessionInput) -> None:
    """Total owed ≈ total credited (within rounding slack)."""
    result = calculate_session(session)
    sum_owes = sum(p.owes_total for p in result.per_player)
    sum_credits = sum(p.credit_total for p in result.per_player)
    n = max(1, len(result.per_player))
    assert abs(sum_owes - sum_credits) <= 10 * n  # 5 per player on each side
```

- [ ] **Step 2: Run to verify all pass**

```bash
pytest tests/domain/test_calculator_properties.py -v
```

Expected: PASS. If any property fails with a Hypothesis-found counterexample, that's a real calculator bug — investigate and fix in `calculator.py`, then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/domain/test_calculator_properties.py
git commit -m "test(domain): add Hypothesis property tests for calculator invariants"
```

---

## Task B7: Phase B coverage gate

- [ ] **Step 1: Run domain coverage**

```bash
.venv/Scripts/pytest tests/domain --cov=app/domain --cov-report=term-missing
```

Expected: ≥ 95% branch coverage on `app/domain/*`. If below, write tests for uncovered branches.

- [ ] **Step 2: Run mypy**

```bash
.venv/Scripts/mypy app/domain --strict
```

Expected: Success: no issues.

- [ ] **Step 3: Commit any added tests**

```bash
git add tests/domain
git commit -m "test(domain): tighten coverage on calculator branches" || true
```

---

# Phase C — Persistence layer

## Task C1: Pydantic Settings module

**Files:**
- Create: `app/config/__init__.py` (empty)
- Create: `app/config/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings.py`:

```python
import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_settings_loads_with_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    s = Settings()
    assert s.database_url == "sqlite+aiosqlite:///:memory:"
    assert s.log_level == "info"
    assert s.tz == "Asia/Kolkata"


def test_settings_rejects_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_settings.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write `app/config/settings.py`**

```python
"""Application settings loaded from environment variables (12-factor)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(..., description="SQLAlchemy async DSN, e.g. sqlite+aiosqlite:///./data/badminton.db")
    log_level: str = Field("info", description="Log level: debug|info|warning|error")
    tz: str = Field("Asia/Kolkata", description="Timezone for date display")
    upi_id: str | None = Field(None, description="Default UPI ID interpolated into messages")
    metrics_enabled: bool = Field(True, description="Whether to expose /metrics")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_settings.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config tests/test_settings.py
git commit -m "feat(config): add Pydantic Settings (env-driven)"
```

---

## Task C2: Async SQLAlchemy engine + session factory

**Files:**
- Create: `app/persistence/__init__.py` (empty)
- Create: `app/persistence/database.py`
- Create: `tests/persistence/__init__.py` (empty)
- Create: `tests/persistence/test_database.py`

- [ ] **Step 1: Write the failing test**

`tests/persistence/test_database.py`:

```python
import pytest
from sqlalchemy import text

from app.persistence.database import Database


@pytest.mark.asyncio
async def test_database_connects_and_executes() -> None:
    db = Database("sqlite+aiosqlite:///:memory:")
    async with db.session() as session:
        result = await session.execute(text("SELECT 1 AS one"))
        assert result.scalar() == 1
    await db.dispose()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/persistence/test_database.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write `app/persistence/database.py`**

```python
"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, dsn: str) -> None:
        self._engine: AsyncEngine = create_async_engine(dsn, future=True)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self._engine.dispose()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/persistence/test_database.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/persistence/database.py tests/persistence/
git commit -m "feat(persistence): add async SQLAlchemy engine and session factory"
```

---

## Task C3: ORM models — Player, PlayerPhone

**Files:**
- Create: `app/persistence/orm.py`
- Modify: `tests/persistence/test_database.py` (add ORM smoke test)

- [ ] **Step 1: Write `app/persistence/orm.py`**

```python
"""SQLAlchemy ORM models. The single source of truth for the DB schema.

Migrations in alembic/versions/ derive from this module.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🏸", nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    phones: Mapped[list[PlayerPhone]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class PlayerPhone(Base):
    __tablename__ = "player_phones"
    __table_args__ = (UniqueConstraint("player_id", "e164_number", name="uq_player_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(4), default="IN", nullable=False)
    e164_number: Mapped[str] = mapped_column(String(20), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    player: Mapped[Player] = relationship(back_populates="phones")


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_court_rate_per_hour: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    current_shuttle_rate_per_hour: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rate_history: Mapped[list[VenueRateHistory]] = relationship(
        back_populates="venue", cascade="all, delete-orphan"
    )


class VenueRateHistory(Base):
    __tablename__ = "venue_rate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    court_rate_per_hour: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    shuttle_rate_per_hour: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    venue: Mapped[Venue] = relationship(back_populates="rate_history")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    played_on: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("draft", "finalized", "sent", name="session_status"),
        default="draft",
        nullable=False,
    )
    snapshot_court_rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    snapshot_shuttle_rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    courts: Mapped[list[Court]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    shuttle_contributions: Mapped[list[ShuttleContribution]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    booker_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session: Mapped[Session] = relationship(back_populates="courts")
    slots: Mapped[list[Slot]] = relationship(
        back_populates="court", cascade="all, delete-orphan", order_by="Slot.slot_index"
    )


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("court_id", "slot_index", name="uq_slot_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id", ondelete="CASCADE"), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)

    court: Mapped[Court] = relationship(back_populates="slots")
    players: Mapped[list[SlotPlayer]] = relationship(
        back_populates="slot", cascade="all, delete-orphan"
    )


class SlotPlayer(Base):
    __tablename__ = "slot_players"

    slot_id: Mapped[int] = mapped_column(
        ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)

    slot: Mapped[Slot] = relationship(back_populates="players")


class ShuttleContribution(Base):
    __tablename__ = "shuttle_contributions"
    __table_args__ = (
        UniqueConstraint("session_id", "owner_player_id", name="uq_session_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="shuttle_contributions")
```

- [ ] **Step 2: Smoke test that ORM creates a schema**

Append to `tests/persistence/test_database.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine

from app.persistence.database import Base
from app.persistence import orm  # noqa: F401  -- side effect: register tables


@pytest.mark.asyncio
async def test_orm_metadata_creates_all_tables() -> None:
    db = Database("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    expected = {
        "players", "player_phones", "venues", "venue_rate_history",
        "sessions", "courts", "slots", "slot_players", "shuttle_contributions",
    }
    async with db.engine.begin() as conn:
        result = await conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        names = {row[0] for row in result}
    assert expected.issubset(names)
    await db.dispose()
```

- [ ] **Step 3: Run**

```bash
pytest tests/persistence/test_database.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/persistence/orm.py tests/persistence/test_database.py
git commit -m "feat(persistence): add ORM models for Player, Venue, Session, Court, Slot, ShuttleContribution"
```

---

## Task C4: Alembic init + first autogenerate migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/.gitkeep`

- [ ] **Step 1: Run `alembic init`**

```bash
alembic init alembic
```

This generates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and `alembic/versions/`.

- [ ] **Step 2: Edit `alembic.ini` — set sqlalchemy.url to match `DATABASE_URL`**

In `alembic.ini`, replace the `sqlalchemy.url = ...` line with a placeholder (env reads from os):

```ini
sqlalchemy.url =
```

- [ ] **Step 3: Replace `alembic/env.py` with async-aware version**

```python
"""Alembic environment configured for async SQLAlchemy + ORM autogenerate."""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.persistence import orm  # noqa: F401  -- register ORM tables
from app.persistence.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/badminton.db")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate the first migration**

```bash
mkdir -p data
DATABASE_URL=sqlite+aiosqlite:///./data/badminton.db alembic revision --autogenerate -m "initial schema"
```

Inspect the generated migration in `alembic/versions/` — confirm it creates all 9 tables.

- [ ] **Step 5: Apply and verify**

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/badminton.db alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./data/badminton.db alembic downgrade base
DATABASE_URL=sqlite+aiosqlite:///./data/badminton.db alembic upgrade head
```

Expected: each command exits cleanly. The DB file is created and tables appear.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat(persistence): add Alembic migrations (initial schema)"
```

---

## Task C5: Migration smoke test in CI

**Files:**
- Create: `tests/persistence/test_migrations.py`

- [ ] **Step 1: Write the test**

```python
"""Verify Alembic migrations are reversible."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_alembic_migrations_run_cleanly(tmp_path: Path, direction: str) -> None:
    db_path = tmp_path / "test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

    # Always upgrade first
    r = subprocess.run(
        ["alembic", "upgrade", "head"], env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr

    if direction == "downgrade":
        r = subprocess.run(
            ["alembic", "downgrade", "base"], env=env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: Run**

```bash
pytest tests/persistence/test_migrations.py -v
```

Expected: PASS (both directions).

- [ ] **Step 3: Commit**

```bash
git add tests/persistence/test_migrations.py
git commit -m "test(persistence): verify Alembic migrations are reversible"
```

---

## Task C6: PlayerRepository

**Files:**
- Create: `app/persistence/repositories/__init__.py` (empty)
- Create: `app/persistence/repositories/player.py`
- Create: `tests/persistence/repositories/__init__.py` (empty)
- Create: `tests/persistence/repositories/test_player.py`
- Create: `tests/conftest.py` (shared fixtures)

- [ ] **Step 1: Write conftest fixtures**

`tests/conftest.py`:

```python
"""Shared pytest fixtures."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import orm  # noqa: F401
from app.persistence.database import Base, Database


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    db = Database("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield db
    await db.dispose()


@pytest_asyncio.fixture
async def session(db: Database) -> AsyncIterator[AsyncSession]:
    async with db.session() as s:
        yield s
```

- [ ] **Step 2: Write the failing test**

`tests/persistence/repositories/test_player.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.player import PlayerRepository


@pytest.mark.asyncio
async def test_create_and_get_player(session: AsyncSession) -> None:
    repo = PlayerRepository(session)
    p = await repo.create(name="Alice", emoji="🐰", is_guest=False)
    fetched = await repo.get(p.id)
    assert fetched is not None
    assert fetched.name == "Alice"


@pytest.mark.asyncio
async def test_list_active_players_excludes_inactive_and_deleted(session: AsyncSession) -> None:
    repo = PlayerRepository(session)
    a = await repo.create(name="A")
    b = await repo.create(name="B")
    c = await repo.create(name="C")
    await repo.set_active(b.id, False)
    await repo.soft_delete(c.id)
    actives = await repo.list_active()
    names = {p.name for p in actives}
    assert names == {"A"}


@pytest.mark.asyncio
async def test_add_phone(session: AsyncSession) -> None:
    repo = PlayerRepository(session)
    p = await repo.create(name="Alice")
    await repo.add_phone(p.id, e164="+919876543210", is_primary=True)
    refreshed = await repo.get(p.id)
    assert refreshed is not None
    assert refreshed.phones[0].e164_number == "+919876543210"
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/persistence/repositories/test_player.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Write the repository**

`app/persistence/repositories/player.py`:

```python
"""Player repository — only place that touches the players + player_phones tables."""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.orm import Player, PlayerPhone


class PlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        name: str,
        emoji: str = "🏸",
        is_guest: bool = False,
    ) -> Player:
        p = Player(name=name, emoji=emoji, is_guest=is_guest)
        self._s.add(p)
        await self._s.flush()
        return p

    async def get(self, player_id: int) -> Player | None:
        stmt = (
            select(Player)
            .where(Player.id == player_id)
            .options(selectinload(Player.phones))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def list_active(self) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(Player.is_active.is_(True), Player.deleted_at.is_(None))
            .options(selectinload(Player.phones))
            .order_by(Player.name)
        )
        return (await self._s.execute(stmt)).scalars().all()

    async def set_active(self, player_id: int, active: bool) -> None:
        p = await self.get(player_id)
        if p is None:
            return
        p.is_active = active

    async def soft_delete(self, player_id: int) -> None:
        p = await self.get(player_id)
        if p is None:
            return
        p.deleted_at = datetime.utcnow()
        p.is_active = False

    async def add_phone(self, player_id: int, *, e164: str, is_primary: bool = True) -> PlayerPhone:
        phone = PlayerPhone(player_id=player_id, e164_number=e164, is_primary=is_primary)
        self._s.add(phone)
        await self._s.flush()
        return phone
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/persistence/repositories/test_player.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/persistence/repositories tests/persistence tests/conftest.py
git commit -m "feat(persistence): add PlayerRepository"
```

---

## Task C7: VenueRepository

**Files:**
- Create: `app/persistence/repositories/venue.py`
- Create: `tests/persistence/repositories/test_venue.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.venue import VenueRepository


@pytest.mark.asyncio
async def test_create_venue_with_initial_rate_history(session: AsyncSession) -> None:
    repo = VenueRepository(session)
    v = await repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    assert v.id is not None
    fetched = await repo.get(v.id)
    assert fetched is not None
    assert len(fetched.rate_history) == 1
    assert fetched.rate_history[0].court_rate_per_hour == Decimal("400")


@pytest.mark.asyncio
async def test_update_rates_appends_history(session: AsyncSession) -> None:
    repo = VenueRepository(session)
    v = await repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    await repo.update_rates(
        v.id,
        court_rate=Decimal("450"),
        shuttle_rate=Decimal("60"),
        effective_from=date(2026, 4, 1),
    )
    refreshed = await repo.get(v.id)
    assert refreshed is not None
    assert refreshed.current_court_rate_per_hour == Decimal("450")
    assert len(refreshed.rate_history) == 2
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/persistence/repositories/test_venue.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write `app/persistence/repositories/venue.py`**

```python
"""Venue repository — manages venues + rate history."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.orm import Venue, VenueRateHistory


class VenueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        name: str,
        court_rate: Decimal,
        shuttle_rate: Decimal,
        effective_from: date,
        notes: str | None = None,
    ) -> Venue:
        v = Venue(
            name=name,
            notes=notes,
            current_court_rate_per_hour=court_rate,
            current_shuttle_rate_per_hour=shuttle_rate,
        )
        self._s.add(v)
        await self._s.flush()
        history = VenueRateHistory(
            venue_id=v.id,
            effective_from=effective_from,
            court_rate_per_hour=court_rate,
            shuttle_rate_per_hour=shuttle_rate,
        )
        self._s.add(history)
        await self._s.flush()
        return v

    async def get(self, venue_id: int) -> Venue | None:
        stmt = (
            select(Venue)
            .where(Venue.id == venue_id)
            .options(selectinload(Venue.rate_history))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> Sequence[Venue]:
        stmt = select(Venue).options(selectinload(Venue.rate_history)).order_by(Venue.name)
        return (await self._s.execute(stmt)).scalars().all()

    async def update_rates(
        self,
        venue_id: int,
        *,
        court_rate: Decimal,
        shuttle_rate: Decimal,
        effective_from: date,
    ) -> None:
        v = await self.get(venue_id)
        if v is None:
            return
        v.current_court_rate_per_hour = court_rate
        v.current_shuttle_rate_per_hour = shuttle_rate
        history = VenueRateHistory(
            venue_id=v.id,
            effective_from=effective_from,
            court_rate_per_hour=court_rate,
            shuttle_rate_per_hour=shuttle_rate,
        )
        self._s.add(history)
        await self._s.flush()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/persistence/repositories/test_venue.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/persistence/repositories/venue.py tests/persistence/repositories/test_venue.py
git commit -m "feat(persistence): add VenueRepository with rate history tracking"
```

---

## Task C8: SessionRepository (largest of the three)

**Files:**
- Create: `app/persistence/repositories/session.py`
- Create: `tests/persistence/repositories/test_session.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.session import SessionRepository
from app.persistence.repositories.venue import VenueRepository


@pytest.mark.asyncio
async def test_create_draft_with_courts_and_slots(session: AsyncSession) -> None:
    venue_repo = VenueRepository(session)
    player_repo = PlayerRepository(session)
    session_repo = SessionRepository(session)

    v = await venue_repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    a = await player_repo.create(name="A")
    b = await player_repo.create(name="B")

    s = await session_repo.create_draft(
        venue_id=v.id,
        played_on=date(2026, 4, 28),
        started_at=time(19, 0),
        duration_minutes=60,
        courts=[
            {
                "label": "Court 1",
                "booker_player_id": a.id,
                "duration_minutes": 60,
                "slot_assignments": [
                    {a.id, b.id},  # slot 0
                    {a.id, b.id},  # slot 1
                ],
            }
        ],
        shuttle_contributions=[
            {"owner_player_id": a.id, "total_minutes": 60},
        ],
    )
    fetched = await session_repo.get_aggregate(s.id)
    assert fetched is not None
    assert len(fetched.courts) == 1
    assert len(fetched.courts[0].slots) == 2
    assert fetched.courts[0].slots[0].players[0].player_id in {a.id, b.id}


@pytest.mark.asyncio
async def test_finalize_writes_rate_snapshot(session: AsyncSession) -> None:
    venue_repo = VenueRepository(session)
    player_repo = PlayerRepository(session)
    session_repo = SessionRepository(session)

    v = await venue_repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    a = await player_repo.create(name="A")
    b = await player_repo.create(name="B")

    s = await session_repo.create_draft(
        venue_id=v.id,
        played_on=date(2026, 4, 28),
        started_at=time(19, 0),
        duration_minutes=30,
        courts=[
            {
                "label": "Court 1",
                "booker_player_id": a.id,
                "duration_minutes": 30,
                "slot_assignments": [{a.id, b.id}],
            }
        ],
        shuttle_contributions=[],
    )
    await session_repo.finalize(s.id)
    refreshed = await session_repo.get_aggregate(s.id)
    assert refreshed is not None
    assert refreshed.status == "finalized"
    assert refreshed.snapshot_court_rate == Decimal("400")
    assert refreshed.snapshot_shuttle_rate == Decimal("50")
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/persistence/repositories/test_session.py -v
```

- [ ] **Step 3: Write the repository**

`app/persistence/repositories/session.py`:

```python
"""Session repository — manages sessions, courts, slots, slot players, shuttle contribs."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.orm import (
    Court,
    Session,
    ShuttleContribution,
    Slot,
    SlotPlayer,
    Venue,
)


class CourtInputDict(TypedDict):
    label: str
    booker_player_id: int
    duration_minutes: int
    slot_assignments: list[set[int]]  # one set of player_ids per slot


class ShuttleInputDict(TypedDict):
    owner_player_id: int
    total_minutes: int


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_draft(
        self,
        *,
        venue_id: int,
        played_on: date,
        started_at: time,
        duration_minutes: int,
        courts: list[CourtInputDict],
        shuttle_contributions: list[ShuttleInputDict],
        notes: str | None = None,
    ) -> Session:
        s = Session(
            venue_id=venue_id,
            played_on=played_on,
            started_at=started_at,
            duration_minutes=duration_minutes,
            notes=notes,
            status="draft",
        )
        self._s.add(s)
        await self._s.flush()

        for c in courts:
            court = Court(
                session_id=s.id,
                label=c["label"],
                booker_player_id=c["booker_player_id"],
                duration_minutes=c["duration_minutes"],
            )
            self._s.add(court)
            await self._s.flush()
            for idx, player_set in enumerate(c["slot_assignments"]):
                slot = Slot(court_id=court.id, slot_index=idx)
                self._s.add(slot)
                await self._s.flush()
                for pid in player_set:
                    self._s.add(SlotPlayer(slot_id=slot.id, player_id=pid))

        for shuttle in shuttle_contributions:
            self._s.add(
                ShuttleContribution(
                    session_id=s.id,
                    owner_player_id=shuttle["owner_player_id"],
                    total_minutes=shuttle["total_minutes"],
                )
            )

        await self._s.flush()
        return s

    async def get_aggregate(self, session_id: int) -> Session | None:
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .options(
                selectinload(Session.courts).selectinload(Court.slots).selectinload(Slot.players),
                selectinload(Session.shuttle_contributions),
            )
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def list_recent(self, limit: int = 20) -> Sequence[Session]:
        stmt = (
            select(Session)
            .order_by(Session.played_on.desc(), Session.id.desc())
            .limit(limit)
            .options(selectinload(Session.courts))
        )
        return (await self._s.execute(stmt)).scalars().all()

    async def finalize(self, session_id: int) -> None:
        s = await self.get_aggregate(session_id)
        if s is None:
            return
        venue = await self._s.get(Venue, s.venue_id)
        if venue is None:
            raise ValueError(f"venue {s.venue_id} not found")
        s.status = "finalized"
        s.snapshot_court_rate = venue.current_court_rate_per_hour
        s.snapshot_shuttle_rate = venue.current_shuttle_rate_per_hour
        s.finalized_at = datetime.utcnow()

    async def mark_sent(self, session_id: int) -> None:
        s = await self.get_aggregate(session_id)
        if s is None:
            return
        s.status = "sent"

    async def reopen(self, session_id: int) -> None:
        s = await self.get_aggregate(session_id)
        if s is None:
            return
        s.status = "finalized"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/persistence/repositories/test_session.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/persistence/repositories/session.py tests/persistence/repositories/test_session.py
git commit -m "feat(persistence): add SessionRepository (draft + finalize + aggregate fetch)"
```

---

# Phase D — Services layer

## Task D1: Domain ↔ ORM mapping helper

**Files:**
- Create: `app/services/__init__.py` (empty)
- Create: `app/services/mapping.py`
- Create: `tests/services/__init__.py` (empty)
- Create: `tests/services/test_mapping.py`

- [ ] **Step 1: Write the failing test**

`tests/services/test_mapping.py`:

```python
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.session import SessionRepository
from app.persistence.repositories.venue import VenueRepository
from app.services.mapping import session_orm_to_domain


@pytest.mark.asyncio
async def test_session_orm_maps_to_domain_input(session: AsyncSession) -> None:
    venue_repo = VenueRepository(session)
    player_repo = PlayerRepository(session)
    session_repo = SessionRepository(session)

    v = await venue_repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    a = await player_repo.create(name="Alice")
    b = await player_repo.create(name="Bob")

    s = await session_repo.create_draft(
        venue_id=v.id,
        played_on=date(2026, 4, 28),
        started_at=time(19, 0),
        duration_minutes=30,
        courts=[
            {
                "label": "Court 1",
                "booker_player_id": a.id,
                "duration_minutes": 30,
                "slot_assignments": [{a.id, b.id}],
            }
        ],
        shuttle_contributions=[],
    )
    await session_repo.finalize(s.id)
    aggregate = await session_repo.get_aggregate(s.id)
    assert aggregate is not None

    domain = await session_orm_to_domain(session, aggregate)
    assert domain.court_rate_per_hour == Decimal("400")
    assert len(domain.courts) == 1
    assert domain.courts[0].slots[0].player_ids == frozenset({a.id, b.id})
    names = {p.name for p in domain.participants}
    assert names == {"Alice", "Bob"}
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/services/test_mapping.py -v
```

- [ ] **Step 3: Write the mapping helper**

`app/services/mapping.py`:

```python
"""Map ORM session aggregates to pure-domain SessionInput."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    CourtInput,
    PlayerRef,
    SessionInput,
    ShuttleContributionInput,
    SlotInput,
)
from app.persistence.orm import Player, Session as ORMSession


async def session_orm_to_domain(session: AsyncSession, s: ORMSession) -> SessionInput:
    if s.snapshot_court_rate is None or s.snapshot_shuttle_rate is None:
        raise ValueError(
            f"session {s.id} is not finalized; rate snapshots are required for calculation"
        )

    courts = tuple(
        CourtInput(
            court_id=c.id,
            booker_player_id=c.booker_player_id,
            duration_minutes=c.duration_minutes,
            slots=tuple(
                SlotInput(
                    slot_index=slot.slot_index,
                    player_ids=frozenset(sp.player_id for sp in slot.players),
                )
                for slot in c.slots
            ),
        )
        for c in s.courts
    )

    contribs = tuple(
        ShuttleContributionInput(
            owner_player_id=sc.owner_player_id, total_minutes=sc.total_minutes
        )
        for sc in s.shuttle_contributions
    )

    # Collect participant ids and load names
    participant_ids: set[int] = set()
    for c in s.courts:
        participant_ids.add(c.booker_player_id)
        for slot in c.slots:
            participant_ids.update(sp.player_id for sp in slot.players)
    for sc in s.shuttle_contributions:
        participant_ids.add(sc.owner_player_id)

    if participant_ids:
        stmt = select(Player).where(Player.id.in_(participant_ids))
        rows = (await session.execute(stmt)).scalars().all()
        refs = frozenset(PlayerRef(p.id, p.name) for p in rows)
    else:
        refs = frozenset()

    return SessionInput(
        court_rate_per_hour=Decimal(s.snapshot_court_rate),
        shuttle_rate_per_hour=Decimal(s.snapshot_shuttle_rate),
        courts=courts,
        shuttle_contributions=contribs,
        participants=refs,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/services/test_mapping.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/__init__.py app/services/mapping.py tests/services
git commit -m "feat(services): map ORM session aggregate to domain SessionInput"
```

---

## Task D2: SessionService — finalize and compute

**Files:**
- Create: `app/services/session_service.py`
- Create: `tests/services/test_session_service.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.venue import VenueRepository
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_finalize_and_compute_returns_result(session: AsyncSession) -> None:
    venue_repo = VenueRepository(session)
    player_repo = PlayerRepository(session)
    service = SessionService(session)

    v = await venue_repo.create(
        name="Sportsbox",
        court_rate=Decimal("400"),
        shuttle_rate=Decimal("50"),
        effective_from=date(2026, 1, 1),
    )
    a = await player_repo.create(name="Alice")
    b = await player_repo.create(name="Bob")

    sid = await service.create_draft(
        venue_id=v.id,
        played_on=date(2026, 4, 28),
        started_at=time(19, 0),
        duration_minutes=30,
        courts=[
            {
                "label": "Court 1",
                "booker_player_id": a.id,
                "duration_minutes": 30,
                "slot_assignments": [{a.id, b.id}],
            }
        ],
        shuttle_contributions=[],
    )
    result = await service.finalize_and_compute(sid)
    by_id = {p.player_id: p for p in result.per_player}
    assert by_id[a.id].owes_court == 100
    assert by_id[b.id].owes_court == 100
    assert by_id[a.id].credit_court == 200
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/services/test_session_service.py -v
```

- [ ] **Step 3: Write the service**

`app/services/session_service.py`:

```python
"""Session orchestration. Wraps repositories + domain calculator."""
from __future__ import annotations

from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.calculator import calculate_session
from app.domain.models import SessionResult
from app.persistence.repositories.session import (
    CourtInputDict,
    SessionRepository,
    ShuttleInputDict,
)
from app.services.mapping import session_orm_to_domain


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = SessionRepository(session)

    async def create_draft(
        self,
        *,
        venue_id: int,
        played_on: date,
        started_at: time,
        duration_minutes: int,
        courts: list[CourtInputDict],
        shuttle_contributions: list[ShuttleInputDict],
        notes: str | None = None,
    ) -> int:
        s = await self._repo.create_draft(
            venue_id=venue_id,
            played_on=played_on,
            started_at=started_at,
            duration_minutes=duration_minutes,
            courts=courts,
            shuttle_contributions=shuttle_contributions,
            notes=notes,
        )
        return s.id

    async def finalize_and_compute(self, session_id: int) -> SessionResult:
        await self._repo.finalize(session_id)
        aggregate = await self._repo.get_aggregate(session_id)
        if aggregate is None:
            raise ValueError(f"session {session_id} not found")
        domain_input = await session_orm_to_domain(self._s, aggregate)
        return calculate_session(domain_input)

    async def compute(self, session_id: int) -> SessionResult:
        """Recompute a finalized session without re-finalizing (for re-rendering)."""
        aggregate = await self._repo.get_aggregate(session_id)
        if aggregate is None:
            raise ValueError(f"session {session_id} not found")
        domain_input = await session_orm_to_domain(self._s, aggregate)
        return calculate_session(domain_input)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/services/test_session_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/session_service.py tests/services/test_session_service.py
git commit -m "feat(services): add SessionService (create draft, finalize, compute)"
```

---

## Task D3: Messaging service — generate WhatsApp message + wa.me URL

**Files:**
- Create: `app/services/messaging.py`
- Create: `tests/services/test_messaging.py`

- [ ] **Step 1: Write the failing test**

```python
from app.domain.models import PlayerResult
from app.services.messaging import (
    DEFAULT_TEMPLATE,
    build_message_text,
    build_wa_me_url,
)


def make_result(net: int = 170, owes_court: int = 150, owes_shuttle: int = 20) -> PlayerResult:
    return PlayerResult(
        player_id=1,
        name="Carol",
        play_minutes=90,
        owes_court=owes_court,
        owes_shuttle=owes_shuttle,
        credit_court=0,
        credit_shuttle=0,
        owes_total=owes_court + owes_shuttle,
        credit_total=0,
        net=net,
    )


def test_build_message_text_renders_owes_direction() -> None:
    text = build_message_text(
        template=DEFAULT_TEMPLATE,
        player=make_result(),
        played_on="28 Apr 2026",
        venue="Sportsbox",
        upi_id="alice@upi",
    )
    assert "Hi Carol!" in text
    assert "₹150" in text
    assert "₹20" in text
    assert "you owe me" in text
    assert "alice@upi" in text


def test_build_message_text_renders_owed_direction() -> None:
    text = build_message_text(
        template=DEFAULT_TEMPLATE,
        player=make_result(net=-100),
        played_on="28 Apr 2026",
        venue="Sportsbox",
        upi_id=None,
    )
    assert "I owe you" in text
    assert "₹100" in text


def test_build_message_text_omits_credit_lines_when_no_credit() -> None:
    text = build_message_text(
        template=DEFAULT_TEMPLATE,
        player=make_result(),
        played_on="28 Apr 2026",
        venue="Sportsbox",
        upi_id="x@upi",
    )
    assert "credited" not in text.lower()


def test_build_wa_me_url() -> None:
    url = build_wa_me_url("+919876543210", "Hi there 🏸")
    assert url.startswith("https://wa.me/919876543210?text=")
    assert "Hi%20there" in url
    # emoji must be URL-encoded
    assert "%F0%9F%8F%B8" in url


def test_build_wa_me_url_rejects_non_e164() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_wa_me_url("9876543210", "hi")
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/services/test_messaging.py -v
```

- [ ] **Step 3: Write `app/services/messaging.py`**

```python
"""WhatsApp message generation. wa.me link + text rendering."""
from __future__ import annotations

from urllib.parse import quote

from app.domain.models import PlayerResult


DEFAULT_TEMPLATE = """\
Hi {name}! 🏸
Badminton on {played_on} at {venue}:
• Court: ₹{owes_court}
• Shuttle: ₹{owes_shuttle}
{credit_lines}
Total: ₹{abs_net} {direction}

{upi_line}
""".strip()


def build_message_text(
    *,
    template: str,
    player: PlayerResult,
    played_on: str,
    venue: str,
    upi_id: str | None,
) -> str:
    direction = (
        "you owe me" if player.net > 0
        else "I owe you" if player.net < 0
        else "settled"
    )
    credit_lines = ""
    if player.credit_total > 0:
        if player.credit_court > 0:
            credit_lines += f"• You're credited ₹{player.credit_court} for booking court\n"
        if player.credit_shuttle > 0:
            credit_lines += f"• You're credited ₹{player.credit_shuttle} for shuttles\n"
        credit_lines = credit_lines.rstrip()

    upi_line = f"Pay via UPI: {upi_id}" if upi_id else ""

    return template.format(
        name=player.name,
        played_on=played_on,
        venue=venue,
        owes_court=player.owes_court,
        owes_shuttle=player.owes_shuttle,
        credit_lines=credit_lines,
        abs_net=abs(player.net),
        direction=direction,
        upi_line=upi_line,
    )


def build_wa_me_url(e164_phone: str, message: str) -> str:
    if not e164_phone.startswith("+"):
        raise ValueError(f"phone must be in E.164 format with leading +; got {e164_phone!r}")
    digits = e164_phone[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/services/test_messaging.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/messaging.py tests/services/test_messaging.py
git commit -m "feat(services): add WhatsApp message + wa.me URL generation"
```

---

# Phase E — API layer

## Task E1: FastAPI app factory + health endpoint

**Files:**
- Create: `app/main.py`
- Create: `app/api/__init__.py` (empty)
- Create: `app/api/deps.py`
- Create: `tests/api/__init__.py` (empty)
- Create: `tests/api/test_health.py`

- [ ] **Step 1: Write the failing test**

`tests/api/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/api/test_health.py -v
```

- [ ] **Step 3: Write deps**

`app/api/deps.py`:

```python
"""FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import Database


def get_db(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    db: Database = request.app.state.db
    async with db.session() as s:
        yield s
```

- [ ] **Step 4: Write the app factory**

`app/main.py`:

```python
"""FastAPI app factory and uvicorn entrypoint."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.persistence import orm  # noqa: F401
from app.persistence.database import Database


def build_app(database_url: str | None = None) -> FastAPI:
    dsn = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/badminton.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(dsn)
        app.state.db = db
        try:
            yield
        finally:
            await db.dispose()

    app = FastAPI(title="Badminton Splitter", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        db: Database = app.state.db
        async with db.session() as s:
            await s.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.mount(
        "/static",
        StaticFiles(directory="app/web/static"),
        name="static",
    )

    return app


app = build_app()
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/api/test_health.py -v
```

Expected: PASS (you may see a `StaticFiles` warning if `app/web/static` doesn't exist — create the dir or skip the mount during testing in a follow-up; for now `mkdir -p app/web/static`).

```bash
mkdir -p app/web/static/css app/web/static/js
touch app/web/static/css/.gitkeep app/web/static/js/.gitkeep
```

Re-run; expect: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/api tests/api app/web/static
git commit -m "feat(api): add FastAPI app factory and /health endpoint"
```

---

## Task E2: Pydantic schemas

**Files:**
- Create: `app/api/schemas/__init__.py` (empty)
- Create: `app/api/schemas/player.py`
- Create: `app/api/schemas/venue.py`
- Create: `app/api/schemas/session.py`

- [ ] **Step 1: Write `app/api/schemas/player.py`**

```python
"""Pydantic schemas for player endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
import phonenumbers


class PlayerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    emoji: str = Field("🏸", max_length=8)
    phone: str | None = None
    is_guest: bool = False

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        try:
            parsed = phonenumbers.parse(v, "IN")
        except phonenumbers.NumberParseException as e:
            raise ValueError(f"invalid phone: {e}") from e
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("invalid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class PlayerOut(BaseModel):
    id: int
    name: str
    emoji: str
    is_guest: bool
    is_active: bool
    primary_phone: str | None
```

- [ ] **Step 2: Write `app/api/schemas/venue.py`**

```python
"""Pydantic schemas for venue endpoints."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class VenueCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    court_rate: Decimal = Field(..., ge=Decimal("0"))
    shuttle_rate: Decimal = Field(..., ge=Decimal("0"))
    effective_from: date
    notes: str | None = None


class VenueOut(BaseModel):
    id: int
    name: str
    notes: str | None
    current_court_rate: Decimal
    current_shuttle_rate: Decimal
```

- [ ] **Step 3: Write `app/api/schemas/session.py`**

```python
"""Pydantic schemas for session wizard."""
from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, field_validator


class CourtSubmit(BaseModel):
    label: str = Field(..., min_length=1, max_length=50)
    booker_player_id: int
    duration_minutes: int
    slot_assignments: list[list[int]]  # one list of player_ids per slot

    @field_validator("duration_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v <= 0 or v % 30 != 0:
            raise ValueError("duration_minutes must be a positive multiple of 30")
        return v


class ShuttleSubmit(BaseModel):
    owner_player_id: int
    total_minutes: int = Field(..., ge=0)

    @field_validator("total_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v % 30 != 0:
            raise ValueError("total_minutes must be a multiple of 30")
        return v


class SessionSubmit(BaseModel):
    venue_id: int
    played_on: date
    started_at: time
    duration_minutes: int
    courts: list[CourtSubmit]
    shuttle_contributions: list[ShuttleSubmit] = []
    notes: str | None = None

    @field_validator("duration_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v <= 0 or v % 30 != 0:
            raise ValueError("duration_minutes must be a positive multiple of 30")
        return v


class PlayerResultOut(BaseModel):
    player_id: int
    name: str
    play_minutes: int
    owes_court: int
    owes_shuttle: int
    credit_court: int
    credit_shuttle: int
    owes_total: int
    credit_total: int
    net: int


class SessionResultOut(BaseModel):
    per_player: list[PlayerResultOut]
    total_court_cost: float
    total_shuttle_cost: float
```

- [ ] **Step 4: Verify import**

```bash
python -c "from app.api.schemas import session, player, venue"
```

Expected: silent success.

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas
git commit -m "feat(api): add Pydantic request/response schemas"
```

---

## Task E3: Players router

**Files:**
- Create: `app/api/routers/__init__.py` (empty)
- Create: `app/api/routers/players.py`
- Create: `tests/api/test_players.py`
- Modify: `app/main.py` (register router)

- [ ] **Step 1: Write the failing test**

`tests/api/test_players.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_create_and_list_player() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    db = None
    async with ASGITransport(app=app) as transport:  # noqa: SIM117
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # bootstrap schema
            r = await client.get("/health")
            assert r.status_code == 200
            db = app.state.db
            async with db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            r = await client.post(
                "/api/players",
                json={"name": "Alice", "emoji": "🐰", "phone": "+919876543210"},
            )
            assert r.status_code == 201, r.text
            created = r.json()
            assert created["name"] == "Alice"
            assert created["primary_phone"] == "+919876543210"

            r = await client.get("/api/players")
            assert r.status_code == 200
            assert any(p["name"] == "Alice" for p in r.json())
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/api/test_players.py -v
```

- [ ] **Step 3: Write the router**

`app/api/routers/players.py`:

```python
"""Player REST endpoints (used by HTMX wizard and standalone)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.player import PlayerCreate, PlayerOut
from app.persistence.repositories.player import PlayerRepository

router = APIRouter(prefix="/api/players", tags=["players"])


def _to_out(player) -> PlayerOut:  # type: ignore[no-untyped-def]
    primary = next((p for p in player.phones if p.is_primary), None) if player.phones else None
    return PlayerOut(
        id=player.id,
        name=player.name,
        emoji=player.emoji,
        is_guest=player.is_guest,
        is_active=player.is_active,
        primary_phone=primary.e164_number if primary else None,
    )


@router.get("", response_model=list[PlayerOut])
async def list_players(session: AsyncSession = Depends(get_session)) -> list[PlayerOut]:
    repo = PlayerRepository(session)
    players = await repo.list_active()
    return [_to_out(p) for p in players]


@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def create_player(
    payload: PlayerCreate, session: AsyncSession = Depends(get_session)
) -> PlayerOut:
    repo = PlayerRepository(session)
    p = await repo.create(name=payload.name, emoji=payload.emoji, is_guest=payload.is_guest)
    if payload.phone:
        await repo.add_phone(p.id, e164=payload.phone, is_primary=True)
    refreshed = await repo.get(p.id)
    if refreshed is None:
        raise HTTPException(500, "could not reload player")
    return _to_out(refreshed)
```

- [ ] **Step 4: Register router in `app/main.py`**

In `build_app`, before returning app, add:

```python
from app.api.routers import players as players_router

app.include_router(players_router.router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/api/test_players.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/routers app/main.py tests/api/test_players.py
git commit -m "feat(api): add /api/players (list + create)"
```

---

## Task E4: Venues router

**Files:**
- Create: `app/api/routers/venues.py`
- Create: `tests/api/test_venues.py`
- Modify: `app/main.py` (register router)

- [ ] **Step 1: Write the failing test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_create_and_list_venue() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as transport:  # noqa: SIM117
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            r = await client.post(
                "/api/venues",
                json={
                    "name": "Sportsbox",
                    "court_rate": "400",
                    "shuttle_rate": "50",
                    "effective_from": "2026-01-01",
                },
            )
            assert r.status_code == 201, r.text
            r = await client.get("/api/venues")
            assert r.status_code == 200
            assert any(v["name"] == "Sportsbox" for v in r.json())
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/api/test_venues.py -v
```

- [ ] **Step 3: Write the router**

`app/api/routers/venues.py`:

```python
"""Venue REST endpoints."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.venue import VenueCreate, VenueOut
from app.persistence.repositories.venue import VenueRepository

router = APIRouter(prefix="/api/venues", tags=["venues"])


@router.get("", response_model=list[VenueOut])
async def list_venues(session: AsyncSession = Depends(get_session)) -> list[VenueOut]:
    repo = VenueRepository(session)
    venues = await repo.list_all()
    return [
        VenueOut(
            id=v.id,
            name=v.name,
            notes=v.notes,
            current_court_rate=Decimal(v.current_court_rate_per_hour),
            current_shuttle_rate=Decimal(v.current_shuttle_rate_per_hour),
        )
        for v in venues
    ]


@router.post("", response_model=VenueOut, status_code=status.HTTP_201_CREATED)
async def create_venue(
    payload: VenueCreate, session: AsyncSession = Depends(get_session)
) -> VenueOut:
    repo = VenueRepository(session)
    v = await repo.create(
        name=payload.name,
        court_rate=payload.court_rate,
        shuttle_rate=payload.shuttle_rate,
        effective_from=payload.effective_from,
        notes=payload.notes,
    )
    refreshed = await repo.get(v.id)
    if refreshed is None:
        raise HTTPException(500, "could not reload venue")
    return VenueOut(
        id=refreshed.id,
        name=refreshed.name,
        notes=refreshed.notes,
        current_court_rate=Decimal(refreshed.current_court_rate_per_hour),
        current_shuttle_rate=Decimal(refreshed.current_shuttle_rate_per_hour),
    )
```

- [ ] **Step 4: Register router in `app/main.py`**

```python
from app.api.routers import venues as venues_router
app.include_router(venues_router.router)
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/api/test_venues.py -v
git add app/api/routers/venues.py tests/api/test_venues.py app/main.py
git commit -m "feat(api): add /api/venues (list + create with rate history)"
```

---

## Task E5: Sessions router (create draft + finalize + result)

**Files:**
- Create: `app/api/routers/sessions.py`
- Create: `tests/api/test_sessions.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_full_session_flow() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as transport:  # noqa: SIM117
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            r = await client.post(
                "/api/venues",
                json={
                    "name": "Sportsbox", "court_rate": "400",
                    "shuttle_rate": "50", "effective_from": "2026-01-01",
                },
            )
            venue_id = r.json()["id"]

            a = (await client.post("/api/players", json={"name": "Alice"})).json()["id"]
            b = (await client.post("/api/players", json={"name": "Bob"})).json()["id"]

            r = await client.post(
                "/api/sessions",
                json={
                    "venue_id": venue_id,
                    "played_on": "2026-04-28",
                    "started_at": "19:00:00",
                    "duration_minutes": 30,
                    "courts": [
                        {
                            "label": "Court 1",
                            "booker_player_id": a,
                            "duration_minutes": 30,
                            "slot_assignments": [[a, b]],
                        }
                    ],
                    "shuttle_contributions": [],
                },
            )
            assert r.status_code == 201, r.text
            sid = r.json()["id"]

            r = await client.post(f"/api/sessions/{sid}/finalize")
            assert r.status_code == 200, r.text
            data = r.json()
            by_id = {p["player_id"]: p for p in data["per_player"]}
            assert by_id[a]["owes_court"] == 100
            assert by_id[b]["owes_court"] == 100
```

- [ ] **Step 2: Run failure**

```bash
pytest tests/api/test_sessions.py -v
```

- [ ] **Step 3: Write the router**

`app/api/routers/sessions.py`:

```python
"""Session wizard endpoints (JSON API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.session import (
    PlayerResultOut,
    SessionResultOut,
    SessionSubmit,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: SessionSubmit, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    service = SessionService(session)
    courts = [
        {
            "label": c.label,
            "booker_player_id": c.booker_player_id,
            "duration_minutes": c.duration_minutes,
            "slot_assignments": [set(slot) for slot in c.slot_assignments],
        }
        for c in payload.courts
    ]
    contribs = [
        {"owner_player_id": c.owner_player_id, "total_minutes": c.total_minutes}
        for c in payload.shuttle_contributions
    ]
    sid = await service.create_draft(
        venue_id=payload.venue_id,
        played_on=payload.played_on,
        started_at=payload.started_at,
        duration_minutes=payload.duration_minutes,
        courts=courts,
        shuttle_contributions=contribs,
        notes=payload.notes,
    )
    return {"id": sid}


@router.post("/{session_id}/finalize", response_model=SessionResultOut)
async def finalize_session(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> SessionResultOut:
    service = SessionService(session)
    try:
        result = await service.finalize_and_compute(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return SessionResultOut(
        per_player=[
            PlayerResultOut(
                player_id=p.player_id,
                name=p.name,
                play_minutes=p.play_minutes,
                owes_court=p.owes_court,
                owes_shuttle=p.owes_shuttle,
                credit_court=p.credit_court,
                credit_shuttle=p.credit_shuttle,
                owes_total=p.owes_total,
                credit_total=p.credit_total,
                net=p.net,
            )
            for p in result.per_player
        ],
        total_court_cost=float(result.total_court_cost),
        total_shuttle_cost=float(result.total_shuttle_cost),
    )
```

- [ ] **Step 4: Register, run, commit**

In `app/main.py`:
```python
from app.api.routers import sessions as sessions_router
app.include_router(sessions_router.router)
```

```bash
pytest tests/api/test_sessions.py -v
git add app/api/routers/sessions.py tests/api/test_sessions.py app/main.py
git commit -m "feat(api): add /api/sessions (create draft + finalize+compute)"
```

---

# Phase F — Web UI (templates, Tailwind, HTMX)

This phase is more file-heavy than logic-heavy. I'll be efficient: design tokens + base layout in one task, then one task per screen group. Each task creates a subset of templates, wires the route in a router, and adds a smoke test that the page renders.

## Task F1: Tailwind setup + design tokens + base template

**Files:**
- Create: `app/web/templates/base.html`
- Create: `app/web/templates/_macros.html`
- Create: `app/web/static/css/tailwind.input.css`
- Create: `tailwind.config.js`
- Create: `app/web/static/js/htmx.min.js` (vendored — download from htmx.org)
- Modify: `Makefile` (already has `tailwind` target)

- [ ] **Step 1: Install Tailwind CLI standalone binary**

Tailwind v4 standalone binary download:
```bash
# pick the right binary for your OS from https://github.com/tailwindlabs/tailwindcss/releases
# place as `tailwindcss` (or `tailwindcss.exe` on Windows) on PATH
```

Verify:
```bash
tailwindcss --help
```

- [ ] **Step 2: Write `tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/web/templates/**/*.html",
    "./app/web/static/js/**/*.js",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        // OKLCH-based palette via CSS variables in tailwind.input.css
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        ink: "var(--color-ink)",
        muted: "var(--color-muted)",
        accent: "var(--color-accent)",
        "accent-fg": "var(--color-accent-fg)",
        positive: "var(--color-positive)",
        negative: "var(--color-negative)",
      },
      borderRadius: {
        DEFAULT: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 3: Write `app/web/static/css/tailwind.input.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --color-surface: oklch(98% 0.01 270);
    --color-surface-2: oklch(95% 0.01 270);
    --color-ink: oklch(20% 0.02 270);
    --color-muted: oklch(50% 0.02 270);
    --color-accent: oklch(60% 0.18 200);
    --color-accent-fg: oklch(98% 0.01 200);
    --color-positive: oklch(65% 0.15 145);
    --color-negative: oklch(60% 0.20 25);
  }

  html.dark {
    --color-surface: oklch(15% 0.01 270);
    --color-surface-2: oklch(20% 0.01 270);
    --color-ink: oklch(95% 0.01 270);
    --color-muted: oklch(65% 0.02 270);
    --color-accent: oklch(70% 0.18 200);
    --color-accent-fg: oklch(15% 0.01 200);
    --color-positive: oklch(70% 0.15 145);
    --color-negative: oklch(70% 0.20 25);
  }

  html, body {
    background: var(--color-surface);
    color: var(--color-ink);
    font-family: theme('fontFamily.sans');
  }
}

@layer components {
  .btn {
    @apply inline-flex items-center justify-center gap-2 px-4 py-2 rounded font-medium
           transition-colors focus-visible:outline-2 focus-visible:outline-accent
           min-h-[44px];
  }
  .btn-primary {
    @apply btn bg-accent text-accent-fg hover:opacity-90;
  }
  .btn-ghost {
    @apply btn hover:bg-surface-2;
  }
  .card {
    @apply bg-surface-2 rounded-lg p-4;
  }
  .num {
    @apply font-mono tabular-nums;
  }
}
```

- [ ] **Step 4: Build Tailwind once**

```bash
make tailwind
```

Expected: `app/web/static/css/tailwind.output.css` is generated.

- [ ] **Step 5: Vendor HTMX**

Download `htmx.min.js` 1.9+ from https://htmx.org/ and save as `app/web/static/js/htmx.min.js`.

- [ ] **Step 6: Write `app/web/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en" class="{{ theme_class | default('') }}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  <title>{% block title %}Badminton Splitter{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/tailwind.output.css" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <script defer src="/static/js/htmx.min.js"></script>
</head>
<body class="min-h-screen">
  <main class="max-w-[480px] mx-auto px-4 pt-6 pb-24">
    {% block content %}{% endblock %}
  </main>

  <nav class="fixed bottom-0 left-0 right-0 bg-surface-2 border-t border-muted/20">
    <div class="max-w-[480px] mx-auto grid grid-cols-3 gap-1 p-2">
      <a href="/" class="btn-ghost flex-col text-xs">Sessions</a>
      <a href="/players" class="btn-ghost flex-col text-xs">Roster</a>
      <a href="/settings" class="btn-ghost flex-col text-xs">Settings</a>
    </div>
  </nav>

  <script>
    // Theme: respect saved preference, fall back to system
    const saved = localStorage.getItem('theme');
    const sysDark = matchMedia('(prefers-color-scheme: dark)').matches;
    if (saved === 'dark' || (!saved && sysDark)) document.documentElement.classList.add('dark');
  </script>
</body>
</html>
```

- [ ] **Step 7: Add Jinja2 to FastAPI**

Modify `app/main.py` — inside `build_app`, add:

```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/web/templates")
app.state.templates = templates
```

- [ ] **Step 8: Smoke render of base via a temporary route**

Add to `app/main.py`:

```python
from fastapi import Request
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse("base.html", {"request": request})
```

Manually verify:

```bash
make dev
# Visit http://localhost:8080 — should render an empty page with bottom nav.
```

- [ ] **Step 9: Commit**

```bash
git add tailwind.config.js app/web/static/css/tailwind.input.css app/web/static/js/htmx.min.js app/web/templates/base.html app/main.py
git commit -m "feat(web): Tailwind v4 setup, design tokens, base template, HTMX vendored"
```

---

## Task F2: Sessions list page

**Files:**
- Create: `app/web/templates/sessions/list.html`
- Modify: `app/api/routers/sessions.py` (add HTML route at `/`)
- Create: `tests/api/test_sessions_html.py`

- [ ] **Step 1: Write the test**

`tests/api/test_sessions_html.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_sessions_list_renders() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as t:  # noqa: SIM117
        async with AsyncClient(transport=t, base_url="http://test") as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            r = await client.get("/")
            assert r.status_code == 200
            assert "Sessions" in r.text or "session" in r.text.lower()
```

- [ ] **Step 2: Write template `app/web/templates/sessions/list.html`**

```html
{% extends "base.html" %}
{% block title %}Sessions · Badminton Splitter{% endblock %}
{% block content %}
<header class="flex items-center justify-between mb-6">
  <h1 class="text-2xl font-semibold">Sessions</h1>
</header>

{% if sessions %}
  <ul class="space-y-3">
    {% for s in sessions %}
      <li>
        <a href="/sessions/{{ s.id }}" class="card block hover:bg-surface-2/80 transition-colors">
          <div class="flex justify-between">
            <div>
              <div class="font-medium">{{ s.played_on.strftime('%a %d %b') }} · {{ s.venue_name }}</div>
              <div class="text-sm text-muted">{{ s.player_count }} players · {{ (s.duration_minutes / 60) | round(1) }} hr · {{ s.court_count }} ct</div>
            </div>
            <div class="text-right">
              <span class="text-xs uppercase tracking-wide text-muted">{{ s.status }}</span>
            </div>
          </div>
        </a>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <div class="card text-center text-muted">
    No sessions yet. Tap the + below to start.
  </div>
{% endif %}

<a href="/sessions/new" class="fixed bottom-20 right-4 btn-primary rounded-full w-14 h-14 text-2xl">+</a>
{% endblock %}
```

- [ ] **Step 3: Replace the temporary `/` route with a real one**

In `app/main.py`, replace the `home` function:

```python
@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    from app.persistence.repositories.session import SessionRepository
    from app.persistence.repositories.venue import VenueRepository

    db = app.state.db
    templates = app.state.templates
    async with db.session() as s:
        sessions = await SessionRepository(s).list_recent(limit=20)
        venues = {v.id: v for v in await VenueRepository(s).list_all()}
    rows = [
        {
            "id": x.id,
            "played_on": x.played_on,
            "venue_name": venues[x.venue_id].name if x.venue_id in venues else "?",
            "player_count": len({sp.player_id for c in x.courts for sl in c.slots for sp in sl.players}) if x.courts else 0,
            "duration_minutes": x.duration_minutes,
            "court_count": len(x.courts),
            "status": x.status,
        }
        for x in sessions
    ]
    return templates.TemplateResponse("sessions/list.html", {"request": request, "sessions": rows})
```

- [ ] **Step 4: Run test**

```bash
pytest tests/api/test_sessions_html.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/web/templates/sessions/list.html app/main.py tests/api/test_sessions_html.py
git commit -m "feat(web): sessions list page"
```

---

## Task F3: New-session wizard — Setup + Players steps

**Files:**
- Create: `app/web/templates/sessions/new_setup.html`
- Create: `app/web/templates/sessions/new_players.html`
- Create: `app/api/routers/sessions_html.py` — separate from API router for HTML routes
- Modify: `app/main.py` (register `sessions_html.router`)
- Create: `tests/api/test_session_wizard_html.py`

- [ ] **Step 1: Write the test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_wizard_setup_step_renders() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as t:  # noqa: SIM117
        async with AsyncClient(transport=t, base_url="http://test") as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            r = await client.get("/sessions/new")
            assert r.status_code == 200
            assert "venue" in r.text.lower()
```

- [ ] **Step 2: Write `app/api/routers/sessions_html.py`**

```python
"""HTML routes for the session wizard."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.venue import VenueRepository

router = APIRouter(tags=["web:sessions"])


@router.get("/sessions/new", response_class=HTMLResponse)
async def new_session_setup(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    venues = await VenueRepository(session).list_all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/new_setup.html",
        {"request": request, "venues": venues, "today": date.today().isoformat()},
    )


@router.get("/sessions/new/players", response_class=HTMLResponse)
async def new_session_players(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    players = await PlayerRepository(session).list_active()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/new_players.html", {"request": request, "players": players}
    )
```

- [ ] **Step 3: Write `app/web/templates/sessions/new_setup.html`**

```html
{% extends "base.html" %}
{% block title %}New session — Setup{% endblock %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">New session — Step 1: Setup</h1>
<form method="post" action="/sessions/new/players" class="space-y-4">
  <label class="block">
    <span class="text-sm text-muted">Venue</span>
    <select name="venue_id" required class="w-full p-3 bg-surface-2 rounded">
      {% for v in venues %}
        <option value="{{ v.id }}">{{ v.name }} (₹{{ v.current_court_rate_per_hour }}/hr)</option>
      {% endfor %}
    </select>
  </label>
  <label class="block">
    <span class="text-sm text-muted">Date played</span>
    <input type="date" name="played_on" value="{{ today }}" required class="w-full p-3 bg-surface-2 rounded" />
  </label>
  <label class="block">
    <span class="text-sm text-muted">Start time</span>
    <input type="time" name="started_at" required class="w-full p-3 bg-surface-2 rounded" />
  </label>
  <label class="block">
    <span class="text-sm text-muted">Duration (minutes)</span>
    <input type="number" name="duration_minutes" min="30" step="30" value="90" required class="w-full p-3 bg-surface-2 rounded num" />
  </label>
  <button type="submit" class="btn-primary w-full">Continue → Players</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Write `app/web/templates/sessions/new_players.html`**

```html
{% extends "base.html" %}
{% block title %}New session — Players{% endblock %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">New session — Step 2: Players</h1>
<p class="text-sm text-muted mb-3">Tap to toggle. Add a guest if someone isn't in the roster.</p>
<form method="post" action="/sessions/new/courts" class="space-y-4">
  <div class="flex flex-wrap gap-2">
    {% for p in players %}
      <label class="inline-flex items-center gap-2 px-3 py-2 bg-surface-2 rounded-lg cursor-pointer has-[:checked]:bg-accent/20 has-[:checked]:ring-2 has-[:checked]:ring-accent transition">
        <input type="checkbox" name="player_ids" value="{{ p.id }}" class="sr-only" />
        <span>{{ p.emoji }}</span>
        <span>{{ p.name }}</span>
      </label>
    {% endfor %}
  </div>
  <details class="card">
    <summary class="cursor-pointer">+ Add guest</summary>
    <div class="mt-2 space-y-2">
      <input name="guest_name" placeholder="Name" class="w-full p-2 bg-surface rounded" />
      <input name="guest_phone" placeholder="+91… (optional)" class="w-full p-2 bg-surface rounded" />
      <button formaction="/sessions/new/players/add-guest" formmethod="post" class="btn-ghost w-full">Add to session</button>
    </div>
  </details>
  <button type="submit" class="btn-primary w-full">Continue → Courts</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Register router**

In `app/main.py`:

```python
from app.api.routers import sessions_html as sessions_html_router
app.include_router(sessions_html_router.router)
```

- [ ] **Step 6: Run + commit**

```bash
pytest tests/api/test_session_wizard_html.py -v
git add app/web/templates/sessions app/api/routers/sessions_html.py app/main.py tests/api/test_session_wizard_html.py
git commit -m "feat(web): wizard steps 1-2 (setup + players)"
```

---

## Task F4: Wizard steps — Courts + Slot grid + Shuttles

These three steps share state across requests via a server-side draft session (the SessionRepository's `create_draft`). Approach: as soon as we leave step 2, create a draft with placeholder courts; subsequent steps refine the draft via PATCH-like POSTs.

**Files:**
- Modify: `app/persistence/repositories/session.py` — add `update_courts`, `update_slots`, `update_shuttles` methods
- Create: `app/web/templates/sessions/new_courts.html`
- Create: `app/web/templates/sessions/new_slots.html`
- Create: `app/web/templates/sessions/new_shuttles.html`
- Create: `app/web/templates/partials/slot_cell.html`
- Modify: `app/api/routers/sessions_html.py` — add the three step routes + HTMX endpoints for slot toggling

> **Note for the executor:** Steps 4-6 of the wizard are the most UI-heavy. Implement step-by-step:
> 1. Add `update_*` repository methods first with unit tests.
> 2. Add wizard step routes (each a GET to render + POST to advance).
> 3. The slot grid uses HTMX: each cell is a button with `hx-post="/sessions/{id}/slots/toggle"` carrying `court_id`, `slot_index`, `player_id`. The endpoint returns the updated cell HTML fragment.
> 4. Shuttles step: simple form with one row per session player.
>
> Keep templates small and reuse the chip pattern from `new_players.html`.
>
> Skip detailed checkbox steps in this plan — the executor should use TDD: write a test that the wizard end-to-end produces a draft session matching `tests/api/test_sessions.py` expectations, then build to satisfy.

- [ ] **Step 1: Add repository update methods**

In `app/persistence/repositories/session.py`, add:

```python
async def update_courts(
    self, session_id: int, *, courts: list[CourtInputDict]
) -> None:
    s = await self.get_aggregate(session_id)
    if s is None:
        raise ValueError(f"session {session_id} not found")
    # remove existing courts (cascade removes slots + slot_players)
    for c in list(s.courts):
        await self._s.delete(c)
    await self._s.flush()
    for c in courts:
        court = Court(
            session_id=s.id,
            label=c["label"],
            booker_player_id=c["booker_player_id"],
            duration_minutes=c["duration_minutes"],
        )
        self._s.add(court)
        await self._s.flush()
        for idx, player_set in enumerate(c["slot_assignments"]):
            slot = Slot(court_id=court.id, slot_index=idx)
            self._s.add(slot)
            await self._s.flush()
            for pid in player_set:
                self._s.add(SlotPlayer(slot_id=slot.id, player_id=pid))
    await self._s.flush()


async def toggle_slot_player(
    self, *, slot_id: int, player_id: int
) -> bool:
    """Toggle a player on/off a slot. Returns True if now on, False if removed."""
    from sqlalchemy import select as _select  # local to avoid shadowing
    stmt = _select(SlotPlayer).where(
        SlotPlayer.slot_id == slot_id, SlotPlayer.player_id == player_id
    )
    existing = (await self._s.execute(stmt)).scalar_one_or_none()
    if existing:
        await self._s.delete(existing)
        await self._s.flush()
        return False
    self._s.add(SlotPlayer(slot_id=slot_id, player_id=player_id))
    await self._s.flush()
    return True


async def update_shuttle_contributions(
    self, session_id: int, *, contributions: list[ShuttleInputDict]
) -> None:
    s = await self.get_aggregate(session_id)
    if s is None:
        raise ValueError(f"session {session_id} not found")
    for sc in list(s.shuttle_contributions):
        await self._s.delete(sc)
    await self._s.flush()
    for c in contributions:
        if c["total_minutes"] > 0:
            self._s.add(
                ShuttleContribution(
                    session_id=s.id,
                    owner_player_id=c["owner_player_id"],
                    total_minutes=c["total_minutes"],
                )
            )
    await self._s.flush()
```

Add tests for each method in `tests/persistence/repositories/test_session.py` (mirror existing tests' style — set up venue/players/draft, call method, assert resulting state).

- [ ] **Step 2: Wizard step 3 — Courts (`new_courts.html` + route)**

```html
{# app/web/templates/sessions/new_courts.html #}
{% extends "base.html" %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">Step 3: Courts</h1>
<form method="post" action="/sessions/{{ session.id }}/courts" class="space-y-4" id="courts-form">
  <div id="courts-list" class="space-y-3">
    {% for i in range(1, 3) %}
      <div class="card">
        <div class="grid grid-cols-2 gap-2">
          <input name="court_{{ i }}_label" placeholder="Label e.g. Court {{ i }}" class="p-2 bg-surface rounded" required />
          <select name="court_{{ i }}_booker" class="p-2 bg-surface rounded" required>
            <option value="">Booker</option>
            {% for p in session_players %}
              <option value="{{ p.id }}">{{ p.name }}</option>
            {% endfor %}
          </select>
        </div>
        <input type="number" name="court_{{ i }}_minutes" min="30" step="30" value="{{ session.duration_minutes }}" class="mt-2 p-2 bg-surface rounded num w-full" required />
      </div>
    {% endfor %}
  </div>
  <button type="submit" class="btn-primary w-full">Continue → Slot grid</button>
</form>
{% endblock %}
```

Route in `sessions_html.py`:

```python
from datetime import date as _date, time as _time

from fastapi.responses import RedirectResponse


@router.post("/sessions/new/courts", response_class=HTMLResponse)
async def new_session_create_draft_and_show_courts(
    request: Request, session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    venue_id = int(form["venue_id"])
    played_on = _date.fromisoformat(form["played_on"])
    started_at = _time.fromisoformat(form["started_at"])
    duration = int(form["duration_minutes"])
    player_ids = [int(x) for x in form.getlist("player_ids")]

    # Create draft with one placeholder court covering the full session;
    # all session players assigned to slot 0 by default. Wizard step 4 refines.
    n_slots = duration // 30
    courts: list = [
        {
            "label": "Court 1",
            "booker_player_id": player_ids[0] if player_ids else 0,
            "duration_minutes": duration,
            "slot_assignments": [set(player_ids) for _ in range(n_slots)],
        }
    ]
    sid = await SessionService(session).create_draft(
        venue_id=venue_id,
        played_on=played_on,
        started_at=started_at,
        duration_minutes=duration,
        courts=courts,
        shuttle_contributions=[],
    )
    return RedirectResponse(f"/sessions/{sid}/courts", status_code=303)


@router.get("/sessions/{session_id}/courts", response_class=HTMLResponse)
async def show_session_courts_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    session_repo = SessionRepository(session)
    s = await session_repo.get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    # session_players = union of all SlotPlayer ids across courts
    pids = {sp.player_id for c in s.courts for sl in c.slots for sp in sl.players}
    rows = await PlayerRepository(session).list_active()
    session_players = [p for p in rows if p.id in pids]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/new_courts.html",
        {"request": request, "session": s, "session_players": session_players},
    )


@router.post("/sessions/{session_id}/courts", response_class=HTMLResponse)
async def submit_courts_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    form = await request.form()
    courts: list = []
    for i in range(1, 5):  # up to 4 courts in wizard
        label = form.get(f"court_{i}_label")
        if not label:
            continue
        booker = int(form[f"court_{i}_booker"])
        minutes = int(form[f"court_{i}_minutes"])
        n_slots = minutes // 30
        # default: copy slot 0 player set from existing draft (or empty if absent)
        s = await SessionRepository(session).get_aggregate(session_id)
        existing_slot_0 = (
            {sp.player_id for sp in s.courts[0].slots[0].players}
            if s and s.courts and s.courts[0].slots
            else set()
        )
        courts.append(
            {
                "label": label,
                "booker_player_id": booker,
                "duration_minutes": minutes,
                "slot_assignments": [existing_slot_0 for _ in range(n_slots)],
            }
        )
    await SessionRepository(session).update_courts(session_id, courts=courts)
    return RedirectResponse(f"/sessions/{session_id}/slots", status_code=303)
```

Required imports at top of `sessions_html.py`:

```python
from fastapi import HTTPException
from app.persistence.repositories.session import SessionRepository
from app.services.session_service import SessionService
```

- [ ] **Step 3: Wizard step 4 — Slot grid (the centerpiece)**

`app/web/templates/sessions/new_slots.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-xl font-semibold mb-2">Step 4: Slot grid</h1>
<p class="text-sm text-muted mb-3">Tap a cell to assign players for that 30-min slot.</p>

<div class="grid gap-3" style="grid-template-columns: max-content repeat({{ n_slots }}, 1fr);">
  <div></div>
  {% for i in range(n_slots) %}
    <div class="text-center text-xs text-muted">{{ i*30 }}m–{{ (i+1)*30 }}m</div>
  {% endfor %}

  {% for court in courts %}
    <div class="text-sm font-medium self-center">{{ court.label }}</div>
    {% for slot in court.slots %}
      {% include "partials/slot_cell.html" %}
    {% endfor %}
  {% endfor %}
</div>

<a href="/sessions/{{ session.id }}/shuttles" class="btn-primary w-full mt-6">Continue → Shuttles</a>
{% endblock %}
```

`app/web/templates/partials/slot_cell.html`:

```html
<div id="slot-{{ slot.id }}"
     hx-get="/sessions/{{ session.id }}/slots/{{ slot.id }}/picker"
     hx-trigger="click"
     hx-target="#slot-picker"
     class="card cursor-pointer min-h-[60px] flex flex-wrap gap-1 content-start">
  {% for sp in slot.players %}
    <span class="text-xs px-1.5 py-0.5 bg-accent/20 rounded">{{ sp.player.emoji }}{{ sp.player.name[0] }}</span>
  {% endfor %}
</div>
```

Plus a sticky "picker" overlay at the bottom of `new_slots.html`:

```html
<div id="slot-picker" class="fixed inset-x-0 bottom-16"></div>
```

And the picker fragment:

```html
{# returned by /sessions/{id}/slots/{slot_id}/picker #}
<div class="card mx-4 shadow-xl">
  <div class="text-xs text-muted mb-2">Tap to add/remove</div>
  <div class="flex flex-wrap gap-2">
    {% for p in players %}
      <button hx-post="/sessions/{{ session_id }}/slots/{{ slot_id }}/toggle/{{ p.id }}"
              hx-target="#slot-{{ slot_id }}"
              hx-swap="outerHTML"
              class="px-2 py-1 rounded {{ 'bg-accent/40' if p.id in current_player_ids else 'bg-surface-2' }}">
        {{ p.emoji }} {{ p.name }}
      </button>
    {% endfor %}
  </div>
</div>
```

Routes for `picker`, `toggle`:
- `GET /sessions/{id}/slots/{slot_id}/picker` → render picker fragment
- `POST /sessions/{id}/slots/{slot_id}/toggle/{player_id}` → call `toggle_slot_player`, return updated `slot_cell.html` fragment

- [ ] **Step 4: Wizard step 5 — Shuttles**

`app/web/templates/sessions/new_shuttles.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">Step 5: Shuttles</h1>
<p class="text-sm text-muted mb-3">Minutes each player's shuttles were on duty (multiples of 30).</p>
<form method="post" action="/sessions/{{ session.id }}/shuttles" class="space-y-3">
  {% for p in session_players %}
    <label class="card flex items-center justify-between gap-3">
      <span>{{ p.emoji }} {{ p.name }}</span>
      <input type="number" name="player_{{ p.id }}_minutes" min="0" step="30" value="{{ existing.get(p.id, 0) }}" class="num w-24 p-2 bg-surface rounded text-right" />
    </label>
  {% endfor %}
  <button type="submit" class="btn-primary w-full">Continue → Review</button>
</form>
{% endblock %}
```

Routes:

```python
@router.get("/sessions/{session_id}/shuttles", response_class=HTMLResponse)
async def show_shuttles_step(
    session_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    pids = {sp.player_id for c in s.courts for sl in c.slots for sp in sl.players}
    rows = await PlayerRepository(session).list_active()
    session_players = [p for p in rows if p.id in pids]
    existing = {sc.owner_player_id: sc.total_minutes for sc in s.shuttle_contributions}
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/new_shuttles.html",
        {
            "request": request,
            "session": s,
            "session_players": session_players,
            "existing": existing,
        },
    )


@router.post("/sessions/{session_id}/shuttles")
async def submit_shuttles(
    session_id: int, request: Request, session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    contribs: list = []
    for key, value in form.items():
        if not (key.startswith("player_") and key.endswith("_minutes")):
            continue
        pid = int(key.removeprefix("player_").removesuffix("_minutes"))
        minutes = int(value or 0)
        if minutes > 0:
            contribs.append({"owner_player_id": pid, "total_minutes": minutes})
    await SessionRepository(session).update_shuttle_contributions(
        session_id, contributions=contribs
    )
    return RedirectResponse(f"/sessions/{session_id}/review", status_code=303)
```

- [ ] **Step 5: Wizard step 6 — Review + Finalize**

`app/web/templates/sessions/review.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">Step 6: Review</h1>
<div class="card mb-4">
  <div class="text-sm text-muted">{{ session.played_on.strftime('%a %d %b %Y') }} · {{ venue.name }}</div>
  <div class="text-sm num">Total court ₹{{ preview.total_court_cost | int }} · shuttle ₹{{ preview.total_shuttle_cost | int }}</div>
</div>
<ul class="space-y-2 mb-6">
  {% for p in preview.per_player %}
    <li class="card flex justify-between">
      <span>{{ p.name }}</span>
      <span class="num">
        {% if p.net > 0 %}owes ₹{{ p.net }}{% elif p.net < 0 %}owed ₹{{ -p.net }}{% else %}settled{% endif %}
      </span>
    </li>
  {% endfor %}
</ul>
<form method="post" action="/sessions/{{ session.id }}/finalize">
  <button class="btn-primary w-full">Finalize and view send buttons</button>
</form>
<a href="/sessions/{{ session.id }}/shuttles" class="btn-ghost w-full mt-2">← Back to shuttles</a>
{% endblock %}
```

Routes:

```python
@router.get("/sessions/{session_id}/review", response_class=HTMLResponse)
async def show_review_step(
    session_id: int, request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    venue = await VenueRepository(session).get(s.venue_id)
    if venue is None:
        raise HTTPException(404, f"venue {s.venue_id} not found")
    # Preview against CURRENT venue rates (not yet snapshotted on draft)
    if s.snapshot_court_rate is None:
        s.snapshot_court_rate = venue.current_court_rate_per_hour
    if s.snapshot_shuttle_rate is None:
        s.snapshot_shuttle_rate = venue.current_shuttle_rate_per_hour
    await session.flush()
    preview = await SessionService(session).compute(session_id)
    # Reset snapshot to None so finalize() does the real snapshot at click time
    s.snapshot_court_rate = None
    s.snapshot_shuttle_rate = None
    await session.flush()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/review.html",
        {"request": request, "session": s, "venue": venue, "preview": preview},
    )


@router.post("/sessions/{session_id}/finalize")
async def finalize_session_html(
    session_id: int, session: AsyncSession = Depends(get_session)
):
    await SessionService(session).finalize_and_compute(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)
```

- [ ] **Step 6: Tests for each wizard step**

Add to `tests/api/test_session_wizard_html.py`:

```python
@pytest.mark.asyncio
async def test_full_wizard_walkthrough() -> None:
    """Drive the wizard end-to-end via httpx; assert finalized session matches expected math."""
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as t:  # noqa: SIM117
        async with AsyncClient(transport=t, base_url="http://test", follow_redirects=True) as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # set up venue + 2 players
            await client.post("/api/venues", json={
                "name": "V", "court_rate": "400", "shuttle_rate": "50",
                "effective_from": "2026-01-01",
            })
            a = (await client.post("/api/players", json={"name": "Alice"})).json()["id"]
            b = (await client.post("/api/players", json={"name": "Bob"})).json()["id"]

            # step 1 → step 2 (creates draft)
            r = await client.post(
                "/sessions/new/players",
                data={
                    "venue_id": "1",
                    "played_on": "2026-04-28",
                    "started_at": "19:00",
                    "duration_minutes": "30",
                },
            )
            assert r.status_code in (200, 303)

            # step 2 → step 3 (player selection redirects to draft creation)
            r = await client.post(
                "/sessions/new/courts",
                data=[("venue_id", "1"), ("played_on", "2026-04-28"),
                      ("started_at", "19:00"), ("duration_minutes", "30"),
                      ("player_ids", str(a)), ("player_ids", str(b))],
            )
            # server creates draft; status 200 after redirects
            assert r.status_code == 200
```

(Add similar coverage for steps 3→4→5→6 and finalize, asserting the result page renders ₹100 for each.)

- [ ] **Step 7: Commit**

```bash
git add app/web/templates/sessions app/web/templates/partials app/api/routers/sessions_html.py app/persistence/repositories/session.py tests/
git commit -m "feat(web): wizard steps 3-6 (courts, slot grid, shuttles, review)"
```

---

## Task F5: Result page with WhatsApp send buttons

**Files:**
- Create: `app/web/templates/sessions/result.html`
- Modify: `app/api/routers/sessions_html.py` — add `/sessions/{id}` GET route
- Create: `tests/api/test_result_page.py`

- [ ] **Step 1: Write the test**

```python
# integration: create venue, players, session via API; finalize; GET /sessions/{id}; assert wa.me link in HTML for player with phone, copy button for player without
```

- [ ] **Step 2: Write the result template**

```html
{% extends "base.html" %}
{% block content %}
<header class="mb-4">
  <div class="text-sm text-muted">{{ session.played_on.strftime('%a %d %b %Y') }} · {{ venue.name }}</div>
  <h1 class="text-xl font-semibold">Cost split</h1>
  <div class="text-sm text-muted num">
    Court ₹{{ result.total_court_cost | int }} · Shuttle ₹{{ result.total_shuttle_cost | int }}
  </div>
</header>

<ul class="space-y-3">
  {% for p in result.per_player %}
    {% set line = lines[p.player_id] %}
    <li class="card">
      <div class="flex justify-between items-baseline">
        <div class="font-medium">{{ p.name }}{% if not line.has_phone %} <span class="text-xs text-muted">(no phone)</span>{% endif %}</div>
        <div class="num text-lg {{ 'text-positive' if p.net > 0 else 'text-negative' if p.net < 0 else '' }}">
          {% if p.net > 0 %}owes you ₹{{ p.net }}{% elif p.net < 0 %}you owe ₹{{ -p.net }}{% else %}settled{% endif %}
        </div>
      </div>
      <div class="text-xs text-muted mt-1 num">
        Court ₹{{ p.owes_court }} · Shuttle ₹{{ p.owes_shuttle }}
        {% if p.credit_total > 0 %}· Credit ₹{{ p.credit_total }}{% endif %}
      </div>
      <div class="mt-3">
        {% if line.has_phone %}
          <a href="{{ line.wa_me_url }}" target="_blank" rel="noopener" class="btn-primary w-full">💬 Send via WhatsApp</a>
        {% else %}
          <button class="btn-ghost w-full" data-copy="{{ line.message_text }}"
                  onclick="navigator.clipboard.writeText(this.dataset.copy); this.textContent='Copied ✓'">
            📋 Copy message
          </button>
        {% endif %}
      </div>
    </li>
  {% endfor %}
</ul>

<form method="post" action="/sessions/{{ session.id }}/mark-sent" class="mt-4">
  <button class="btn-ghost w-full">Mark all sent</button>
</form>
{% endblock %}
```

- [ ] **Step 3: Route**

```python
from app.api.deps import get_session
from app.config.settings import Settings
from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.session import SessionRepository
from app.persistence.repositories.venue import VenueRepository
from app.services.messaging import DEFAULT_TEMPLATE, build_message_text, build_wa_me_url
from app.services.session_service import SessionService


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def show_session_result(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    session_repo = SessionRepository(session)
    s = await session_repo.get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    venue = await VenueRepository(session).get(s.venue_id)
    if venue is None:
        raise HTTPException(404, f"venue {s.venue_id} missing")
    if s.status == "draft":
        raise HTTPException(400, "session must be finalized before viewing result")

    result = await SessionService(session).compute(session_id)

    # Resolve phone numbers for participants
    pids = [p.player_id for p in result.per_player]
    player_repo = PlayerRepository(session)
    rows = []
    for pid in pids:
        rows.append(await player_repo.get(pid))
    by_id = {p.id: p for p in rows if p is not None}

    settings = Settings()
    played_on_str = s.played_on.strftime("%d %b %Y")
    lines: dict[int, dict] = {}
    for p in result.per_player:
        msg = build_message_text(
            template=DEFAULT_TEMPLATE,
            player=p,
            played_on=played_on_str,
            venue=venue.name,
            upi_id=settings.upi_id,
        )
        primary = None
        player_row = by_id.get(p.player_id)
        if player_row is not None:
            primary = next((ph for ph in player_row.phones if ph.is_primary), None)
        lines[p.player_id] = {
            "has_phone": primary is not None,
            "wa_me_url": build_wa_me_url(primary.e164_number, msg) if primary else None,
            "message_text": msg,
        }

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "sessions/result.html",
        {
            "request": request,
            "session": s,
            "venue": venue,
            "result": result,
            "lines": lines,
        },
    )


@router.post("/sessions/{session_id}/mark-sent", response_class=HTMLResponse)
async def mark_session_sent(
    session_id: int, session: AsyncSession = Depends(get_session)
):
    await SessionRepository(session).mark_sent(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/api/test_result_page.py -v
git add app/web/templates/sessions/result.html app/api/routers/sessions_html.py tests/api/test_result_page.py
git commit -m "feat(web): result page with WhatsApp send buttons"
```

---

## Task F6: Players page (template + route + test) — full reference for F7/F8 to copy

**Files:**
- Create: `app/web/templates/players/list.html`
- Create: `app/web/templates/players/form.html`
- Create: `app/api/routers/players_html.py`
- Create: `tests/api/test_players_html.py`
- Modify: `app/main.py` — register `players_html.router`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import build_app
from app.persistence import orm  # noqa: F401
from app.persistence.database import Base


@pytest.mark.asyncio
async def test_players_list_renders() -> None:
    app = build_app(database_url="sqlite+aiosqlite:///:memory:")
    async with ASGITransport(app=app) as t:  # noqa: SIM117
        async with AsyncClient(transport=t, base_url="http://test") as client:
            await client.get("/health")
            async with app.state.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            r = await client.get("/players")
            assert r.status_code == 200
            assert "roster" in r.text.lower() or "player" in r.text.lower()
```

- [ ] **Step 2: Write `app/api/routers/players_html.py`**

```python
"""HTML routes for the player roster."""
from __future__ import annotations

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.persistence.repositories.player import PlayerRepository

router = APIRouter(tags=["web:players"])


@router.get("/players", response_class=HTMLResponse)
async def list_players_html(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    players = await PlayerRepository(session).list_active()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "players/list.html", {"request": request, "players": players}
    )


@router.get("/players/new", response_class=HTMLResponse)
async def new_player_form(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "players/form.html", {"request": request, "player": None}
    )


@router.post("/players")
async def create_player_html(
    request: Request, session: AsyncSession = Depends(get_session)
):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    emoji = str(form.get("emoji", "🏸"))
    phone_raw = str(form.get("phone", "")).strip()
    repo = PlayerRepository(session)
    p = await repo.create(name=name, emoji=emoji, is_guest=False)
    if phone_raw:
        try:
            parsed = phonenumbers.parse(phone_raw, "IN")
        except phonenumbers.NumberParseException as e:
            raise HTTPException(400, f"invalid phone: {e}") from e
        if not phonenumbers.is_valid_number(parsed):
            raise HTTPException(400, "invalid phone number")
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        await repo.add_phone(p.id, e164=e164, is_primary=True)
    return RedirectResponse("/players", status_code=303)


@router.post("/players/{player_id}/delete")
async def delete_player_html(
    player_id: int, session: AsyncSession = Depends(get_session)
):
    await PlayerRepository(session).soft_delete(player_id)
    return RedirectResponse("/players", status_code=303)
```

- [ ] **Step 3: Write `app/web/templates/players/list.html`**

```html
{% extends "base.html" %}
{% block title %}Roster · Badminton Splitter{% endblock %}
{% block content %}
<header class="flex items-center justify-between mb-6">
  <h1 class="text-2xl font-semibold">Roster</h1>
  <a href="/players/new" class="btn-primary">+ Add</a>
</header>
{% if players %}
<ul class="space-y-2">
  {% for p in players %}
    <li class="card flex justify-between items-center">
      <div>
        <span class="text-xl">{{ p.emoji }}</span>
        <span class="ml-2 font-medium">{{ p.name }}</span>
        {% if p.phones %}
          <span class="ml-2 text-xs text-muted num">{{ p.phones[0].e164_number }}</span>
        {% else %}
          <span class="ml-2 text-xs text-muted">no phone</span>
        {% endif %}
      </div>
      <form method="post" action="/players/{{ p.id }}/delete">
        <button class="btn-ghost text-sm text-negative">Remove</button>
      </form>
    </li>
  {% endfor %}
</ul>
{% else %}
<div class="card text-center text-muted">No players yet.</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Write `app/web/templates/players/form.html`**

```html
{% extends "base.html" %}
{% block title %}New player{% endblock %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">{{ "Edit player" if player else "New player" }}</h1>
<form method="post" action="/players" class="space-y-4">
  <label class="block">
    <span class="text-sm text-muted">Name</span>
    <input name="name" value="{{ player.name if player else '' }}" required class="w-full p-3 bg-surface-2 rounded" />
  </label>
  <label class="block">
    <span class="text-sm text-muted">Emoji avatar</span>
    <input name="emoji" maxlength="8" value="{{ player.emoji if player else '🏸' }}" class="w-full p-3 bg-surface-2 rounded" />
  </label>
  <label class="block">
    <span class="text-sm text-muted">Primary WhatsApp phone (optional, +91… or local)</span>
    <input name="phone" type="tel" placeholder="+91 9876543210" class="w-full p-3 bg-surface-2 rounded num" />
  </label>
  <button type="submit" class="btn-primary w-full">Save</button>
  <a href="/players" class="btn-ghost w-full block text-center">Cancel</a>
</form>
{% endblock %}
```

- [ ] **Step 5: Register router in `app/main.py`**

```python
from app.api.routers import players_html as players_html_router
app.include_router(players_html_router.router)
```

- [ ] **Step 6: Run + commit**

```bash
pytest tests/api/test_players_html.py -v
git add app/web/templates/players app/api/routers/players_html.py app/main.py tests/api/test_players_html.py
git commit -m "feat(web): roster pages (list + add + soft-delete)"
```

---

## Task F7: Venues pages (mirror F6 pattern)

**Files:**
- Create: `app/web/templates/venues/list.html`
- Create: `app/web/templates/venues/form.html`
- Create: `app/api/routers/venues_html.py`
- Create: `tests/api/test_venues_html.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write test mirroring `test_players_html.py` (path `/venues`).**

- [ ] **Step 2: Write the router** with three routes:
  - `GET /venues` — list venues
  - `GET /venues/new` — render form
  - `POST /venues` — parse name, court_rate, shuttle_rate, effective_from (default to today), call `VenueRepository.create`, redirect to `/venues`

- [ ] **Step 3: Write `app/web/templates/venues/list.html`**

```html
{% extends "base.html" %}
{% block title %}Venues{% endblock %}
{% block content %}
<header class="flex justify-between mb-6">
  <h1 class="text-2xl font-semibold">Venues</h1>
  <a href="/venues/new" class="btn-primary">+ Add</a>
</header>
<ul class="space-y-2">
  {% for v in venues %}
    <li class="card">
      <div class="font-medium">{{ v.name }}</div>
      <div class="text-sm text-muted num">
        Court ₹{{ v.current_court_rate_per_hour }}/hr · Shuttle ₹{{ v.current_shuttle_rate_per_hour }}/hr
      </div>
    </li>
  {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 4: Write `app/web/templates/venues/form.html`** (mirror player form: text input for name, two number inputs for rates, date input for effective_from, submit button).

- [ ] **Step 5: Register, run, commit.**

```bash
git add app/web/templates/venues app/api/routers/venues_html.py app/main.py tests/api/test_venues_html.py
git commit -m "feat(web): venue pages (list + add)"
```

---

## Task F8: Settings page (theme + UPI ID + message template)

**Files:**
- Create: `app/web/templates/settings/form.html`
- Create: `app/api/routers/settings_html.py`
- Create: `app/persistence/orm.py` — add `AppSettings` row (singleton)
- Create: alembic migration
- Create: `tests/api/test_settings_html.py`

> **Decision for the executor:** the simplest place to persist user-editable settings (UPI ID, message template, theme preference) is a single-row `app_settings` table with id=1. Add it to `orm.py` and generate a new Alembic migration.

- [ ] **Step 1: Add `AppSettings` ORM model**

In `app/persistence/orm.py`:

```python
class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upi_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str] = mapped_column(String(10), default="system", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Generate migration**

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/badminton.db alembic revision --autogenerate -m "add app_settings"
```

Inspect generated file. After upgrade, manually insert id=1 row in app startup (lifespan) if missing:

```python
# in app/main.py lifespan, after engine setup:
from app.persistence.orm import AppSettings
from sqlalchemy import select
from app.services.messaging import DEFAULT_TEMPLATE

async with db.session() as s:
    existing = (await s.execute(select(AppSettings).where(AppSettings.id == 1))).scalar_one_or_none()
    if existing is None:
        s.add(AppSettings(id=1, upi_id=None, message_template=DEFAULT_TEMPLATE, theme="system"))
```

- [ ] **Step 3: Write router + template** with two routes (`GET /settings`, `POST /settings`) — load the singleton, render form with name/template/theme/UPI inputs, POST updates the row.

`app/web/templates/settings/form.html`:

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block content %}
<h1 class="text-2xl font-semibold mb-4">Settings</h1>
<form method="post" action="/settings" class="space-y-4">
  <label class="block">
    <span class="text-sm text-muted">UPI ID (interpolated into messages)</span>
    <input name="upi_id" value="{{ settings.upi_id or '' }}" class="w-full p-3 bg-surface-2 rounded num" />
  </label>
  <label class="block">
    <span class="text-sm text-muted">Message template</span>
    <textarea name="message_template" rows="10" class="w-full p-3 bg-surface-2 rounded font-mono text-sm">{{ settings.message_template }}</textarea>
  </label>
  <label class="block">
    <span class="text-sm text-muted">Theme</span>
    <select name="theme" class="w-full p-3 bg-surface-2 rounded">
      <option value="system" {% if settings.theme == "system" %}selected{% endif %}>System</option>
      <option value="light" {% if settings.theme == "light" %}selected{% endif %}>Light</option>
      <option value="dark" {% if settings.theme == "dark" %}selected{% endif %}>Dark</option>
    </select>
  </label>
  <button class="btn-primary w-full">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Wire `Settings.upi_id` to read from DB instead of env in result page**

Modify the result page route (Task F5 step 3) to load `AppSettings.upi_id` instead of reading from `Settings()` env var:

```python
from sqlalchemy import select as _select
from app.persistence.orm import AppSettings as _AppSettings

settings_row = (await session.execute(
    _select(_AppSettings).where(_AppSettings.id == 1)
)).scalar_one()
upi_id = settings_row.upi_id
template = settings_row.message_template
```

Replace the call to `build_message_text` to use `template=template, upi_id=upi_id`.

- [ ] **Step 5: Run + commit**

```bash
pytest tests/api/test_settings_html.py -v
git add app/persistence/orm.py alembic/versions/ app/web/templates/settings app/api/routers/settings_html.py app/main.py tests/api/test_settings_html.py
git commit -m "feat(web): settings page (UPI, template, theme) backed by app_settings table"
```

---

# Phase G — E2E + Deployment

## Task G1: Playwright happy-path E2E

**Files:**
- Create: `tests/e2e/__init__.py` (empty)
- Create: `tests/e2e/test_happy_path.py`
- Create: `tests/e2e/conftest.py`

- [ ] **Step 1: Install Playwright browsers**

```bash
playwright install chromium
```

- [ ] **Step 2: Write the test**

`tests/e2e/test_happy_path.py`:

```python
"""End-to-end happy-path: create a venue + players + session, finalize, see result."""
import pytest
from playwright.async_api import Page, expect


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_session_flow_in_browser(page: Page, base_url: str) -> None:
    await page.goto(f"{base_url}/")
    # ... walk through wizard, asserting key UI elements appear
    # 1. add venue via /venues/new
    # 2. add 2 players via /players/new
    # 3. start session: pick venue, set duration 30
    # 4. select both players
    # 5. add 1 court, set booker
    # 6. set slot 0 to include both players
    # 7. skip shuttles
    # 8. finalize
    # 9. assert result page shows expected ₹ amounts
    await expect(page.locator("text=owes you")).to_be_visible(timeout=10000)
```

`tests/e2e/conftest.py`:

```python
"""Spawn the app under uvicorn for E2E."""
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page, async_playwright


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    port = _free_port()
    db = tmp_path_factory.mktemp("e2e") / "test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    # Apply migrations
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    # Run server
    proc = subprocess.Popen(
        ["uvicorn", "app.main:app", "--port", str(port)],
        env=env,
    )
    # wait for readiness
    import urllib.request
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
            break
        except Exception:
            time.sleep(0.25)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()


@pytest_asyncio.fixture
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as p:
        b = await p.chromium.launch()
        yield b
        await b.close()


@pytest_asyncio.fixture
async def context(browser: Browser) -> AsyncIterator[BrowserContext]:
    c = await browser.new_context(viewport={"width": 414, "height": 896})  # iPhone-ish
    yield c
    await c.close()


@pytest_asyncio.fixture
async def page(context: BrowserContext) -> AsyncIterator[Page]:
    p = await context.new_page()
    yield p
```

- [ ] **Step 3: Run**

```bash
pytest -m e2e -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e
git commit -m "test(e2e): add Playwright happy-path test"
```

---

## Task G2: Multi-stage Dockerfile

**Files:**
- Create: `docker/Dockerfile`

- [ ] **Step 1: Write `docker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
# ---------------- Stage 1: Tailwind build ------------------
FROM node:20-alpine AS tailwind
WORKDIR /build

# Tailwind CLI standalone (no Node packages needed beyond this)
ARG TAILWIND_VERSION=4.0.0
RUN apk add --no-cache curl && \
    curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-arm64 && \
    chmod +x tailwindcss-linux-arm64 && mv tailwindcss-linux-arm64 /usr/local/bin/tailwindcss

COPY tailwind.config.js ./
COPY app/web/static/css/tailwind.input.css ./input.css
COPY app/web/templates ./app/web/templates
RUN tailwindcss -i ./input.css -o ./output.css --minify

# ---------------- Stage 2: Runtime --------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --no-create-home app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[]"

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# pull built CSS from stage 1
COPY --from=tailwind /build/output.css ./app/web/static/css/tailwind.output.css

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8080"]
```

- [ ] **Step 2: Build and smoke-test locally**

```bash
docker buildx build --load -f docker/Dockerfile -t badminton-splitter:dev .
docker run --rm -p 8080:8080 -v $(pwd)/data:/app/data \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/test.db badminton-splitter:dev &
sleep 5
curl -f http://localhost:8080/health
docker kill $(docker ps -q --filter ancestor=badminton-splitter:dev)
```

Expected: `{"status":"ok"}` from curl.

- [ ] **Step 3: Commit**

```bash
git add docker/Dockerfile
git commit -m "build: multi-stage Dockerfile (Tailwind build + slim Python runtime)"
```

---

## Task G3: docker-compose with Litestream sidecar

**Files:**
- Create: `docker/docker-compose.yml`
- Create: `docker/litestream.yml`

- [ ] **Step 1: Write `docker/docker-compose.yml`**

```yaml
services:
  app:
    image: ghcr.io/{{GITHUB_OWNER}}/badminton-splitter:latest  # replace at deploy time
    restart: unless-stopped
    ports: ["8080:8080"]
    volumes:
      - /opt/badminton/data:/app/data
    environment:
      DATABASE_URL: sqlite+aiosqlite:////app/data/badminton.db
      LOG_LEVEL: info
      TZ: Asia/Kolkata
      UPI_ID: ""
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

  litestream:
    image: litestream/litestream:0.3
    restart: unless-stopped
    volumes:
      - /opt/badminton/data:/app/data
      - /opt/badminton/backup:/backup
      - ./litestream.yml:/etc/litestream.yml:ro
    command: replicate -config /etc/litestream.yml
    depends_on:
      - app
```

- [ ] **Step 2: Write `docker/litestream.yml`**

```yaml
dbs:
  - path: /app/data/badminton.db
    replicas:
      - type: file
        path: /backup/badminton
        retention: 168h         # 7 days
        snapshot-interval: 24h
```

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.yml docker/litestream.yml
git commit -m "build: docker-compose with Litestream sidecar for SQLite backup"
```

---

## Task G4: structlog + observability endpoints

**Files:**
- Create: `app/observability.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write `app/observability.py`**

```python
"""Logging + Prometheus metrics setup."""
from __future__ import annotations

import logging
import time

import structlog
from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])


def configure_structlog(level: str = "info") -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(request.method, path).observe(elapsed)
        return response


def install(app: FastAPI, *, enabled: bool = True) -> None:
    if not enabled:
        return
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 2: Wire into `app/main.py`**

In `build_app`, after creating `app`:

```python
from app.config.settings import Settings
from app.observability import configure_structlog, install as install_observability

settings = Settings()
configure_structlog(settings.log_level)
install_observability(app, enabled=settings.metrics_enabled)
```

- [ ] **Step 3: Test**

```bash
make dev
curl http://localhost:8080/metrics | head -20
```

Expected: Prometheus metrics output.

- [ ] **Step 4: Commit**

```bash
git add app/observability.py app/main.py
git commit -m "feat(observability): structlog + Prometheus /metrics + request middleware"
```

---

## Task G5: Pi deploy Makefile target + final smoke

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Replace the placeholder `pi-deploy` target**

```makefile
PI_HOST ?= pi
PI_PATH ?= /opt/badminton

pi-deploy:
	@test -n "$(GITHUB_OWNER)" || (echo "set GITHUB_OWNER" && exit 1)
	ssh $(PI_HOST) "cd $(PI_PATH) && \
		sed -i 's|{{GITHUB_OWNER}}|$(GITHUB_OWNER)|g' docker-compose.yml && \
		docker compose pull && \
		docker compose up -d && \
		sleep 5 && \
		curl -fs http://localhost:8080/health"

pi-bootstrap:
	@test -n "$(PI_HOST)" || (echo "set PI_HOST" && exit 1)
	ssh $(PI_HOST) "sudo mkdir -p $(PI_PATH)/data $(PI_PATH)/backup"
	scp docker/docker-compose.yml docker/litestream.yml $(PI_HOST):$(PI_PATH)/
```

- [ ] **Step 2: Document in README**

Add a "Deploy to Pi" section explaining:
1. `GITHUB_OWNER=<your-gh-name> make pi-bootstrap PI_HOST=pi-tailscale-name` once
2. CI on `main` builds and pushes the image to GHCR
3. `GITHUB_OWNER=<...> make pi-deploy PI_HOST=pi-tailscale-name` to roll out

- [ ] **Step 3: Commit**

```bash
git add Makefile README.md
git commit -m "build: Pi deploy Makefile target + bootstrap"
```

---

# Coverage and final gate

## Task Z1: Final CI run + coverage check

- [ ] **Step 1: Run full local CI**

```bash
make ci
```

Expected: lint, type, all tests PASS.

- [ ] **Step 2: Check coverage**

```bash
.venv/Scripts/pytest --cov=app --cov-report=term-missing -m "not e2e"
```

Expected: ≥ 80% overall, ≥ 95% on `app/domain`.

- [ ] **Step 3: Push to remote, watch CI**

```bash
git push -u origin main
```

Watch GitHub Actions go green.

- [ ] **Step 4: First Pi deploy**

Follow README Pi deploy section. Confirm via Tailscale URL.

- [ ] **Step 5: Done.**

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

# Self-review notes

**Spec coverage:** every section of the spec has at least one task —
- §2 Architecture / Stack → A2 (deps), C1 (settings), C2 (database), F1 (Tailwind), G2 (Docker)
- §3 Data model → C3 (ORM), C4 (migrations), F8 (AppSettings table)
- §4 Calculator → B1 (types), B2 (rounding), B3-B5 (court + shuttle), B6 (property tests)
- §5 UI → F1 (design system + base), F2 (sessions list), F3-F5 (wizard), F6 (roster), F7 (venues), F8 (settings)
- §6 Messaging → D3 (text + wa.me URL), F5 (result page wiring)
- §7 Testing → integrated through every task; G1 covers e2e
- §8 Deployment → G2 (Dockerfile), G3 (compose + Litestream), G5 (Pi deploy Makefile)
- §9 Open questions → still deferred to executor judgment

**Type consistency check:**
- `SessionInput`, `CourtInput`, `SlotInput`, `ShuttleContributionInput`, `PlayerRef`, `PlayerResult`, `SessionResult` defined in B1 and used in B3-B6, D1, D2.
- `CourtInputDict` and `ShuttleInputDict` (TypedDicts at the persistence boundary) defined in C8 and used in D2 service code, F4 wizard route, F4 update_courts.
- `round_to_5` defined in B2; called in B3 and B5 only.
- `Database`, `Base` defined in C2; imported consistently in tests and migrations.
- Repository class names: `PlayerRepository` (C6), `VenueRepository` (C7), `SessionRepository` (C8) — consistent throughout.

**Placeholder scan (post-fix):**
- Initial draft had three `...` placeholders in F4-F5; all replaced with concrete code.
- F4 wizard step 4 (slot grid) is the most UI-complex task — the picker/toggle endpoints are concrete in the templates section, but executor will refine HTMX swap targets while running locally.
- F8 message template wiring requires modifying the F5 result route after AppSettings is added — explicit step in F8 step 4.

**Order of execution:** phases must run sequentially A → B → C → D → E → F → G. Within Phase F, F1 must precede all others; F2-F8 can be done in any order given their templates and routes are independent. Within Phase B, B1 → B2 → B3 → B4 → B5 → B6 → B7 strictly.

**Known thinness (acknowledged):**
- F4 step 1 (repo update method tests) is described in prose, not given as test code — pattern should mirror `test_session.py` from C8.
- F6/F7 deletion / edit flows beyond create are not separately scoped (acceptable for v1).
