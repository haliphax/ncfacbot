"""Safe contents commands"""

# stdlib
from functools import partial
from os import environ
from os.path import dirname, join, realpath
import re

# 3rd party
from discord.ext.commands import Bot, Cog, command, Context
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from sqlitedict import SqliteDict

# api
from aethersprite import config, data_folder, log
from aethersprite.authz import channel_only, require_roles_from_setting
from aethersprite.common import FakeContext
from aethersprite.filters import RoleFilter
from aethersprite.settings import register, settings

MAX_ITEMS_PER_MESSAGE = 20
"""Maximum number of items listed per Discord message to avoid rejection"""

SPELLS_PATTERN = r"([- a-zA-Z0-9]+) - Small \w+ Gem, (\d+) shots \((\d+)\)"
"""Regex for splitting apart spell gem text"""

COUNTS_PATTERN = r"\((\d+)\)"
"""Regex for getting counts from potions, etc."""

SCRIPT_URL = config.get("ncfacbot", {}).get(
    "safe_contents_script",
    environ.get(
        "SAFE_CONTENTS_SCRIPT",
        "https://shazbot.oddnetwork.org/nexusclash.safe/static/nc-safe-report.user.js",
    ),
)
"""URL for UserScript, if any"""

README_URL = config.get("ncfacbot", {}).get(
    "safe_contents_readme",
    environ.get(
        "SAFE_CONTENTS_README",
        "https://github.com/haliphax/ncfacbot/blob/main/ncfacbot/safe.md",
    ),
)
"""URL for README, if any"""

authz_safe = partial(require_roles_from_setting, setting="safe.roles")
router = APIRouter(prefix="/nexusclash.safe")
static = StaticFiles(directory=join(realpath(dirname(__file__)), "web"))


def _get_database():
    """Helper function to get a database reference"""

    return SqliteDict(
        f"{data_folder}safe.sqlite3", tablename="contents", autocommit=True
    )


class Safe(Cog, name="safe"):
    """Safe contents commands"""

    _safe = _get_database()

    _icons = {
        "Components": "tools",
        "Potions": "test_tube",
        "Spells": "mage",
    }
    """Emoji to use when displaying lists"""

    async def _get(self, ctx: Context, kind: str):
        """Helper function for retrieving item lists"""

        assert ctx.guild

        if settings["safe.key"].get(ctx) is None:
            await ctx.send(":thumbsdown: No UserScript key has been set.")
            log.warn("No UserScript key is set for this guild")

            return

        guild = str(ctx.guild.id)
        await ctx.send(f":{self._icons[kind]}: **{kind}**")
        msg = []
        items = []
        count = 0

        if guild in self._safe:
            items += self._safe[guild][kind]

        if not items:
            await ctx.send("> _None_")
        else:
            for i in items:
                msg.append(f"- {i}")
                count += 1

                if count % MAX_ITEMS_PER_MESSAGE == 0:
                    await ctx.send(">>> " + "\n".join(msg))
                    msg = []

        if len(msg):
            await ctx.send(">>> " + "\n".join(msg))

    @command(name="safe.help")
    async def help(self, ctx):
        """View README for information about safe contents UserScript"""

        await ctx.send(f":information_source: <{README_URL}>")
        log.info(f"{ctx.author} viewed safe README info")

    @command()
    async def potions(self, ctx):
        """Lists potions in the faction safe"""

        await self._get(ctx, "Potions")
        log.info(f"{ctx.author} viewed list of potions")

    @command(name="safe.script")
    async def script(self, ctx):
        """Get URL for the UserScript to report safe contents"""

        await ctx.send(f":space_invader: <{SCRIPT_URL}>")
        log.info(f"{ctx.author} viewed URL for UserScript")

    @command()
    async def spells(self, ctx):
        """Lists spell gems in the faction safe"""

        await self._get(ctx, "Spells")
        log.info(f"{ctx.author} viewed list of spells")

    @command()
    async def components(self, ctx):
        """Lists components in the faction safe"""

        await self._get(ctx, "Components")
        log.info(f"{ctx.author} viewed list of components")


