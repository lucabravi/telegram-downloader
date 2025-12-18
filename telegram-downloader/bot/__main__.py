import logging
import asyncio

from pyrogram.filters import command, document, media
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler
from pyrogram.handlers.message_handler import MessageHandler

from . import app, commands, download
from .util import check_admins, check_admins_callback
from .db import create_tables

# region BASIC COMMANDS
app.add_handler(MessageHandler(
    check_admins(commands.start),
    command('start')
))
app.add_handler(MessageHandler(
    check_admins(commands.bot_help),
    command('help')
))
# endregion BASIC COMMANDS

# region STATS COMMANDS
app.add_handler(MessageHandler(
    check_admins(commands.usage),
    command('usage')
))
# endregion STATS COMMANDS

# region MANAGE PATH COMMANDS
app.add_handler(MessageHandler(
    check_admins(commands.change_folder),
    command('cd')
))

app.add_handler(MessageHandler(
    check_admins(commands.use_autofolder),
    command('autofolder')
))

app.add_handler(MessageHandler(
    check_admins(commands.use_autoname),
    command('autoname')
))

app.add_handler(MessageHandler(
    check_admins(commands.create_folder),
    command('mkdir')
))

app.add_handler(MessageHandler(
    check_admins(commands.show_folder),
    command('ls')
))
# endregion MANAGE PATH COMMANDS

# region GET MEDIA
app.add_handler(MessageHandler(
    check_admins(download.handler.add_file),
    document | media
))
# endregion GET MEDIA

from pyrogram import filters


def switch_callback(data):
    async def func(flt, _, query):
        return query.data.startswith(flt.data)

    # "data" kwarg is accessed with "flt.data" above
    return filters.create(func, data=data)


app.add_handler(CallbackQueryHandler(check_admins_callback(download.manager.stopDownload), filters=switch_callback('stop')))
app.add_handler(CallbackQueryHandler(check_admins_callback(download.manager.cd), filters=switch_callback('cd')))

app.start()
logging.info("Bot started!")
logging.info("Press CTRL+Z to stop...")

loop = asyncio.get_event_loop()

loop.create_task(create_tables())

loop.create_task(download.manager.run())
loop.run_forever()
loop.close()

app.stop()
