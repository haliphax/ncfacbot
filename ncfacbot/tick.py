"Next game tick command"

# stdlib
from datetime import datetime, timezone
from random import randrange
import typing

# 3rd party
from aethersprite import log
from aethersprite.common import DATETIME_FORMAT, seconds_to_str, THUMBS_DOWN
from discord.ext.commands import Bot, command, Context

# local
from . import discord_timestamp, get_next_tick

#: Future/past tick limit
TICK_LIMIT = 1000
#: Silly stuff to say for past ticks
SILLY = (
    ", when the west was still wild...",
    ", when I was a younger bot and still had all my wits about me!",
    "... in the before-time, the long-long-ago.",
    ", if you can believe that!",
    ", okay?",
    "! You remember that?! Man, those were some good times.",
)
SILLY_LEN = len(SILLY)


@command(brief="Next game tick or time [n] ticks from now")
async def tick(ctx: Context, n: typing.Optional[int] = 1):
    """
    Next game tick or time [n] ticks from now in GMT

    Show the next game tick in GMT. Provide a value for <n> to get the GMT timestamp of <n> ticks from now. For past ticks, use a negative number.

    Values of n between -1000 and 1000 are allowed.
    """

    assert n
    if -TICK_LIMIT > n or n > TICK_LIMIT:
        # let's not be silly, now
        await ctx.message.add_reaction(THUMBS_DOWN)
        log.warn(f"{ctx.author} made rejected next tick request of {n}")
        return

    future_tick = get_next_tick(n)
    tick_str = f"{discord_timestamp(future_tick)} - "
    until = ""

    if n >= 0:
        until = seconds_to_str(
            (future_tick - datetime.now(timezone.utc)).total_seconds()
        )

        if len(until):
            until += " from now"
        else:
            until = "right now!"

    elif n < 0:
        until = seconds_to_str(
            (datetime.now(timezone.utc) - future_tick).total_seconds()
        )
        until += " before now" + SILLY[randrange(SILLY_LEN)]

    tick_str += until
    await ctx.send(f":calendar: {tick_str}")
    log.info(f"{ctx.author} requested next tick: {tick_str}")


async def setup(bot: Bot):
    bot.add_command(tick)
