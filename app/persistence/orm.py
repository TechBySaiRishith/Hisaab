"""SQLAlchemy ORM models. The single source of truth for the DB schema.

Migrations in alembic/versions/ derive from this module.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🏸", nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_self: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    phones: Mapped[list[PlayerPhone]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class PlayerPhone(Base):
    __tablename__ = "player_phones"
    __table_args__ = (UniqueConstraint("player_id", "e164_number", name="uq_player_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(4), default="IN", nullable=False)
    e164_number: Mapped[str] = mapped_column(String(20), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    player: Mapped[Player] = relationship(back_populates="phones")


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_court_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    current_shuttle_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rate_history: Mapped[list[VenueRateHistory]] = relationship(
        back_populates="venue", cascade="all, delete-orphan"
    )


class VenueRateHistory(Base):
    __tablename__ = "venue_rate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    court_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    shuttle_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    venue: Mapped[Venue] = relationship(back_populates="rate_history")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), nullable=False)
    played_on: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("draft", "finalized", "sent", name="session_status"),
        default="draft",
        nullable=False,
    )
    snapshot_court_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    snapshot_shuttle_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    courts: Mapped[list[Court]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    shuttle_contributions: Mapped[list[ShuttleContribution]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    booker_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session: Mapped[Session] = relationship(back_populates="courts")
    slots: Mapped[list[Slot]] = relationship(
        back_populates="court", cascade="all, delete-orphan", order_by="Slot.slot_index"
    )


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("court_id", "slot_index", name="uq_slot_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id", ondelete="CASCADE"), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)

    court: Mapped[Court] = relationship(back_populates="slots")
    players: Mapped[list[SlotPlayer]] = relationship(
        back_populates="slot", cascade="all, delete-orphan"
    )


class SlotPlayer(Base):
    __tablename__ = "slot_players"

    slot_id: Mapped[int] = mapped_column(
        ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)

    slot: Mapped[Slot] = relationship(back_populates="players")
    player: Mapped[Player] = relationship("Player")


class ShuttleContribution(Base):
    __tablename__ = "shuttle_contributions"
    __table_args__ = (
        UniqueConstraint("session_id", "owner_player_id", name="uq_session_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="shuttle_contributions")


class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upi_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str] = mapped_column(String(10), default="system", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
