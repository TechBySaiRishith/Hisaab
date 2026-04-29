# Badminton Splitter — Design Spec

**Date:** 2026-04-29
**Status:** Approved (pending written review)
**Scope:** v1 — single-user personal app for computing per-player cost shares from a badminton session and dispatching payment requests via WhatsApp.

---

## 1. Goals and non-goals

### Goals

- Eliminate the manual math the user does after every session.
- Compute each player's share of court + shuttle cost, accounting for:
  - **Multiple courts per session**, each booked by a (potentially different) player.
  - **Variable durations** in 30-minute slots, with players swapping in and out across slots.
  - **Shared shuttles** brought by multiple players, billed at a per-hour rate, credited to the owner.
- Generate a personalised WhatsApp message per player and a one-tap launch into a `wa.me` chat (no message is auto-sent — user taps "send" in WhatsApp).
- Handle players whose phone numbers are not stored — present a copyable message instead of a link.
- Round each player's amounts to the nearest ₹5.
- Run on the user's Raspberry Pi (ARM64), accessible over Tailscale from anywhere on the user's tailnet.
- Be **production-grade**: typed code, tests, migrations, structured logs, CI.
- Have a **polished UI**: real design system, dark mode, mobile-first layout.

### Non-goals (v1)

- Multi-user accounts, login, role-based access. Tailscale is the security perimeter.
- Automated WhatsApp send via API (Twilio / Cloud API / `whatsapp-web.js`). The user explicitly chose `wa.me` link generation only.
- Public internet exposure / SSL termination — Tailscale handles that.
- Payment integration (UPI deep links beyond plain text in the message body, no payment status reconciliation).
- Multi-currency.
- Recurring / scheduled sessions.
- Offline-first / PWA. The user has connectivity when settling up.

---

## 2. Architecture

### Stack

- **Backend:** FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 (async), Alembic migrations, SQLite.
- **Frontend:** Server-rendered Jinja2 templates + HTMX for interactivity; Tailwind CSS v4 (built once at image build via standalone CLI — no Node at runtime); Lucide icons; Inter + JetBrains Mono fonts; OKLCH-based design tokens.
- **Server:** uvicorn under a single Docker container.
- **Storage:** SQLite file on a Docker volume; Litestream sidecar replicates the WAL to a backup directory.
- **Logging:** structlog → JSON to stdout.
- **Quality:** ruff (lint+format), mypy strict on `domain/` and `services/`, pytest + Hypothesis property tests, pre-commit, GitHub Actions CI.

### Layered structure

```
app/
├── domain/         # Pure Python. No I/O, no framework. Business types + calculator.
├── persistence/    # SQLAlchemy ORM models + Alembic migrations + repositories.
├── services/       # Orchestration. Transactions live here.
├── api/            # FastAPI routers + Pydantic schemas. Thin.
├── web/            # Jinja2 templates + HTMX partials + static CSS.
└── config/         # Pydantic Settings (env-driven).
```

The calculator (`domain/calculator.py`) is a pure function that takes a fully-loaded session aggregate and returns a result object. This is what carries the business invariants and is what gets the heaviest test coverage (Hypothesis property tests in addition to unit tests).

### Runtime topology

```
Phone (Tailscale) ──► Pi:8080 ──► Docker container (FastAPI + uvicorn)
                                          │
                                          ▼
                                   /data/badminton.db (SQLite, mounted volume)
                                          │
                                          ▼
                                   Litestream sidecar ──► /backup/*.db.wal
```

---

## 3. Data model

### Entities

**Player**
- `id` (PK), `name`, `emoji` (avatar), `is_guest` (bool), `is_active` (bool), `deleted_at` (nullable, soft-delete), `created_at`, `updated_at`.

**PlayerPhone** (one-to-many from Player)
- `id`, `player_id` (FK), `country_code` (default `IN`), `e164_number`, `is_primary`, `created_at`.

**Venue**
- `id`, `name`, `notes`, `current_court_rate_per_hour`, `current_shuttle_rate_per_hour`, `created_at`, `updated_at`.

**VenueRateHistory** (audit trail of rate changes)
- `id`, `venue_id` (FK), `effective_from` (date), `court_rate_per_hour`, `shuttle_rate_per_hour`.

**Session**
- `id`, `venue_id` (FK), `played_on` (date), `started_at` (time), `duration_minutes` (multiple of 30, ≥ 30), `notes`, `status` ENUM(`draft`, `finalized`, `sent`), `snapshot_court_rate`, `snapshot_shuttle_rate`, `created_at`, `finalized_at`, `updated_at`.
- Snapshot rates are written when the session transitions to `finalized` and freeze the calculation.

