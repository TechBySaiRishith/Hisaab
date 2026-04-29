"""Pydantic schemas for venue endpoints."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class VenueCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    court_rate: Decimal = Field(..., ge=Decimal("0"))
    shuttle_rate: Decimal = Field(..., ge=Decimal("0"))
    effective_from: date
    notes: str | None = None


class VenueOut(BaseModel):
    id: int
    name: str
    notes: str | None
    current_court_rate: Decimal
    current_shuttle_rate: Decimal
