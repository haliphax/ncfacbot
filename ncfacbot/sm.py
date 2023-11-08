"Sorcerers Might countdown command"

# stdlib
import asyncio as aio
from datetime import datetime, timezone, timedelta
from math import ceil
import typing

# api
from aethersprite import data_folder, log
from aethersprite.authz import channel_only
from aethersprite.common import FakeContext
from aethersprite.emotes import THUMBS_DOWN
from aethersprite.filters import ChannelFilter, RoleFilter
from aethersprite.settings import register, settings

# 3rd party
from discord.abc import GuildChannel
from discord.ext.commands import Bot, check, command, Context
from sqlitedict import SqliteDict

bot: Bot

# constants
SM_LIMIT = 100
# filters
channel_filter = ChannelFilter("sm.channel")
# database
schedule = SqliteDict(f"{data_folder}sm.sqlite3", tablename="announce", autocommit=True)


class SMSchedule:
    """Sorcerer's Might expiry announcement schedule"""

    def __init__(self, user: str, nick: str, channel: str, schedule: datetime):
        #: The full user name
        self.user = user
        #: The user's nick/name
        self.nick = nick
        #: The channel where the request was made
        self.channel = channel
        #: The time to announce
        self.schedule = schedule

    def __repr__(self):
        return (
            f"<SMSchedule user='{self.user}' nick='{self.nick}' "
            f"channel={self.channel} schedule={self.schedule}>"
        )


def _done(bot: Bot, guild: str, channel: str, user: str, nick: str):
    """Countdown completed callback"""

    loop = aio.get_event_loop()
    int_guild = int(guild)
    fake_ctx = None

    try:
        fake_ctx = FakeContext(guild=[g for g in bot.guilds if g.id == int_guild][0])
    except IndexError:
        # guild isn't registered with this bot; remove it
        log.warn(f"Removing missing guild {guild}")
        del schedule[guild]

        return

    try:
        role: str | None = settings["sm.medicrole"].get(fake_ctx)
        chan: str | None = settings["sm.channel"].get(fake_ctx)

        msg = ":adhesive_bandage: "

        # determine the announcement channel
        if chan is None:
            chan = channel

        # get the medic role, if any
        try:
            medic = [r for r in fake_ctx.guild.roles if r.name in role]
            msg += f'{" ".join([m.mention for m in medic])} '
        except IndexError:
            pass
        except TypeError:
            pass

        msg += f"Sorcerers Might ended for {nick}!"
        chan = chan.lower().strip()

        try:
            where = [c for c in fake_ctx.guild.channels if c.name.lower() == chan][0]
            # ctx.send is a coroutine, but we're in a plain function, so we
            # have to wrap the call to ctx.send in a Task
            loop.create_task(where.send(msg))
            log.info(f"{user} completed SM countdown")
        except IndexError:
            log.error(f"Unable to announce SM countdown for {nick} in {chan}")

            return
    finally:
        if guild in schedule and user in schedule[guild]:
            s = schedule[guild]
            del s[user]
            schedule[guild] = s

        sm_alerts: dict = getattr(bot, "sm_alerts")
        cd = sm_alerts[guild]
        del cd[user]
        sm_alerts[guild] = cd
        setattr(bot, "sm_alerts", sm_alerts)


async def on_ready():
    global bot

    """Schedule SMSchedule from database; immediately announce those missed"""

    if hasattr(bot, "__sm_ready__"):
        return

    setattr(bot, "__sm_ready__", None)
    # Use bot property to store alerts; easy way to ensure it is atomic
    setattr(bot, "sm_alerts", {})

    now = datetime.now(timezone.utc)
    loop = aio.get_event_loop()

    for gid, guild in schedule.items():
        for _, sched in guild.items():
            if sched.schedule <= now:
                log.info(f"Immediately calling SM expiry for {sched.user}")
                _done(bot, gid, sched.channel, sched.user, sched.nick)
            else:
                log.info(f"Scheduling SM expiry for {sched.user}")
                diff = (sched.schedule - now).total_seconds()
                h = loop.call_later(
                    diff, _done, bot, gid, sched.channel, sched.user, sched.nick
                )

                sm_alerts: dict = getattr(bot, "sm_alerts")
                if not gid in sm_alerts:
                    sm_alerts[gid] = {}

                gcd = sm_alerts[gid]
                gcd[sched.user] = (sched.schedule, h)
                sm_alerts[gid] = gcd
                setattr(bot, "sm_alerts", sm_alerts)


