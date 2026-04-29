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
        """Recompute a finalized session without re-finalizing."""
        aggregate = await self._repo.get_aggregate(session_id)
        if aggregate is None:
            raise ValueError(f"session {session_id} not found")
        domain_input = await session_orm_to_domain(self._s, aggregate)
        return calculate_session(domain_input)
