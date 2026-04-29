"""Pydantic schemas for player endpoints."""
from __future__ import annotations

import phonenumbers
from pydantic import BaseModel, Field, field_validator


class PlayerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    emoji: str = Field("🏸", max_length=8)
    phone: str | None = None
    is_guest: bool = False

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        try:
            parsed = phonenumbers.parse(v, "IN")
        except phonenumbers.NumberParseException as e:
            raise ValueError(f"invalid phone: {e}") from e
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("invalid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class PlayerOut(BaseModel):
    id: int
    name: str
    emoji: str
    is_guest: bool
    is_active: bool
    primary_phone: str | None
