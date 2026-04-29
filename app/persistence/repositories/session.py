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
    slot_assignments: list[set[int]]


class ShuttleInputDict(TypedDict):
    court_id: int
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
                    court_id=shuttle["court_id"],
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
            .options(
                selectinload(Session.courts).selectinload(Court.slots).selectinload(Slot.players)
            )
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

    async def update_courts(self, session_id: int, *, courts: list[CourtInputDict]) -> None:
        s = await self.get_aggregate(session_id)
        if s is None:
            raise ValueError(f"session {session_id} not found")
        for existing_court in list(s.courts):
            await self._s.delete(existing_court)
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

    async def toggle_slot_player(self, *, slot_id: int, player_id: int) -> bool:
        """Toggle a player on/off a slot. Returns True if now on, False if removed."""
        stmt = select(SlotPlayer).where(
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
                        court_id=c["court_id"],
                        owner_player_id=c["owner_player_id"],
                        total_minutes=c["total_minutes"],
                    )
                )
        await self._s.flush()
