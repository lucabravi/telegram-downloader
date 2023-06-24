import logging
from threading import Thread

from pyrogram import idle
from pyrogram.filters import command, document, media
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler
from pyrogram.handlers.message_handler import MessageHandler

from . import app, commands, download
from .util import check_admins

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
    check_admins(commands.create_folder),
    command('mkdir')
))

# endregion MANAGE PATH COMMANDS

# region GET MEDIA
app.add_handler(MessageHandler(
    check_admins(download.handler.addFile),
    document | media
))
# endregion GET MEDIA

from pyrogram import filters


def switch_callback(data):
    async def func(flt, _, query):
        return query.data.startswith(flt.data)

    # "data" kwarg is accessed with "flt.data" above
    return filters.create(func, data=data)


app.add_handler(CallbackQueryHandler(download.manager.stopDownload, filters=switch_callback('stop')))
app.add_handler(CallbackQueryHandler(download.manager.cd, filters=switch_callback('cd')))

app.start()
logging.info("Bot started!")
logging.info("Press CTRL+Z to stop...")

t = Thread(target=download.manager.run)
t.start()
idle()
t.join()

app.stop()