**Court** (one row per court booked in a session)
- `id`, `session_id` (FK), `label`, `booker_player_id` (FK Player), `duration_minutes` (multiple of 30; may differ from session duration if a court was booked for less time), `created_at`.

**Slot** (30-min block within a court)
- `id`, `court_id` (FK), `slot_index` (0-based).
- Duration is fixed at 30 min; not stored.

**SlotPlayer** (composite PK)
- `slot_id` (FK), `player_id` (FK).

**ShuttleContribution** (one row per (session, owner))
- `id`, `session_id` (FK), `owner_player_id` (FK Player), `total_minutes` (multiple of 30, ≥ 0), `created_at`, `updated_at`.

### Decisions

1. **Rates are versioned; sessions snapshot rates.** Editing a venue's rate after a session is finalized does not change historical totals. The `snapshot_*` columns on `Session` make recomputation deterministic.
2. **30-min slots are first-class rows**, not derived. The UI maps 1:1 to slot rows.
3. **Shuttle contribution is `(owner, total_minutes)`** — no per-court breakdown, matching the chosen "per owner total hours" input model. "Total minutes" means total court-hours-of-on-duty across all courts (so two courts simultaneously using one owner's shuttles for 30 min counts as 60 min).
4. **`is_guest` flag** instead of a separate guest table — guests flow through the same calc/messaging logic; promotion to permanent roster is a flag flip + phone-number addition.
5. **Soft-delete on Player.** Removing a retired friend doesn't break old sessions.
6. **No "session participants" table.** Participants are the union of `Court.booker`, `SlotPlayer.player_id`, and `ShuttleContribution.owner_player_id`.

### Invariants enforced at the persistence/service boundary

- `Session.duration_minutes % 30 == 0` and `>= 30`.
- `Court.duration_minutes % 30 == 0` and `>= 30` and `<= Session.duration_minutes`.
- For each `Court`, exactly `duration_minutes / 30` `Slot` rows exist with `slot_index` 0..N-1.
- `SlotPlayer.player_id` must reference an active or guest player at session creation time (validated, but stored regardless so soft-deleted players continue to display correctly).
- `ShuttleContribution.total_minutes % 30 == 0`.
- Rate snapshots are non-null on `finalized` sessions.

---

## 4. Cost calculation

### Algorithm (pseudocode)

```python
def calculate_session(session: SessionAggregate) -> SessionResult:
    court_owe = defaultdict(Decimal)
    court_credit = defaultdict(Decimal)
    shuttle_owe = defaultdict(Decimal)
    shuttle_credit = defaultdict(Decimal)

    # ── Court costs (slot-based, equal split per slot) ────────────────────────
    for court in session.courts:
        court_total = (Decimal(court.duration_minutes) / 60) * session.snapshot_court_rate
        per_slot = court_total / len(court.slots)
        court_credit[court.booker_player_id] += court_total

        for slot in court.slots:
            n = len(slot.players)
            if n == 0:
                # Empty slot — booker eats the cost (they committed the booking).
                court_owe[court.booker_player_id] += per_slot
                continue
            share = per_slot / n
            for pid in slot.players:
                court_owe[pid] += share

    # ── Shuttle costs (pro-rata by play minutes) ──────────────────────────────
    total_shuttle_cost = Decimal(0)
    for c in session.shuttle_contributions:
        cost = (Decimal(c.total_minutes) / 60) * session.snapshot_shuttle_rate
        shuttle_credit[c.owner_player_id] += cost
        total_shuttle_cost += cost

    play_minutes = compute_play_minutes(session)  # slot count × 30, summed per player
    total_play = sum(play_minutes.values())

    if total_play > 0 and total_shuttle_cost > 0:
        for pid, mins in play_minutes.items():
            shuttle_owe[pid] += total_shuttle_cost * Decimal(mins) / Decimal(total_play)

    # ── Per-player result (NOT netted; UI shows breakdown + net) ──────────────
    participants = (
        set(court_owe) | set(court_credit) | set(shuttle_owe) | set(shuttle_credit)
    )
    return SessionResult(
        per_player=[
            PlayerResult(
                player_id=pid,
                owes_court=round_to_5(court_owe[pid]),
                owes_shuttle=round_to_5(shuttle_owe[pid]),
                credit_court=round_to_5(court_credit[pid]),
                credit_shuttle=round_to_5(shuttle_credit[pid]),
                owes_total=round_to_5(court_owe[pid] + shuttle_owe[pid]),
                credit_total=round_to_5(court_credit[pid] + shuttle_credit[pid]),
                net=round_to_5(
                    (court_owe[pid] + shuttle_owe[pid])
                    - (court_credit[pid] + shuttle_credit[pid])
                ),
                play_minutes=play_minutes.get(pid, 0),
            )
            for pid in participants
        ],
        court_rate=session.snapshot_court_rate,
        shuttle_rate=session.snapshot_shuttle_rate,
        total_court_cost=sum(court_credit.values()),
        total_shuttle_cost=total_shuttle_cost,
    )


def round_to_5(amount: Decimal) -> int:
    """Round HALF UP to nearest ₹5. 88.6→90, 87→85, 87.5→90, 92.4→90."""
    return int((amount / 5).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 5)
```

### Edge cases

| Case | Behaviour |
|---|---|
| Empty slot (court rented, nobody on it) | Booker pays for that slot — they committed the booking. |
| Booker didn't actually play | Naturally handled — credit applied, no slot owes. |
| Shuttle owner didn't play | Credit applied; their `play_minutes = 0` so they owe 0 of shuttle pool. |
| `total_play_minutes == 0` (impossible — guarded) | Calculator skips shuttle owe distribution; service layer rejects such sessions. |
| `shuttle_rate == 0` or no contributions | All shuttle figures are 0. |
| Sub-30-min anything | Rejected at validation layer. |
| Floats | Never used. All arithmetic in `Decimal`. |

### Property-based tests (Hypothesis)

The calculator is checked against these invariants on every CI run, with randomly generated valid sessions:

1. **Conservation (pre-rounding):** `Σ owes_total == Σ credit_total`.
2. **Conservation (post-rounding):** `|Σ owes_total − Σ credit_total| ≤ 5 × n_players` (rounding slack).
3. **Non-negativity:** `owes_court ≥ 0`, `owes_shuttle ≥ 0` for every player.
4. **Booker-credit identity:** `Σ credit_court == Σ court bills`.
5. **Shuttle-credit identity:** `Σ credit_shuttle == total_shuttle_cost`.
6. **Rate-zero degeneracy:** `shuttle_rate == 0` ⇒ all shuttle figures are 0.

---

## 5. UI design

### Design system

- **Tokens:** OKLCH-based palette, type scale (display / heading / body / caption), spacing scale (4px base), radius scale, motion durations (75/150/300ms).
- **Theme:** dark default, light + system options.
- **Type:** Inter for UI, JetBrains Mono for currency / numeric columns.
- **Icons:** Lucide (inline SVG).
- **Motion:** Tailwind transitions; `view-transitions-api` where supported for slot grid changes.
- **Layout:** mobile-first, max-width 480px container with edge padding; tablet/desktop layouts are stretched but never widescreen.

### Navigation

Bottom tab bar: `Sessions`, `Roster`, `Settings`. Floating `+` action on Sessions.

### Screens

1. **Sessions list** — recent sessions as cards with date · venue · player count · duration · total · status (draft / finalized / sent). Tap to open. Floating `+ New session` opens the wizard.
2. **New-session wizard (5 steps, swipeable):**
   1. **Setup** — venue (dropdown, with "+ New venue" inline), date, start time, duration (30-min stepper).
   2. **Players** — chip multi-select from active roster, "+ Add guest" inline (name + optional phone), "+ Add to roster" promotes the guest.
   3. **Courts** — list of courts, each with label + booker; "+ Court" button.
   4. **Slot grid** — rows = courts, columns = 30-min slots. Tap a cell → bottom sheet of session players → tap to toggle. Visual chip count per cell. "Copy from previous slot" shortcut.
   5. **Shuttles** — for each session player, an optional input "minutes of your shuttles on duty" with quick-pick 30/60/90/120.
   6. **Review** — full breakdown table; per-step edit-back; "Finalize" CTA writes the rate snapshot and locks the session.
3. **Session result / send** — header (date · venue · totals); per-player cards with court owes, shuttle owes, credit (if any), net; per-card action button: "Send via WhatsApp" (`wa.me` deep link) for players with phone, "Copy message" for those without; "Mark all sent" toggles status to `sent`; "Re-open" reverts to `finalized`.
4. **Roster** — searchable list, add/edit modal (name, primary E.164 phone with country picker default IN, avatar emoji, active toggle).
5. **Venue / Settings** — venue list with rate cards and rate-history view; theme; default venue; default duration; **default UPI ID** (interpolated into message template); **message template editor** with live preview.

### Accessibility

- All controls keyboard-navigable; visible focus rings.
- Colour-contrast tokens chosen to meet WCAG AA in both themes.
- Touch targets ≥ 44×44 px.
- Forms paired with labels (no placeholder-as-label).

---

## 6. WhatsApp message generation

### Link format

For a player with E.164 phone `+919876543210`:
```
https://wa.me/919876543210?text=<URL-encoded message>
```

For a player without a phone, the same generated message is shown in a "Copy message" affordance (clipboard write + toast).

### Default template (editable in Settings, with live preview)

```
Hi {name}! 🏸
Badminton on {date} at {venue}:
• Court: ₹{owes_court}
• Shuttle: ₹{owes_shuttle}
{credit_lines}
Total: ₹{abs_net} {direction}

Pay via UPI: {upi_id}
```

- `{credit_lines}` renders only if `credit_total > 0`, listing court / shuttle credits.
- `{direction}` is "you owe me" if `net > 0`, "I owe you" if `net < 0`, "settled" if `net == 0`.
- `{upi_id}` and other settings come from `Settings`.

### Phone storage and validation

- Phone numbers stored as E.164 (`+<countrycode><number>`).
- Validated at input time using the `phonenumbers` library; user gets immediate feedback.
- `wa.me` builder strips the leading `+`.

---

## 7. Testing strategy

| Layer | Tooling | Coverage target |
|---|---|---|
| `domain/` (calculator + value objects) | pytest unit + Hypothesis property tests | 95%+ branch |
| `services/` | pytest with in-memory SQLite + factory-boy | 80%+ |
| `persistence/` | pytest with real SQLite + Alembic upgrade & downgrade verification | smoke + migration tests |
| `api/` | pytest + httpx ASGI client; full request/response tests for each endpoint | every route |
| End-to-end | Playwright on the running container; one scripted "happy path" session creation | 1 test, ~30s |

**Static checks:** `ruff check`, `ruff format --check`, `mypy --strict app/domain app/services` — enforced in pre-commit and CI.

**CI pipeline:** lint → type-check → unit → service → api → e2e → docker buildx (linux/arm64) → push image to GHCR with git-sha tag. PR fails if any stage fails.

---

## 8. Deployment

### Build

- Multi-stage `Dockerfile`:
  - **Stage 1** (`tailwind`): Tailwind CLI standalone binary builds CSS once.
  - **Stage 2** (`runtime`): slim Python 3.12 image; copies app + built CSS.
- Built for `linux/arm64` via `docker buildx`. Image published to GHCR.

### `docker-compose.yml` on the Pi

```yaml
services:
  app:
    image: ghcr.io/{{GITHUB_OWNER}}/badminton-splitter:latest  # replace at deploy time
    restart: unless-stopped
    ports: ["8080:8080"]
    volumes:
      - /opt/badminton/data:/data
    environment:
      DATABASE_URL: sqlite+aiosqlite:////data/badminton.db
      LOG_LEVEL: info
      TZ: Asia/Kolkata

  litestream:
    image: litestream/litestream:0.3
    restart: unless-stopped
    volumes:
      - /opt/badminton/data:/data
      - /opt/badminton/backup:/backup
      - ./litestream.yml:/etc/litestream/litestream.yml:ro
    command: replicate -config /etc/litestream/litestream.yml
```

### Bootstrap

A `Makefile` target `make pi-deploy` SSH's in, pulls the latest image, runs `docker compose up -d`, runs `alembic upgrade head` inside the app container, and verifies `/health` returns 200.

### Updates

Default to **manual** (`make pi-deploy`) for safety. Watchtower can be added later if desired.

### Observability

- Structured JSON logs to stdout (Docker collects them).
- `/health` endpoint (returns DB connectivity status).
- `/metrics` endpoint in Prometheus format (request count, latency histogram, calc duration). Optional consumer.

---

## 9. Open questions deferred to implementation

These are intentionally not answered in the spec; the implementation plan can decide:

1. Whether the slot-grid editor uses Sortable.js + HTMX or stays purely tap-based (decision will be informed by feel-testing during implementation).
2. Whether to add a "settled" toggle per player (for partial settlements within a session), or keep `sent` as a session-level flag in v1.
3. Whether to expose `/metrics` by default or behind a feature flag.

---

## 10. Out of scope (v1) — explicitly deferred

- Authentication / multi-user.
- Automated WhatsApp send (Twilio / Cloud API / `whatsapp-web.js`).
- Public internet exposure (Tailscale handles).
- UPI payment status tracking.
- Recurring sessions / templates.
- Multi-currency.
- Offline / PWA.
- Mobile native app.
