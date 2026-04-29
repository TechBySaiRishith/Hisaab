"""HTML routes for the session wizard."""

from __future__ import annotations

from datetime import date as _date
from datetime import time as _time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.persistence.orm import Slot, SlotPlayer
from app.persistence.repositories.player import PlayerRepository
from app.persistence.repositories.session import SessionRepository
from app.persistence.repositories.venue import VenueRepository
from app.services.session_service import SessionService

router = APIRouter(tags=["web:sessions"])


@router.get("/sessions/new", response_class=HTMLResponse)
async def new_session_setup(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    venues = await VenueRepository(session).list_all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_setup.html",
        {"venues": venues, "today": _date.today().isoformat()},
    )


@router.get("/sessions/new/players", response_class=HTMLResponse)
async def new_session_players(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    repo = PlayerRepository(session)
    players = await repo.list_active()
    self_player = await repo.get_self()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_players.html",
        {"players": players, "self_player": self_player},
    )


@router.post("/sessions/new/players", response_class=HTMLResponse)
async def new_session_players_post(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    """Step 1 POST: collect setup form data and re-render the players page."""
    form = await request.form()
    repo = PlayerRepository(session)
    players = await repo.list_active()
    self_player = await repo.get_self()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_players.html",
        {
            "players": players,
            "self_player": self_player,
            "venue_id": form.get("venue_id"),
            "played_on": form.get("played_on"),
            "started_at": form.get("started_at"),
            "duration_minutes": form.get("duration_minutes"),
        },
    )


@router.post("/sessions/new/court-count", response_class=HTMLResponse)
async def new_session_court_count_form(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    """Step 2 → Step 3 transition: render the court count + duration form,
    carrying venue + date + player_ids forward as hidden fields."""
    form = await request.form()
    player_ids = [str(x) for x in form.getlist("player_ids")]
    if not player_ids:
        return RedirectResponse("/sessions/new", status_code=303)  # type: ignore[return-value]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_court_count.html",
        {
            "venue_id": form.get("venue_id"),
            "played_on": form.get("played_on"),
            "player_ids": player_ids,
        },
    )


