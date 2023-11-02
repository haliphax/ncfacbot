"""Nexus Clash extensions module"""

# stdlib
import calendar
from datetime import datetime, timezone

# 3rd party
from aethersprite.common import FIFTEEN_MINS


def discord_timestamp(dt: datetime):
    """
    Format output as Discord timestamp.

    :param dt: The datetime object to format
    :returns: A formatted Discord timestamp string
    """

    stamp = calendar.timegm(dt.timetuple())

    return f"<t:{stamp}>"


def get_next_tick(n=1):
    """
    Calculate future tick as datetime in GMT.

    :param n: The number of ticks forward to calculate
    :type n: int
    :returns: The time of the calculated tick
    :rtype: datetime
    """

    now = calendar.timegm(datetime.now(timezone.utc).timetuple())
    tick_stamp = (now + (n * FIFTEEN_MINS)) - (now % FIFTEEN_MINS)

    return datetime.fromtimestamp(tick_stamp, tz=timezone.utc)
