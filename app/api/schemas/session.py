"""Pydantic schemas for session wizard."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, field_validator


class CourtSubmit(BaseModel):
    label: str = Field(..., min_length=1, max_length=50)
    booker_player_id: int
    duration_minutes: int
    slot_assignments: list[list[int]]

    @field_validator("duration_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v <= 0 or v % 30 != 0:
            raise ValueError("duration_minutes must be a positive multiple of 30")
        return v


class ShuttleSubmit(BaseModel):
    owner_player_id: int
    total_minutes: int = Field(..., ge=0)

    @field_validator("total_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v % 30 != 0:
            raise ValueError("total_minutes must be a multiple of 30")
        return v


class SessionSubmit(BaseModel):
    venue_id: int
    played_on: date
    started_at: time
    duration_minutes: int
    courts: list[CourtSubmit]
    shuttle_contributions: list[ShuttleSubmit] = []
    notes: str | None = None

    @field_validator("duration_minutes")
    @classmethod
    def _multiple_of_30(cls, v: int) -> int:
        if v <= 0 or v % 30 != 0:
            raise ValueError("duration_minutes must be a positive multiple of 30")
        return v


class PlayerResultOut(BaseModel):
    player_id: int
    name: str
    play_minutes: int
    owes_court: int
    owes_shuttle: int
    credit_court: int
    credit_shuttle: int
    owes_total: int
    credit_total: int
    net: int


class SessionResultOut(BaseModel):
    per_player: list[PlayerResultOut]
    total_court_cost: float
    total_shuttle_cost: float
