"""HTML routes for the player roster."""
from __future__ import annotations

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.persistence.repositories.player import PlayerRepository

router = APIRouter(tags=["web:players"])


@router.get("/players", response_class=HTMLResponse)
async def list_players_html(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> HTMLResponse:
    players = await PlayerRepository(session).list_active()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "players/list.html", {"players": players}
    )


@router.get("/players/new", response_class=HTMLResponse)
async def new_player_form(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "players/form.html", {"player": None}
    )


@router.post("/players")
async def create_player_html(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
):  # type: ignore[return]
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    emoji = str(form.get("emoji", "🏸"))
    phone_raw = str(form.get("phone", "")).strip()
    msg_template_raw = str(form.get("message_template", "")).strip()
    repo = PlayerRepository(session)
    p = await repo.create(name=name, emoji=emoji, is_guest=False)
    if msg_template_raw:
        p.message_template = msg_template_raw
        await session.flush()
    if phone_raw:
        try:
            parsed = phonenumbers.parse(phone_raw, "IN")
        except phonenumbers.NumberParseException as e:
            raise HTTPException(400, f"invalid phone: {e}") from e
        if not phonenumbers.is_valid_number(parsed):
            raise HTTPException(400, "invalid phone number")
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        await repo.add_phone(p.id, e164=e164, is_primary=True)
    return RedirectResponse("/players", status_code=303)


@router.get("/players/{player_id}/edit", response_class=HTMLResponse)
async def edit_player_form(
    player_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HTMLResponse:
    player = await PlayerRepository(session).get(player_id)
    if player is None:
        raise HTTPException(404, f"player {player_id} not found")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "players/form.html", {"player": player}
    )


@router.post("/players/{player_id}/edit")
async def update_player_html(
    player_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):  # type: ignore[return]
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    emoji = str(form.get("emoji", "🏸"))
    msg_template_raw = str(form.get("message_template", "")).strip()
    repo = PlayerRepository(session)
    player = await repo.get(player_id)
    if player is None:
        raise HTTPException(404, f"player {player_id} not found")
    player.name = name
    player.emoji = emoji
    player.message_template = msg_template_raw or None
    await session.flush()
    return RedirectResponse("/players", status_code=303)


@router.post("/players/{player_id}/delete")
async def delete_player_html(
    player_id: int, session: AsyncSession = Depends(get_session)  # noqa: B008
):  # type: ignore[return]
    await PlayerRepository(session).soft_delete(player_id)
    return RedirectResponse("/players", status_code=303)
