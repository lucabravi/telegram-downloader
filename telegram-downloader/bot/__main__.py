import logging
from threading import Thread

from pyrogram import idle
from pyrogram.filters import command, document, media
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler
from pyrogram.handlers.message_handler import MessageHandler

from . import app, commands, download
from .util import checkAdmins

app.add_handler(MessageHandler(
    checkAdmins(commands.start),
    command('start')
))
app.add_handler(MessageHandler(
    checkAdmins(commands.bot_help),
    command('help')
))
app.add_handler(MessageHandler(
    checkAdmins(commands.usage),
    command('usage')
))
app.add_handler(MessageHandler(
    checkAdmins(commands.use_folder),
    command('cd')
))

app.add_handler(MessageHandler(
    checkAdmins(commands.use_autofolder),
    command('autofolder')
))

app.add_handler(MessageHandler(
    checkAdmins(download.handler.addFile),
    document | media
))

from pyrogram import filters

def dynamic_data_filter(data):
    async def func(flt, _, query: str):
        return  query.data.startswith(flt.data )

    # "data" kwarg is accessed with "flt.data" above
    return filters.create(func, data=data)


app.add_handler(CallbackQueryHandler(download.manager.stopDownload, filters=dynamic_data_filter('stop')))
app.add_handler(CallbackQueryHandler(download.manager.cd, filters=dynamic_data_filter('cd')))



app.start()
logging.info("Bot started!")
logging.info("Press CTRL+Z to stop...")

t = Thread(target=download.manager.run)
t.start()
idle()
t.join()

app.stop()
