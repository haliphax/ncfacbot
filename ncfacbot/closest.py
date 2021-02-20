"Closest tick calculator command"

# stdlib
from datetime import datetime, timedelta, timezone
from math import ceil
import typing
# 3rd party
from aethersprite import log
from aethersprite.common import (DATETIME_FORMAT, get_timespan_chunks, MINUTE,
                                 THUMBS_DOWN,)
from discord.ext.commands import command
# local
from . import get_next_tick


@command(brief='Get closest tick to time offset')
async def closest(ctx, *, offset: typing.Optional[str]):
    """
    Get closest tick to time offset

    Displays the GMT time of the closest tick which occurs after the provided offset. If no values are provided, the next tick is shown.

    Example: !closest 2h 15m  <-- shows the closest tick 2 hours and 15 minutes from now
    """

    delta = get_timespan_chunks(offset) if offset else (0, 0, 0)

    for val in delta:
        if val < 0:
            # negative numbers are a no-no
            await ctx.message.add_reaction(THUMBS_DOWN)
            log.warn(f'{ctx.author} made rejected closest request of {delta}')
            return

    days, hours, minutes = delta
    future_tick = get_next_tick()
    diff = future_tick - datetime.now(timezone.utc)
    diff_minutes = ceil(diff.total_seconds() / MINUTE)

    if days >= 1 or hours >= 1 or minutes > diff_minutes:
        # only bother calculating future tick if it's not the next one
        tick_offset = minutes - (minutes % 15) + 15
        future_tick += timedelta(days=days, hours=hours, minutes=tick_offset)

    tick_str = future_tick.strftime(DATETIME_FORMAT)

    await ctx.send(f':dart: {tick_str}')
    log.info(f'{ctx.author} requested closest tick {delta}: {tick_str}')


def setup(bot):
    bot.add_command(closest)
