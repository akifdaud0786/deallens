"""Map a daily scheduler cron to the explicit IST collection slot the collector receives. Pure; no I/O."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_DAILY = re.compile(r"^(\d{1,2}) (\d{1,2}) \* \* \*$")


def scheduled_slot(cron: str, now_utc: str, slots_ist: Iterable[str]) -> str:
    """The most recent firing of daily `cron` (UTC) at or before `now_utc`, as 'YYYY-MM-DDTHH:MM+05:30'.

    A late start keeps its slot; a clock earlier than the cron time yields the previous day's slot (which the
    collector then treats as a duplicate). Raises ValueError unless the cron is daily and lands on a configured slot.
    """
    m = _DAILY.match(cron.strip())
    if not m:
        raise ValueError(f"unsupported cron {cron!r}: expected a daily 'M H * * *' schedule")
    minute, hour = int(m.group(1)), int(m.group(2))
    now = datetime.fromisoformat(now_utc).astimezone(timezone.utc)
    fired = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fired > now:
        fired -= timedelta(days=1)
    local = fired.astimezone(IST)
    if f"{local:%H:%M}" not in set(slots_ist):
        raise ValueError(f"cron {cron!r} fires at {local:%H:%M} IST, which is not a configured collection slot")
    return f"{local:%Y-%m-%dT%H:%M}+05:30"
