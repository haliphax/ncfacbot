"Raid scheduling/announcing command"

# stdlib
import asyncio as aio
from datetime import datetime, timedelta, timezone
from functools import partial
import math
import time
# 3rd party
from discord import Embed
from discord.colour import Colour
from discord.ext.commands import check, Cog, command
from sqlitedict import SqliteDict
# api
from aethersprite import data_folder, log
from aethersprite.authz import channel_only, require_roles_from_setting
from aethersprite.common import FakeContext, seconds_to_str, THUMBS_DOWN
from aethersprite.filters import ChannelFilter, RoleFilter
from aethersprite.settings import register, settings
# local
from . import discord_timestamp

#: Expected format for schedule input
INPUT_FORMAT = '%Y-%m-%d %H:%M %z'
#: No raid message
MSG_NO_RAID = ':person_shrugging: There is no scheduled raid.'

# authz decorators
authz_schedule = partial(require_roles_from_setting,
                         setting='raid.scheduleroles')
authz_check = partial(require_roles_from_setting,
                      setting=('raid.scheduleroles', 'raid.checkroles'))


class RaidSchedule(object):

    "Raid schedule; tracks target, time, leader, and channel"

    #: Time of the raid
    schedule = None
    #: The target to raid
    target = None

    def __init__(self, guild, leader, channel):
        #: The guild that owns the raid
        self.guild = int(guild)
        #: Who set the target/schedule
        self.leader = leader
        #: Channel where the last manipulation was done
        self.channel = channel

    def __repr__(self):
        return (f'<RaidSchedule guild={self.guild} target="{self.target}" '
                f'schedule={self.schedule}>')


