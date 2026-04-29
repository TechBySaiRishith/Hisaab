"""Player REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.player import PlayerCreate, PlayerOut
from app.persistence.orm import Player
from app.persistence.repositories.player import PlayerRepository

router = APIRouter(prefix="/api/players", tags=["players"])


def _to_out(player: Player) -> PlayerOut:
    primary = next((p for p in player.phones if p.is_primary), None) if player.phones else None
    return PlayerOut(
        id=player.id,
        name=player.name,
        emoji=player.emoji,
        is_guest=player.is_guest,
        is_active=player.is_active,
        primary_phone=primary.e164_number if primary else None,
    )


@router.get("", response_model=list[PlayerOut])
async def list_players(session: AsyncSession = Depends(get_session)) -> list[PlayerOut]:  # noqa: B008
    repo = PlayerRepository(session)
    players = await repo.list_active()
    return [_to_out(p) for p in players]


@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def create_player(
    payload: PlayerCreate, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> PlayerOut:
    repo = PlayerRepository(session)
    p = await repo.create(name=payload.name, emoji=payload.emoji, is_guest=payload.is_guest)
    if payload.phone:
        await repo.add_phone(p.id, e164=payload.phone, is_primary=True)
    refreshed = await repo.get(p.id)
    if refreshed is None:
        raise HTTPException(500, "could not reload player")
    return _to_out(refreshed)
