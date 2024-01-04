# Nexus Clash Faction Bot

An extension pack for the [Aethersprite][] [Discord][] bot aimed at
[Nexus Clash][] factions

![ncfacbot](https://github.com/haliphax/ncfacbot/raw/assets/ncfacbot.jpg)

## 🏃 Installing

First, make a `config.toml` file from the provided `config.example.toml` file,
providing it with your username, API token, and any settings tweaks you wish to
apply.

Then, install the bot package in your Python environment of choice:

```shell
pip install -U 'ncfacbot@git+https://github.com/haliphax/ncfacbot.git'
```

In the same directory as your `config.toml` file:

```shell
python -m aethersprite
```

## 📖 Command categories

These categories (referred to as "Cogs") provide multiple commands.

-   `raid`
    Schedule and announce raids
-   `safe`
    Check stronghold stores of components, potions, and spells
-   `shop`
    Maintain shopping lists for components

## 🎲 Independent commands

-   `sm`
    Sorcerer's Might countdown alarm
-   `tick`
    Time of next tick or _n_ ticks from now

[Aethersprite]: https://github.com/haliphax/aethersprite
[Discord]: https://discord.com
[Nexus Clash]: https://www.nexusclash.com
