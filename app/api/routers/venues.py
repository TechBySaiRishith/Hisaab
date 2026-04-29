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
async def list_venues(session: AsyncSession = Depends(get_session)) -> list[VenueOut]:  # noqa: B008
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
    payload: VenueCreate, session: AsyncSession = Depends(get_session)  # noqa: B008
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
