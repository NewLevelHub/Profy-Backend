"""Business time: Asia/Almaty dates over UTC storage (PRO-501).

Every datetime is stored and sent in UTC; the business calendar — what
"today" is, where a day or a week starts, which days are frozen in the
schedule — follows Asia/Almaty (ТЗ CRM Profile v4.1 §4.6 п.9, §6.5). Decide
those questions here, never from `date.today()` or the server's local zone.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = "Asia/Almaty"
BUSINESS_TZ = ZoneInfo(BUSINESS_TIMEZONE)

# Today and the next two days: a specialist may not change their availability
# in them (ТЗ §4.6 п.3).
FREEZE_DAYS = 3


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_business(moment: datetime) -> datetime:
    """`moment` (timezone-aware) as Almaty wall time."""
    return moment.astimezone(BUSINESS_TZ)


def business_date(moment: datetime) -> date:
    """The Almaty calendar date `moment` falls on."""
    return to_business(moment).date()


def today(now: datetime | None = None) -> date:
    return business_date(now or now_utc())


def at(day: date, wall: time) -> datetime:
    """Almaty wall time `wall` on `day`, as a UTC datetime."""
    return datetime.combine(day, wall, tzinfo=BUSINESS_TZ).astimezone(timezone.utc)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC `[start, end)` of the Almaty day `day`."""
    return at(day, time.min), at(day + timedelta(days=1), time.min)


def week_start(day: date) -> date:
    """Monday of the week `day` is in."""
    return day - timedelta(days=day.weekday())


def editable_from(now: datetime | None = None) -> date:
    """First date outside the freeze."""
    return today(now) + timedelta(days=FREEZE_DAYS)


def is_frozen(day: date, now: datetime | None = None) -> bool:
    """`day` is today or one of the next `FREEZE_DAYS - 1` days.

    Past days are not "frozen" — they are past, a separate rule."""
    current = today(now)
    return current <= day < current + timedelta(days=FREEZE_DAYS)
