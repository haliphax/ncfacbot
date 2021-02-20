"Load all command extensions"

from . import __all__ as _mods

META_EXTENSION = True

_package = __name__.replace('._all', '')


def setup(bot):
    for m in _mods:
        bot.load_extension(f'{_package}.{m}')


def teardown(bot):
    for m in _mods:
        bot.unload_extension(f'{_package}.{m}')
