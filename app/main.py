"""FastAPI app factory and uvicorn entrypoint."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from app.observability import configure_structlog
from app.observability import install as install_observability
from app.persistence import orm  # noqa: F401
from app.persistence.database import Database


def build_app(database_url: str | None = None) -> FastAPI:
    if database_url is None:
        # Production path: read settings from environment.
        # Falls back to the legacy env-var default so existing dev workflows
        # (e.g. `make dev`) still work without a .env file.
        _default_dsn = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/badminton.db")
        try:
            from app.config.settings import Settings

            settings = Settings()
            dsn = settings.database_url
            log_level = settings.log_level
            metrics_enabled = settings.metrics_enabled
        except Exception:
            # DATABASE_URL not set (e.g. bare import during test collection)
            dsn = _default_dsn
            log_level = "info"
            metrics_enabled = True
    else:
        # Test path: caller provides DSN, use safe defaults
        dsn = database_url
        log_level = "info"
        metrics_enabled = True

    configure_structlog(log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        db = Database(dsn)
        app.state.db = db
        # Initialize AppSettings singleton + ensure self-player exists
        try:
            async with db.session() as s:
                from app.persistence.orm import AppSettings
                from app.persistence.repositories.player import PlayerRepository
                from app.services.messaging import DEFAULT_TEMPLATE

                existing = (
                    await s.execute(select(AppSettings).where(AppSettings.id == 1))
                ).scalar_one_or_none()
                if existing is None:
                    s.add(
                        AppSettings(
                            id=1,
                            upi_id=None,
                            message_template=DEFAULT_TEMPLATE,
                            theme="system",
                        )
                    )
                await PlayerRepository(s).ensure_self()
        except Exception:
            # Table may not exist yet (before migration) — skip silently
            pass
        try:
            yield
        finally:
            await db.dispose()

    app = FastAPI(title="Hisaab", version="0.1.0", lifespan=lifespan)

    install_observability(app, enabled=metrics_enabled)

    # Jinja2 templates
    templates = Jinja2Templates(directory="app/web/templates")
    app.state.templates = templates

    @app.get("/health")
    async def health() -> dict[str, str]:
        db: Database = app.state.db
        async with db.session() as s:
            await s.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        from app.persistence.repositories.session import SessionRepository
        from app.persistence.repositories.venue import VenueRepository

        db = app.state.db
        tmpl = app.state.templates
        async with db.session() as s:
            sessions = await SessionRepository(s).list_recent(limit=20)
            venues = {v.id: v for v in await VenueRepository(s).list_all()}
        rows = [
            {
                "id": x.id,
                "played_on": x.played_on,
                "venue_name": venues[x.venue_id].name if x.venue_id in venues else "?",
                "player_count": len(
                    {sp.player_id for c in x.courts for sl in c.slots for sp in sl.players}
                )
                if x.courts
                else 0,
                "duration_minutes": x.duration_minutes,
                "court_count": len(x.courts),
                "status": x.status,
            }
            for x in sessions
        ]
        return tmpl.TemplateResponse(request, "sessions/list.html", {"sessions": rows})

    from app.api.routers import players as players_router
    from app.api.routers import players_html as players_html_router
    from app.api.routers import sessions as sessions_router
    from app.api.routers import sessions_html as sessions_html_router
    from app.api.routers import settings_html as settings_html_router
    from app.api.routers import venues as venues_router
    from app.api.routers import venues_html as venues_html_router

    app.include_router(players_router.router)
    app.include_router(venues_router.router)
    app.include_router(sessions_router.router)
    # HTML routers — sessions_html before sessions_html to ensure /sessions/new
    # is matched before /sessions/{session_id}
    app.include_router(sessions_html_router.router)
    app.include_router(players_html_router.router)
    app.include_router(venues_html_router.router)
    app.include_router(settings_html_router.router)

    app.mount(
        "/static",
        StaticFiles(directory="app/web/static"),
        name="static",
    )

    return app


app = build_app()
