import logging
import os
from distutils.util import strtobool

from . import BASE_FOLDER

_dfolder: str = ''
_dautofolder: bool = False
allow_root_folder: bool = strtobool(os.getenv('ALLOW_ROOT_FOLDER', True))

keepcharacters = (' ', '.', '_', 'à', 'è', 'ì', 'ò', 'ù')


def set(f: str):
    global _dfolder
    _dfolder = f


def get() -> str:
    return _dfolder


def autofolder(value: bool = None) -> bool:
    global _dautofolder
    if value is not None:
        _dautofolder = value
    return _dautofolder


def get_curdir_folders():
    folders = []
    for entry in os.scandir(os.path.join(BASE_FOLDER, _dfolder)):
        if entry.is_dir():
            folders.append(entry.name)
    return folders


def mkdir(new_folder):
    new_folder = os.path.join(BASE_FOLDER, new_folder)
    try:
        os.mkdir(new_folder)
        logging.info(f"New folder created: {new_folder}")
    except FileExistsError:
        pass
    except Exception as err:
        text = f"Failed to create folder: {err}"
        logging.warning(text)
        return False, text
    return True, ''


def clean_folder_name(foldern_name: str) -> str:
    foldern_name = "".join(c for c in foldern_name if c.isalnum() or c in keepcharacters)
    return foldern_name
