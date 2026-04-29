"""FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import Database


def get_db(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    db: Database = request.app.state.db
    async with db.session() as s:
        yield s
