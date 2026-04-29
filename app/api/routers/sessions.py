"""Session wizard endpoints (JSON API)."""
from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.session import (
    PlayerResultOut,
    SessionResultOut,
    SessionSubmit,
)
from app.persistence.repositories.session import CourtInputDict, ShuttleInputDict
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: SessionSubmit, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> dict[str, int]:
    service = SessionService(session)
    courts: list[CourtInputDict] = [
        cast(
            "CourtInputDict",
            {
                "label": c.label,
                "booker_player_id": c.booker_player_id,
                "duration_minutes": c.duration_minutes,
                "slot_assignments": [set(slot) for slot in c.slot_assignments],
            },
        )
        for c in payload.courts
    ]
    contribs: list[ShuttleInputDict] = [
        cast(
            "ShuttleInputDict",
            {"owner_player_id": c.owner_player_id, "total_minutes": c.total_minutes},
        )
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
    session_id: int, session: AsyncSession = Depends(get_session)  # noqa: B008
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
