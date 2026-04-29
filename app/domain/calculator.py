"""Pure cost calculator for badminton sessions.

Reads a SessionInput and returns a SessionResult. No I/O, no framework.
See docs/superpowers/specs/2026-04-29-badminton-splitter-design.md §4.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.domain.models import (
    PlayerResult,
    SessionInput,
    SessionResult,
    ShuttleContributionInput,
)
from app.domain.rounding import round_to_5


def calculate_session(session: SessionInput) -> SessionResult:
    court_owe: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    court_credit: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    shuttle_owe: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    shuttle_credit: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    play_minutes: dict[int, int] = defaultdict(int)
    # Per-court play minutes — needed for per-court shuttle distribution
    play_minutes_by_court: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

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
                play_minutes_by_court[court.court_id][pid] += 30
            n = len(slot.player_ids)
            if n == 0:
                court_owe[court.booker_player_id] += per_slot
                continue
            share = per_slot / Decimal(n)
            for pid in slot.player_ids:
                court_owe[pid] += share

    # ── Shuttle costs (per-court attribution) ─────────────────────────────────
    # Each court's shuttle wear is paid only by players who played on that court.
    # Owners are credited the full cost of their contributions.
    total_shuttle_cost = Decimal("0")
    contribs_by_court: dict[int, list[tuple[ShuttleContributionInput, Decimal]]] = defaultdict(list)
    for c in session.shuttle_contributions:
        cost = (Decimal(c.total_minutes) / Decimal(60)) * session.shuttle_rate_per_hour
        shuttle_credit[c.owner_player_id] += cost
        total_shuttle_cost += cost
        contribs_by_court[c.court_id].append((c, cost))

    for court_id, contribs in contribs_by_court.items():
        court_shuttle_cost = sum((cost for _, cost in contribs), Decimal("0"))
        if court_shuttle_cost <= 0:
            continue

        court_play = play_minutes_by_court.get(court_id, {})
        total_court_play = sum(court_play.values())

        if total_court_play > 0:
            for pid, mins in court_play.items():
                shuttle_owe[pid] += court_shuttle_cost * Decimal(mins) / Decimal(total_court_play)
        else:
            # Court had shuttles billed but nobody played any slot on it.
            # Edge case (e.g. court rented + shuttles bought but everyone left
            # before playing). Charge the contribution back to the owners.
            for c, cost in contribs:
                shuttle_owe[c.owner_player_id] += cost

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