roles_filter = RoleFilter("safe.roles")


def _settings():
    """Helper function for registering settings"""

    if "safe.key" in settings:
        return

    register(
        "safe.key",
        None,
        lambda x: True,
        False,
        "The key used by the UserScript for reporting.",
    )
    register(
        "safe.roles",
        None,
        lambda x: True,
        False,
        "The server roles that are allowed to view safe contents. If "
        "unset, there are no restrictions. Separate multiple entries "
        "with commas.",
        filter=roles_filter,
    )


async def setup(bot: Bot):
    _settings()
    cog = Safe(bot)

    for c in cog.get_commands():
        c.add_check(authz_safe)
        c.add_check(channel_only)

    await bot.add_cog(cog)


async def teardown(bot: Bot):
    global settings

    for k in (
        "safe.key",
        "safe.roles",
    ):
        del settings[k]


@router.post("/post")
async def http_safe(request: Request):
    """Post safe contents from UserScript"""

    from flask import current_app

    def get_spell_text(spell, counts):
        """Helper function to get spell output"""

        total = sum(counts)
        shots_txt = ", ".join([str(c) for c in counts])

        return f"{spell} **({total})** ||[{shots_txt}]||"

    db = getattr(current_app, "ext_safe_db")
    data = await request.json()

    for k in ("guild", "items", "key"):
        if k not in data:
            raise HTTPException(400)

    guild = data["guild"]
    ctx = FakeContext(guild={"id": guild})
    key = settings["safe.key"].get(ctx)  # type: ignore

    if key is None:
        raise HTTPException(401)

    if key != data["key"]:
        raise HTTPException(403)

    # massage/validate data
    for category in (
        "Potion",
        "Spell",
    ):
        items = data["items"][category]

        if len(items) == 0:
            continue

        # ignore spell/potion blind item reports
        if items[0] == "0":
            try:
                data["items"][category] = db[guild][category]
            except KeyError:
                data["items"][category] = []

        # clean up spell listings
        elif category == "Spell":
            cleaned = []
            counts = [0, 0, 0, 0, 0, 0]
            last_gem = None
            items_len = len(items)

            for idx in range(items_len):
                eol = idx == items_len - 1
                item = items[idx]
                m = re.search(SPELLS_PATTERN, item)
                assert m
                groups = m.groups()
                spell = groups[0]
                shots = int(groups[1])
                count = int(groups[2])

                if last_gem != spell and last_gem is not None:
                    cleaned.append(get_spell_text(last_gem, counts))
                    counts = [0, 0, 0, 0, 0, 0]
                    counts[shots] = count
                else:
                    counts[shots] += count

                if eol:
                    cleaned.append(get_spell_text(spell, counts))

                last_gem = spell

            d = data["items"]
            d["Spell"] = cleaned
            data["items"] = d

        # add icons to potion listings
        elif category == "Potion":
            updated = []

            for item in data["items"][category]:
                icon = ":green_circle:"
                m = re.search(COUNTS_PATTERN, item)
                assert m
                count = int(m.groups()[0])

                if count < 12:
                    icon = ":red_circle:"
                elif count < 24:
                    icon = ":yellow_circle:"

                updated.append(" ".join((icon, item)))

            d = data["items"]
            d["Potion"] = updated
            data["items"] = d

    db[guild] = {
        "Potions": data["items"]["Potion"],
        "Spells": data["items"]["Spell"],
        "Components": data["items"]["Component"],
    }

    return "", 200


def setup_webapp(app: FastAPI, _):
    """Web application setup"""

    _settings()
    db = _get_database()
    setattr(app, "ext_safe_db", db)
    app.mount(f"{router.prefix}/static", static)
    app.include_router(router)
