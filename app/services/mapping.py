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
from app.persistence.orm import Player
from app.persistence.orm import Session as ORMSession


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
