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
    checkAdmins(commands.botHelp),
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
    checkAdmins(download.handler.addFile),
    document | media
))
app.add_handler(CallbackQueryHandler(download.manager.stopDownload))

app.start()
logging.info("Bot started!")
logging.info("Press CTRL+\\ to stop...")

t = Thread(target=download.manager.run)
t.start()
idle()
t.join()

app.stop()
