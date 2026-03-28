import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = REPO_ROOT / "telegram-downloader" / "bot"


def _clear_test_modules():
    for name in list(sys.modules):
        if name == "bot" or name.startswith("bot."):
            sys.modules.pop(name, None)
        if name == "pyrogram" or name.startswith("pyrogram."):
            sys.modules.pop(name, None)
        if name == "requests":
            sys.modules.pop(name, None)


def _install_stub_requests():
    requests_module = types.ModuleType("requests")

    class Response:
        def __init__(self, status_code=200):
            self.status_code = status_code
            self.headers = {}

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        def __init__(self, message="", response=None):
            super().__init__(message)
            self.response = response

    class Timeout(RequestException):
        pass

    class ConnectionError(RequestException):
        pass

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, *_args, **_kwargs):
            raise NotImplementedError("Session.get should be monkeypatched in tests")

    def get(*_args, **_kwargs):
        raise NotImplementedError("requests.get should be monkeypatched in tests")

    requests_module.Response = Response
    requests_module.RequestException = RequestException
    requests_module.HTTPError = HTTPError
    requests_module.Timeout = Timeout
    requests_module.ConnectionError = ConnectionError
    requests_module.Session = Session
    requests_module.get = get
    sys.modules["requests"] = requests_module


def _install_stub_pyrogram():
    pyrogram_module = types.ModuleType("pyrogram")
    pyrogram_module.__path__ = []
    sys.modules["pyrogram"] = pyrogram_module

    enums_module = types.ModuleType("pyrogram.enums")

    class ParseMode:
        MARKDOWN = "markdown"

    enums_module.ParseMode = ParseMode
    sys.modules["pyrogram.enums"] = enums_module

    types_module = types.ModuleType("pyrogram.types")

    class Message:
        pass

    class CallbackQuery:
        pass

    class InlineKeyboardButton:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    types_module.Message = Message
    types_module.CallbackQuery = CallbackQuery
    types_module.InlineKeyboardButton = InlineKeyboardButton
    types_module.InlineKeyboardMarkup = InlineKeyboardMarkup
    sys.modules["pyrogram.types"] = types_module


def _install_stub_bot_package():
    bot_module = types.ModuleType("bot")
    bot_module.__path__ = [str(BOT_ROOT)]
    bot_module.app = types.SimpleNamespace(max_concurrent_transmissions=3)
    sys.modules["bot"] = bot_module

    download_module = types.ModuleType("bot.download")
    download_module.__path__ = [str(BOT_ROOT / "download")]
    sys.modules["bot.download"] = download_module

    util_module = types.ModuleType("bot.util")
    util_module.dedent = lambda text: text.strip("\n")
    util_module.human_readable = lambda value: f"{value:.2f} B"
    sys.modules["bot.util"] = util_module

    rate_limiter_module = types.ModuleType("bot.rate_limiter")

    async def catch_rate_limit(*_args, **_kwargs):
        return None

    async def enqueue_message(*_args, **_kwargs):
        return None

    rate_limiter_module.catch_rate_limit = catch_rate_limit
    rate_limiter_module.enqueue_message = enqueue_message
    rate_limiter_module.last_sent_message_id = {}
    sys.modules["bot.rate_limiter"] = rate_limiter_module

    manage_path_module = types.ModuleType("bot.manage_path")
    manage_path_module.BASE_FOLDER = "/tmp"

    class VirtualFileSystem:
        pass

    manage_path_module.VirtualFileSystem = VirtualFileSystem
    sys.modules["bot.manage_path"] = manage_path_module


def _load_module(full_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_download_modules():
    _clear_test_modules()
    _install_stub_requests()
    _install_stub_pyrogram()
    _install_stub_bot_package()

    animeunity = _load_module("bot.download.animeunity", BOT_ROOT / "download" / "animeunity.py")
    download_type = _load_module("bot.download.type", BOT_ROOT / "download" / "type.py")
    manager = _load_module("bot.download.manager", BOT_ROOT / "download" / "manager.py")
    return {
        "animeunity": animeunity,
        "type": download_type,
        "manager": manager,
    }
