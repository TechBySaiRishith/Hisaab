"""HTML routes for application settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.persistence.orm import AppSettings
from app.persistence.repositories.player import PlayerRepository
from app.services.messaging import DEFAULT_TEMPLATE

router = APIRouter(tags=["web:settings"])


async def _get_or_create_settings(session: AsyncSession) -> AppSettings:
    settings = (
        await session.execute(select(AppSettings).where(AppSettings.id == 1))
    ).scalar_one_or_none()
    if settings is None:
        settings = AppSettings(
            id=1, upi_id=None, message_template=DEFAULT_TEMPLATE, theme="system"
        )
        session.add(settings)
        await session.flush()
    return settings


@router.get("/settings", response_class=HTMLResponse)
async def show_settings(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> HTMLResponse:
    settings = await _get_or_create_settings(session)
    self_player = await PlayerRepository(session).ensure_self()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings/form.html",
        {"settings": settings, "self_player": self_player},
    )


@router.post("/settings")
async def save_settings(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
):  # type: ignore[return]
    form = await request.form()
    settings = await _get_or_create_settings(session)

    your_name = str(form.get("your_name", "")).strip()
    your_emoji = str(form.get("your_emoji", "")).strip()
    upi_id = str(form.get("upi_id", "")).strip() or None
    message_template = str(form.get("message_template", DEFAULT_TEMPLATE))
    theme = str(form.get("theme", "system"))

    settings.upi_id = upi_id
    settings.message_template = message_template
    settings.theme = theme

    if your_name:
        self_player = await PlayerRepository(session).ensure_self()
        self_player.name = your_name
        if your_emoji:
            self_player.emoji = your_emoji

    await session.flush()
    return RedirectResponse("/settings", status_code=303)
