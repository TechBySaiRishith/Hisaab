"""Pure domain types for the cost calculator. No I/O, no framework imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PlayerRef:
    player_id: int
    name: str

    def __hash__(self) -> int:
        return hash(self.player_id)


@dataclass(frozen=True, slots=True)
class SlotInput:
    slot_index: int
    player_ids: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.player_ids, frozenset):
            object.__setattr__(self, "player_ids", frozenset(self.player_ids))


@dataclass(frozen=True, slots=True)
class CourtInput:
    court_id: int
    booker_player_id: int
    duration_minutes: int
    slots: tuple[SlotInput, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0 or self.duration_minutes % 30 != 0:
            raise ValueError(
                f"court duration_minutes must be positive multiple of 30, got {self.duration_minutes}"
            )
        if not isinstance(self.slots, tuple):
            object.__setattr__(self, "slots", tuple(self.slots))
        expected = self.duration_minutes // 30
        if len(self.slots) != expected:
            raise ValueError(
                f"court {self.court_id} has {len(self.slots)} slots but duration implies {expected}"
            )


@dataclass(frozen=True, slots=True)
class ShuttleContributionInput:
    owner_player_id: int
    total_minutes: int

    def __post_init__(self) -> None:
        if self.total_minutes < 0 or self.total_minutes % 30 != 0:
            raise ValueError(
                f"shuttle total_minutes must be non-negative multiple of 30, got {self.total_minutes}"
            )


@dataclass(frozen=True, slots=True)
class SessionInput:
    court_rate_per_hour: Decimal
    shuttle_rate_per_hour: Decimal
    courts: tuple[CourtInput, ...]
    shuttle_contributions: tuple[ShuttleContributionInput, ...]
    participants: frozenset[PlayerRef]

    def __post_init__(self) -> None:
        if self.court_rate_per_hour < 0:
            raise ValueError("court_rate_per_hour must be >= 0")
        if self.shuttle_rate_per_hour < 0:
            raise ValueError("shuttle_rate_per_hour must be >= 0")
        if not isinstance(self.courts, tuple):
            object.__setattr__(self, "courts", tuple(self.courts))
        if not isinstance(self.shuttle_contributions, tuple):
            object.__setattr__(self, "shuttle_contributions", tuple(self.shuttle_contributions))
        if not isinstance(self.participants, frozenset):
            object.__setattr__(self, "participants", frozenset(self.participants))


@dataclass(frozen=True, slots=True)
class PlayerResult:
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


@dataclass(frozen=True, slots=True)
class SessionResult:
    per_player: tuple[PlayerResult, ...]
    court_rate_per_hour: Decimal
    shuttle_rate_per_hour: Decimal
    total_court_cost: Decimal
    total_shuttle_cost: Decimal