class Raid(Cog, name='raid'):

    """
    Raid commands

    NOTE: A raid will not actually be scheduled until both a schedule AND a target have been set. Until then, check and cancel commands will get a "There is no scheduled raid" message.
    """

    _schedules = SqliteDict(f'{data_folder}raid.sqlite3', tablename='schedule',
                            autocommit=True)
    _handles = {}

    def __init__(self, bot):
        self.bot = bot

    def _reset(self, guild):
        "Delete schedule, handle, etc. and reset raid"

        if guild in self._handles:
            self._handles[guild].cancel()
            del self._handles[guild]

        if guild in self._schedules:
            del self._schedules[guild]

    async def _go(self, raid, ctx, silent=False):
        "Helper method for scheduling announcement callback"

        loop = aio.get_event_loop()
        channel = settings['raid.channel'].get(ctx)

        if channel is None:
            channel = raid.channel

        c = None

        try:
            c = [c for c in ctx.guild.channels if c.name == channel][0]
        except IndexError:
            log.error(f'Unable to find channel {channel} to announce raid')

            return False

        def reminder1():
            loop.create_task(
                c.send(f':stopwatch: @everyone '
                       f'**Reminder:** Raid on {raid.target} @ '
                       f'{discord_timestamp(raid.schedule)}! '
                       f'(in 8 hours)'))
            log.info(f'8 hour reminder for {raid.target} @ '
                     f'{raid.schedule}')
            next = datetime.timestamp(raid.schedule - timedelta(minutes=30))
            self._handles[ctx.guild.id] = loop.call_at(next, reminder2)
            log.info('Scheduled 30 minute reminder')

        def reminder2():
            loop.create_task(
                c.send(f':stopwatch: @here '
                       f'**Reminder:** Raid on {raid.target} in 30 minutes!'))
            log.info(f'30 minute reminder for {raid.target} @ '
                     f'{raid.schedule}')
            next = datetime.timestamp(raid.schedule)
            self._handles[ctx.guild.id] = loop.call_at(next, announce)
            log.info('Scheduled announcement')

        def announce():
            loop.create_task(
                c.send(f':crossed_swords: @everyone '
                       f'**Time to raid {raid.target}!**'))
            log.info(f'Announcement for {raid.target}')
            self._reset(ctx.guild.id)

        if raid.target is None or raid.schedule is None:
            return True

        wait = (raid.schedule - datetime.now(timezone.utc)).total_seconds()

        if wait <= -86400:
            # more than a day old; drop
            return True

        if wait <= 0:
            # in the past; announce immediately
            announce()

            return True

        existing = self._handles.get(ctx.guild.id, None)

        if existing is not None:
            existing.cancel()

        handle = None

        if wait > 28800:
            handle = loop.call_later(wait - 28800, reminder1)
            log.info(f'Set 8 hour reminder for {raid.target}')
        elif wait > 1800:
            handle = loop.call_later(wait - 1800, reminder2)
            log.info(f'Set 30 minute reminder for {raid.target}')
        else:
            handle = loop.call_later(wait, announce)
            log.info(f'Scheduled announcement for {raid.target}')

        self._schedules[ctx.guild.id] = raid
        self._handles[ctx.guild.id] = handle

        if silent:
            return

        await self.check_(ctx)
        log.info(f'{raid.leader} scheduled raid on {raid.target} @ '
                 f'{raid.schedule}')

    @Cog.listener()
    async def on_ready(self):  # pylint: disable=method-hidden
        "Schedule raid announcements from database on startup"

        if hasattr(self.bot, '__raid_ready__'):
            # only have to do this once during initial startup
            return

        setattr(self.bot, '__raid_ready__', None)

        for gid, raid in self._schedules.items():
            try:
                gid = int(gid)
                ctx = FakeContext([g for g in self.bot.guilds
                                   if g.id == gid][0])
                log.info(raid)
                await self._go(raid, ctx, True)
            except IndexError:
                # unknown guild; delete record
                log.error(f'Unknown guild {gid}')
                del self._schedules[gid]

    @command(name='raid')
    @check(authz_check)
    async def alarm(self, ctx):
        "Raise the raid alarm"

        channel = settings['raid.channel'].get(ctx)
        bumper = ':rotating_light:' * 3
        message = ' '.join((bumper, '@everyone We are being raided!', bumper))
        c = ctx

        try:
            c = [c for c in ctx.guild.channels if c.name == channel][0]
        except IndexError:
            log.warn(f'No match for {channel}')
            # No raid channel configured, send to same channel as command
            pass

        await c.send(f'**{message}**')
        log.info(f'{ctx.author} raised the raid alarm')

    @command(name='raid.cancel')
    @check(authz_schedule)
    async def cancel(self, ctx):
        "Cancels a currently scheduled raid"

        if ctx.guild.id not in self._schedules \
                or self._schedules[ctx.guild.id].target is None:
            await ctx.send(MSG_NO_RAID)
            log.info(f'{ctx.author} attempted to cancel nonexistent raid')

            return

        self._reset(ctx.guild.id)
        await ctx.send(':negative_squared_cross_mark: Raid canceled.')
        log.info(f'{ctx.author} canceled raid')

    @command(name='raid.check')
    @check(authz_check)
    async def check_(self, ctx):
        "Check current raid schedule"

        if ctx.guild.id not in self._schedules:
            await ctx.send(MSG_NO_RAID)

            return

        raid = self._schedules[ctx.guild.id]
        until = seconds_to_str(
            (raid.schedule - datetime.now(timezone.utc)).total_seconds())
        embed = Embed(title='Next raid', colour=Colour.red())
        embed.add_field(name=':dart: Target', value=raid.target)
        embed.add_field(name=':crown: Leader', value=raid.leader)
        embed.add_field(name=':calendar: Schedule',
                        value=discord_timestamp(raid.schedule))
        embed.set_footer(text=f'{until} from now')
        await ctx.send(embed=embed)

    @command(name='raid.schedule', brief='Set raid schedule')
    @check(authz_schedule)
    async def schedule(self, ctx, *, when):
        """
        Set raid schedule to <when>, which must be a valid 24-hour datetime string (e.g. 2020-01-01 23:45). Date is optional; today's date will be the default value. Will be parsed as GMT.

        Examples:

            !raid.schedule 2020-01-01 23:45
            !raid.schedule 23:45
        """

        dt = datetime.now(timezone.utc)
        nick = ctx.author.display_name

        try:
            if '-' in when:
                dt = datetime.strptime(when + ' +0000', INPUT_FORMAT)
            else:
                dt = datetime.strptime(f'{dt.strftime("%Y-%m-%d")} {when} '
                                       '+0000', INPUT_FORMAT)

                if dt < datetime.now(timezone.utc):
                    dt = dt + timedelta(days=1)
        except:
            await ctx.message.add_reaction(THUMBS_DOWN)
            log.warning(f'{ctx.author} provided bad args: {when}')

            return

        raid = self._schedules[ctx.guild.id] \
                if ctx.guild.id in self._schedules \
                else RaidSchedule(ctx.guild.id, nick, ctx.channel.id)
        raid.schedule = dt
        raid.leader = nick
        self._schedules[ctx.guild.id] = raid
        await ctx.send(f':calendar: Schedule set to {discord_timestamp(dt)}.')
        log.info(f'{ctx.author} set raid schedule: {dt}')
        await self._go(raid, ctx)

    @command(name='raid.target')
    @check(authz_schedule)
    async def target(self, ctx, *, target):
        "Set raid target"

        nick = ctx.author.display_name
        raid = self._schedules[ctx.guild.id] \
                if ctx.guild.id in self._schedules \
                else RaidSchedule(ctx.guild.id, nick, ctx.channel.name)
        raid.target = target
        raid.leader = nick
        self._schedules[ctx.guild.id] = raid
        await ctx.send(f':point_right: Target set to {target}.')
        log.info(f'{ctx.author} set raid target: {target}')
        await self._go(raid, ctx)


channel_filter = ChannelFilter('raid.channel')
scheduleroles_filter = RoleFilter('raid.scheduleroles')
checkroles_filter = RoleFilter('raid.checkroles')


def setup(bot):
    # settings
    register('raid.channel', None, lambda x: True, False,
             'The channel where raids will be announced. If set to the '
             'default, they will be announced in the same channel where the '
             'last modification to the target or schedule was made.',
             filter=channel_filter)
    register('raid.scheduleroles', None, lambda x: True, False,
             'The server roles that are allowed to schedule/cancel raids and '
             'set raid targets. If set to the default, there are no '
             'restrictions. Separate multiple entries with commas.',
             filter=scheduleroles_filter)
    register('raid.checkroles', None, lambda x: True, False,
             'The server roles that are allowed to check current raid '
             'schedule and target. If set to the default, there are no '
             'restrictions. Separate multiple entries with commas.',
             filter=checkroles_filter)
    cog = Raid(bot)

    for c in cog.get_commands():
        c.add_check(channel_only)

    bot.add_cog(cog)


def teardown(bot):
    global settings

    for k in ('raid.channel', 'raid.scheduleroles', 'raid.checkroles'):
        del settings[k]
