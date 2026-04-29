"""Player repository — only place that touches the players + player_phones tables."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

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
        stmt = select(Player).where(Player.id == player_id).options(selectinload(Player.phones))
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def list_active(self, *, include_self: bool = False) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(Player.is_active.is_(True), Player.deleted_at.is_(None))
            .options(selectinload(Player.phones))
            .order_by(Player.name)
        )
        if not include_self:
            stmt = stmt.where(Player.is_self.is_(False))
        return (await self._s.execute(stmt)).scalars().all()

    async def get_self(self) -> Player | None:
        stmt = (
            select(Player)
            .where(Player.is_self.is_(True), Player.deleted_at.is_(None))
            .options(selectinload(Player.phones))
            .limit(1)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def ensure_self(self, *, default_name: str = "You") -> Player:
        existing = await self.get_self()
        if existing is not None:
            return existing
        p = Player(name=default_name, emoji="🫵", is_self=True, is_guest=False, is_active=True)
        self._s.add(p)
        await self._s.flush()
        return p

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