@router.post("/sessions/new/courts")
async def new_session_create_draft_and_show_courts(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    """Step 3 submit: collect court_count + per-court durations, create draft.
    Session-level duration is derived as the max of court durations.
    started_at is set to a placeholder (not user-facing in v1)."""
    from typing import cast

    from app.persistence.repositories.session import CourtInputDict

    form = await request.form()
    venue_id = int(form["venue_id"])
    played_on = _date.fromisoformat(str(form["played_on"]))
    player_ids = [int(x) for x in form.getlist("player_ids")]
    court_count = max(1, min(4, int(form.get("court_count", "1"))))

    if not player_ids:
        return RedirectResponse("/sessions/new", status_code=303)

    courts: list = []
    court_minutes_list: list[int] = []
    for i in range(1, court_count + 1):
        court_minutes_raw = form.get(f"court_{i}_minutes")
        court_minutes = int(court_minutes_raw) if court_minutes_raw else 60
        court_minutes = max(30, (court_minutes // 30) * 30)
        court_minutes_list.append(court_minutes)
        n_slots = max(1, court_minutes // 30)
        courts.append(
            cast(
                "CourtInputDict",
                {
                    "label": f"Court {i}",
                    "booker_player_id": player_ids[0],
                    "duration_minutes": court_minutes,
                    "slot_assignments": [set(player_ids) for _ in range(n_slots)],
                },
            )
        )

    # Session-level duration = longest court (wall-clock duration of the session)
    session_duration = max(court_minutes_list) if court_minutes_list else 60
    started_at = _time(0, 0)  # placeholder — no longer user-collected in v1

    sid = await SessionService(session).create_draft(
        venue_id=venue_id,
        played_on=played_on,
        started_at=started_at,
        duration_minutes=session_duration,
        courts=courts,
        shuttle_contributions=[],
    )
    return RedirectResponse(f"/sessions/{sid}/courts", status_code=303)


@router.get("/sessions/{session_id}/courts", response_class=HTMLResponse)
async def show_session_courts_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    pids = {sp.player_id for c in s.courts for sl in c.slots for sp in sl.players}
    rows = await PlayerRepository(session).list_active(include_self=True)
    session_players = [p for p in rows if p.id in pids]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_courts.html",
        {"session": s, "session_players": session_players},
    )


@router.post("/sessions/{session_id}/courts")
async def submit_courts_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    """Update labels + bookers on the existing court rows. Durations are
    preserved from when the draft was created in step 3."""
    from typing import cast

    from app.persistence.repositories.session import CourtInputDict

    form = await request.form()
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")

    # Preserve each existing court's duration + slot player assignments
    courts = []
    for i, existing in enumerate(s.courts, start=1):
        label = str(form.get(f"court_{i}_label") or existing.label)
        booker_raw = form.get(f"court_{i}_booker")
        booker = int(booker_raw) if booker_raw else existing.booker_player_id
        minutes = existing.duration_minutes
        n_slots = max(1, minutes // 30)
        existing_assignments: list[set[int]] = [
            {sp.player_id for sp in slot.players} for slot in existing.slots
        ]
        # Pad if needed (shouldn't be — but safety)
        while len(existing_assignments) < n_slots:
            existing_assignments.append(existing_assignments[-1] if existing_assignments else set())
        courts.append(
            cast(
                "CourtInputDict",
                {
                    "label": label,
                    "booker_player_id": booker,
                    "duration_minutes": minutes,
                    "slot_assignments": existing_assignments[:n_slots],
                },
            )
        )
    await SessionRepository(session).update_courts(session_id, courts=courts)
    return RedirectResponse(f"/sessions/{session_id}/slots", status_code=303)


@router.get("/sessions/{session_id}/slots", response_class=HTMLResponse)
async def show_slots_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload as _selectinload

    from app.persistence.orm import Court, Session

    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")

    stmt = (
        sa_select(Session)
        .where(Session.id == session_id)
        .options(
            _selectinload(Session.courts)
            .selectinload(Court.slots)
            .selectinload(Slot.players)
            .selectinload(SlotPlayer.player)
        )
    )
    s_full = (await session.execute(stmt)).scalar_one_or_none()
    if s_full is None:
        raise HTTPException(404, f"session {session_id} not found")

    n_slots = max(
        (len(c.slots) for c in s_full.courts),
        default=0,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_slots.html",
        {
            "session": s_full,
            "courts": s_full.courts,
            "n_slots": n_slots,
        },
    )


@router.get("/sessions/{session_id}/slots/{slot_id}/picker", response_class=HTMLResponse)
async def get_slot_picker(
    session_id: int,
    slot_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    stmt = _select(Slot).where(Slot.id == slot_id).options(selectinload(Slot.players))
    slot = (await session.execute(stmt)).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, f"slot {slot_id} not found")
    current_player_ids = {sp.player_id for sp in slot.players}
    players = await PlayerRepository(session).list_active(include_self=True)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/slot_picker.html",
        {
            "session_id": session_id,
            "slot_id": slot_id,
            "players": players,
            "current_player_ids": current_player_ids,
        },
    )


@router.post(
    "/sessions/{session_id}/slots/{slot_id}/toggle/{player_id}",
    response_class=HTMLResponse,
)
async def toggle_slot_player(
    session_id: int,
    slot_id: int,
    player_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    from app.persistence.orm import Session

    await SessionRepository(session).toggle_slot_player(slot_id=slot_id, player_id=player_id)
    stmt = (
        _select(Slot)
        .where(Slot.id == slot_id)
        .options(selectinload(Slot.players).selectinload(SlotPlayer.player))
    )
    slot = (await session.execute(stmt)).scalar_one_or_none()
    if slot is None:
        raise HTTPException(404, f"slot {slot_id} not found")

    s = await session.get(Session, session_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/slot_cell.html",
        {
            "session": s,
            "slot": slot,
        },
    )


@router.get("/sessions/{session_id}/shuttles", response_class=HTMLResponse)
async def show_shuttles_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    pids = {sp.player_id for c in s.courts for sl in c.slots for sp in sl.players}
    rows = await PlayerRepository(session).list_active(include_self=True)
    session_players = [p for p in rows if p.id in pids]
    existing = {sc.owner_player_id: sc.total_minutes for sc in s.shuttle_contributions}
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/new_shuttles.html",
        {
            "session": s,
            "session_players": session_players,
            "existing": existing,
        },
    )


@router.post("/sessions/{session_id}/shuttles")
async def submit_shuttles(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    from typing import cast

    from app.persistence.repositories.session import ShuttleInputDict

    form = await request.form()
    contribs = []
    for key, value in form.items():
        if not (key.startswith("player_") and key.endswith("_minutes")):
            continue
        pid = int(key.removeprefix("player_").removesuffix("_minutes"))
        minutes = int(value or 0)
        if minutes > 0:
            contribs.append(
                cast("ShuttleInputDict", {"owner_player_id": pid, "total_minutes": minutes})
            )
    await SessionRepository(session).update_shuttle_contributions(
        session_id, contributions=contribs
    )
    return RedirectResponse(f"/sessions/{session_id}/review", status_code=303)


@router.get("/sessions/{session_id}/review", response_class=HTMLResponse)
async def show_review_step(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    venue = await VenueRepository(session).get(s.venue_id)
    if venue is None:
        raise HTTPException(404, f"venue {s.venue_id} not found")
    if s.snapshot_court_rate is None:
        s.snapshot_court_rate = venue.current_court_rate_per_hour
    if s.snapshot_shuttle_rate is None:
        s.snapshot_shuttle_rate = venue.current_shuttle_rate_per_hour
    await session.flush()
    preview = await SessionService(session).compute(session_id)
    s.snapshot_court_rate = None
    s.snapshot_shuttle_rate = None
    await session.flush()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/review.html",
        {"session": s, "venue": venue, "preview": preview},
    )


@router.post("/sessions/{session_id}/finalize")
async def finalize_session_html(
    session_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    await SessionService(session).finalize_and_compute(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def show_session_result(
    session_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    from app.persistence.orm import AppSettings
    from app.services.messaging import DEFAULT_TEMPLATE, build_message_text, build_wa_me_url

    s = await SessionRepository(session).get_aggregate(session_id)
    if s is None:
        raise HTTPException(404, f"session {session_id} not found")
    venue = await VenueRepository(session).get(s.venue_id)
    if venue is None:
        raise HTTPException(404, f"venue {s.venue_id} missing")
    if s.status == "draft":
        raise HTTPException(400, "session must be finalized before viewing result")

    result = await SessionService(session).compute(session_id)

    settings_row = (
        await session.execute(_select(AppSettings).where(AppSettings.id == 1))
    ).scalar_one_or_none()
    upi_id = settings_row.upi_id if settings_row else None
    template = (settings_row.message_template if settings_row else None) or DEFAULT_TEMPLATE

    pids = [p.player_id for p in result.per_player]
    player_repo = PlayerRepository(session)
    by_id = {}
    for pid in pids:
        p = await player_repo.get(pid)
        if p is not None:
            by_id[p.id] = p

    self_player = await player_repo.get_self()
    self_player_id = self_player.id if self_player else None

    played_on_str = s.played_on.strftime("%d %b %Y")
    lines: dict[int, dict] = {}
    you_summary: dict | None = None
    other_results = []

    for p in result.per_player:
        player_row = by_id.get(p.player_id)

        if self_player_id is not None and p.player_id == self_player_id:
            # Build a "you" summary block — no WhatsApp message needed
            if p.net == 0:
                tally = "settled"
            elif p.net > 0:
                # positive net = self owes others (in self's POV: paid less than fair share)
                tally = "you owe"
            else:
                tally = "to collect"
            you_summary = {
                "owes_court": p.owes_court,
                "owes_shuttle": p.owes_shuttle,
                "credit_court": p.credit_court,
                "credit_shuttle": p.credit_shuttle,
                "credit_total": p.credit_total,
                "net": p.net,
                "abs_net": abs(p.net),
                "tally": tally,
                "play_minutes": p.play_minutes,
            }
            continue

        per_player_template = player_row.message_template if player_row else None
        effective_template = per_player_template or template
        msg = build_message_text(
            template=effective_template,
            player=p,
            played_on=played_on_str,
            venue=venue.name,
            upi_id=upi_id,
        )
        primary = None
        if player_row is not None:
            primary = next((ph for ph in player_row.phones if ph.is_primary), None)
        lines[p.player_id] = {
            "has_phone": primary is not None,
            "wa_me_url": build_wa_me_url(primary.e164_number, msg) if primary else None,
            "message_text": msg,
            "uses_custom_template": per_player_template is not None,
        }
        other_results.append(p)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "sessions/result.html",
        {
            "session": s,
            "venue": venue,
            "result": result,
            "you": you_summary,
            "other_results": other_results,
            "lines": lines,
        },
    )


@router.post("/sessions/{session_id}/mark-sent")
async def mark_session_sent(
    session_id: int,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    await SessionRepository(session).mark_sent(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)
