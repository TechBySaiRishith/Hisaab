"""HTML routes for venues."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.persistence.repositories.venue import VenueRepository

router = APIRouter(tags=["web:venues"])


@router.get("/venues", response_class=HTMLResponse)
async def list_venues_html(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
) -> HTMLResponse:
    venues = await VenueRepository(session).list_all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "venues/list.html", {"venues": venues}
    )


@router.get("/venues/new", response_class=HTMLResponse)
async def new_venue_form(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "venues/form.html", {"venue": None, "today": date.today().isoformat()}
    )


@router.post("/venues")
async def create_venue_html(
    request: Request, session: AsyncSession = Depends(get_session)  # noqa: B008
):  # type: ignore[return]
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    court_rate_str = str(form.get("court_rate", "0"))
    shuttle_rate_str = str(form.get("shuttle_rate", "0"))
    effective_from_str = str(form.get("effective_from", date.today().isoformat()))
    try:
        court_rate = Decimal(court_rate_str)
        shuttle_rate = Decimal(shuttle_rate_str)
        effective_from = date.fromisoformat(effective_from_str)
    except Exception as e:
        raise HTTPException(400, f"invalid input: {e}") from e

    await VenueRepository(session).create(
        name=name,
        court_rate=court_rate,
        shuttle_rate=shuttle_rate,
        effective_from=effective_from,
    )
    return RedirectResponse("/venues", status_code=303)