@command(brief="Start a Sorcerers Might countdown", name="sm")
@check(channel_only)
async def sm(ctx: Context, n: typing.Optional[int] = None):
    """
    Start a Sorcerers Might countdown for n minutes

    You may also use a value of 0 to cancel the countdown. If no value is provided, the remaining time of the countdown will be shown.

    Values of n up to 100 are allowed.
    """

    assert isinstance(ctx.channel, GuildChannel)
    assert ctx.guild
    author = str(ctx.author)
    guild = str(ctx.guild.id)
    loop = aio.get_event_loop()
    nick = ctx.author.display_name
    now = datetime.now(timezone.utc)
    sm_alerts: dict = getattr(ctx.bot, "sm_alerts")

    if n is None:
        # report countdown status
        if not guild in sm_alerts or author not in sm_alerts[guild]:
            await ctx.send(
                ":person_shrugging: " "You do not currently have a countdown."
            )

            return

        cd = sm_alerts[guild][author]

        # get remaining time
        remaining = (cd[0] - now).total_seconds() / 60

        if remaining > 1:
            remaining = ceil(remaining)

        remaining = int(remaining)
        minutes = "minutes" if remaining > 1 else "minute"

        if remaining < 1:
            await ctx.send(":open_mouth: Less than 1 minute remaining!")
        else:
            await ctx.send(f":stopwatch: About {remaining} {minutes} to go.")

        log.info(
            f"{ctx.author} checking SM status: "
            f'{"<1" if remaining < 1 else remaining} {minutes}'
        )

        return

    minutes = "minutes" if n > 1 else "minute"

    if n > SM_LIMIT:
        # let's not be silly, now
        await ctx.message.add_reaction(THUMBS_DOWN)
        log.warn(
            f"{ctx.author} made rejected SM countdown request of {n} " f"{minutes}"
        )

        return

    if guild in sm_alerts:
        gcd = sm_alerts[guild]

        if author in gcd:
            # cancel callback and remove schedule
            cd = sm_alerts[guild][author]
            cd[1].cancel()
            del gcd[author]
            sm_alerts[guild] = gcd
            setattr(ctx.bot, "sm_alerts", sm_alerts)

            try:
                s = schedule[guild]
                del s[author]
                schedule[guild] = s
            except KeyError:
                pass

            await ctx.send(
                ":negative_squared_cross_mark: " "Your countdown has been canceled."
            )
            log.info(f"{ctx.author} canceled SM countdown")

            # if no valid duration supplied, we're done
            if n < 1:
                return

    if n < 1:
        await ctx.send(":person_shrugging: " "You do not currently have a countdown.")
        log.warn(f"{ctx.author} failed to cancel nonexistent SM countdown")

        return

    output = (
        f":alarm_clock: Starting a Sorcerers Might countdown for {n} " f"{minutes}."
    )
    sm_end = (
        now
        + timedelta(minutes=n)
        - timedelta(seconds=now.second, microseconds=now.microsecond)
    )

    # store countdown reference in database
    if not guild in schedule:
        # first time; make a space for this server
        schedule[guild] = {}

    sched = schedule[guild]
    sched[author] = SMSchedule(
        author, nick, ctx.channel.name, sm_end + timedelta(minutes=1)
    )
    schedule[guild] = sched

    # set timer for countdown completed callback
    if guild not in sm_alerts:
        sm_alerts[guild] = {}

    gcd = sm_alerts[guild]
    gcd[author] = (
        sm_end,
        loop.call_later(
            60 * (n + 1), _done, ctx.bot, guild, ctx.channel.name, author, nick
        ),
    )
    sm_alerts[guild] = gcd
    setattr(ctx.bot, "sm_alerts", sm_alerts)
    await ctx.send(output)
    log.info(f"{ctx.author} started SM countdown for {n} {minutes}")


medic_filter = RoleFilter("sm.medicrole")


async def setup(bot_: Bot):
    global bot

    bot = bot_

    # settings
    register(
        "sm.medicrole",
        None,
        lambda x: True,
        False,
        "The Discord server role(s) used for announcing SM countdown "
        "expirations. Will be suppressed if it doesn't exist.",
        filter=medic_filter,
    )
    register(
        "sm.channel",
        None,
        lambda x: True,
        False,
        "The channel where SM countdown expiry announcements will be "
        "posted. If set to the default, they will be announced in the "
        "same channel where they were last manipulated (per-user).",
        filter=channel_filter,
    )

    bot.add_listener(on_ready)
    bot.add_command(sm)


async def teardown(bot: Bot):
    global settings

    for k in ("sm.medicrole", "sm.channel"):
        del settings[k]

    bot.remove_listener(on_ready)
