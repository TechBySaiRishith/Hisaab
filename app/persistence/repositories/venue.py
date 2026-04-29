"""Venue repository — manages venues + rate history."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

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
        stmt = select(Venue).where(Venue.id == venue_id).options(selectinload(Venue.rate_history))
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
        # Expire only the rate_history relationship so the next get() reloads it.
        self._s.expire(v, ["rate_history"])
