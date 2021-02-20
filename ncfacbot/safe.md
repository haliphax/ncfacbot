# Discord Bot Safe Contents

## Introduction

The `safe` commands collection allows people to view the contents of the
faction safe from within Discord. This data has to come from Nexus Clash
itself, however, and so a bridge is required. That bridge comes in the form
of a [UserScript] that executes some code from a user's web browser when a
specific page or set of pages is visited. (In our case, that page is the main
Nexus Clash interface.)

## Installation and configuration

You will first need a UserScript manager. [TamperMonkey] is generally best,
though GreaseMonkey should work well enough. Once you have it installed,
the installation prompt should appear as soon as you visit the URL for the
[Safe Contents UserScript]. The script is also served by the bot's web
application back-end, and its URL can be requested with the `safe.script`
command.

Once you have installed the script _and you are in your faction stronghold_,
you should see a small icon next to your user profile link in the page header
that looks like a cartoon speech bag. Clicking this will prompt for your
Discord guild ID and your faction's secret key. The guild ID can be found
by using the Discord webapp and opening a channel in your faction's Discord
server. The first set of numbers is your faction ID. Everything after the
forward slash proceeding the first set of numbers is the channel ID, and can
be ignored. As for the secret key... ask your Discord server admins/mods.


[Safe Contents UserScript]: ../webapp/static/nc-safe-report.user.js
[TamperMonkey]: https://www.tampermonkey.net/
[UserScript]: https://en.wikipedia.org/wiki/Userscript
