"""WhatsApp message generation. wa.me link + text rendering."""
from __future__ import annotations

from urllib.parse import quote

from app.domain.models import PlayerResult

DEFAULT_TEMPLATE = """\
Hi {name}! 🏸
Badminton on {played_on} at {venue}:
• Court: ₹{owes_court}
• Shuttle: ₹{owes_shuttle}
{credit_lines}
Total: ₹{abs_net} {direction}

{upi_line}
""".strip()


def build_message_text(
    *,
    template: str,
    player: PlayerResult,
    played_on: str,
    venue: str,
    upi_id: str | None,
) -> str:
    direction = (
        "you owe me" if player.net > 0
        else "I owe you" if player.net < 0
        else "settled"
    )
    credit_lines = ""
    if player.credit_total > 0:
        if player.credit_court > 0:
            credit_lines += f"• You're credited ₹{player.credit_court} for booking court\n"
        if player.credit_shuttle > 0:
            credit_lines += f"• You're credited ₹{player.credit_shuttle} for shuttles\n"
        credit_lines = credit_lines.rstrip()

    upi_line = f"Pay via UPI: {upi_id}" if upi_id else ""

    return template.format(
        name=player.name,
        played_on=played_on,
        venue=venue,
        owes_court=player.owes_court,
        owes_shuttle=player.owes_shuttle,
        credit_lines=credit_lines,
        abs_net=abs(player.net),
        direction=direction,
        upi_line=upi_line,
    )


def build_wa_me_url(e164_phone: str, message: str) -> str:
    if not e164_phone.startswith("+"):
        raise ValueError(f"phone must be in E.164 format with leading +; got {e164_phone!r}")
    digits = e164_phone[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"
