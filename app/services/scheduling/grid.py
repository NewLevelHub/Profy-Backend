"""The schedule grid: 30-minute slots inside the working day, Almaty wall
time over UTC. Pure functions — no database, no clock of their own."""

from datetime import date, datetime, time, timedelta

from app.services import tz

SLOT = timedelta(minutes=30)
DAY_START = time(8, 0)
DAY_END = time(22, 0)
WEEK_DAYS = 7


class GridError(ValueError):
    """An interval that does not fit the grid; `error_code` is the contract's."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def day_slot_starts(day: date) -> list[datetime]:
    """UTC starts of every grid slot on the Almaty day `day`."""
    first = tz.at(day, DAY_START)
    last = tz.at(day, DAY_END)
    starts = []
    current = first
    while current < last:
        starts.append(current)
        current += SLOT
    return starts


def week_days(monday: date) -> list[date]:
    return [monday + timedelta(days=offset) for offset in range(WEEK_DAYS)]


def week_bounds(monday: date) -> tuple[datetime, datetime]:
    """UTC `[start, end)` of the grid of the week starting `monday`."""
    return tz.at(monday, DAY_START), tz.at(monday + timedelta(days=WEEK_DAYS - 1), DAY_END)


def _aligned(moment: datetime) -> bool:
    local = tz.to_business(moment)
    return local.second == 0 and local.microsecond == 0 and local.minute % 30 == 0


def wall_on_grid(wall: time) -> bool:
    return wall.second == 0 and wall.microsecond == 0 and wall.minute % 30 == 0


def interval_slots(start: datetime, end: datetime) -> list[datetime]:
    """Slot starts covering `[start, end)` — one Almaty day, inside the grid.

    Raises `GridError("slot_misaligned")` or `GridError("slot_out_of_grid")`."""
    if end <= start or not _aligned(start) or not _aligned(end):
        raise GridError("slot_misaligned")
    day = tz.business_date(start)
    if tz.at(day, DAY_START) > start or end > tz.at(day, DAY_END):
        raise GridError("slot_out_of_grid")
    slots = []
    current = start
    while current < end:
        slots.append(current)
        current += SLOT
    return slots


def wall_interval_slots(day: date, start: time, end: time) -> list[datetime]:
    """`interval_slots` for an `HH:MM`–`HH:MM` interval of a template day."""
    if not wall_on_grid(start) or not wall_on_grid(end) or end <= start:
        raise GridError("slot_misaligned")
    if start < DAY_START or end > DAY_END:
        raise GridError("slot_out_of_grid")
    return interval_slots(tz.at(day, start), tz.at(day, end))


def parse_wall(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))
