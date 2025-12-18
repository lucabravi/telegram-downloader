import os
import re
import logging
from pathlib import PurePath

from . import BASE_FOLDER

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def _env_bool(name: str, default: bool = False) -> bool:
    """
    Lightweight bool parser for env vars. Accepts common truthy strings; falls back to default on missing.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 't', 'yes', 'y', 'on')


# Default must be a string for parser; avoid TypeError when env var is missing.
ALLOW_ROOT_FOLDER = _env_bool('ALLOW_ROOT_FOLDER', default=False)


class VirtualFileSystem:
    '''
    Object that allow the management of a virtual file system avoiding to overcome the root directory assigned
    '''

    def __init__(self, root=BASE_FOLDER):
        self.__root = os.path.abspath(root)
        self.__current_path = self.__root
        self.allow_root_folder = ALLOW_ROOT_FOLDER

    def mkdir(self, directory_name) -> (bool, str):
        '''
        create a new directory in the current path with the name passed by parameter
        :param directory_name:
        '''
        directory_name = self.cleanup_path_name(directory_name)
        if not directory_name:
            info = "Invalid directory name"
            logging.info(info)
            return False, info

        tmp_dir = os.path.join(self.__current_path, directory_name)
        if not PurePath(os.path.abspath(tmp_dir)).is_relative_to(self.__root):
            info = "Cannot go beyond the virtual root directory"
            logging.info(info)
            return False, info

        os.makedirs(tmp_dir, exist_ok=True)
        logging.info(f"Created directory '{directory_name}'")
        return True, directory_name

    def cd(self, directory_name) -> (bool, str):
        '''
        change the current_rel_path to the subdirectory passed by param
        :param directory_name:
        '''
        tmp_dir = os.path.abspath(os.path.join(self.__current_path, directory_name))

        if not os.path.isdir(tmp_dir):
            info = f"Directory '{directory_name}' does not exist or is not accessible"
            logging.info(info)
            return False, info

        if not PurePath(tmp_dir).is_relative_to(self.__root):
            info = "Cannot go beyond the virtual root directory"
            logging.info(info)
            return False, info

        self.__current_path = tmp_dir
        return True, self.current_rel_path

    def abs_cd(self, directory_name) -> (bool, str):
        '''
        change the current_rel_path to the subdirectory passed by param always starting from virtual root
        :param directory_name:
        '''
        tmp_dir = os.path.abspath(os.path.join(self.__root, directory_name))

        if not os.path.isdir(tmp_dir):
            info = f"Directory '{directory_name}' does not exist or is not accessible"
            logging.info(info)
            return False, info

        if not PurePath(tmp_dir).is_relative_to(self.__root):
            info = "Cannot go beyond the virtual root directory"
            logging.info(info)
            return False, info

        self.__current_path = tmp_dir
        return True, self.current_rel_path

    def ls(self) -> (list, list):
        '''
        get two list, one for the subdirectory and one for the files found on the current path
        '''
        directories = []
        files = []
        for item in os.listdir(self.__current_path):
            item_path = os.path.join(self.__current_path, item)
            if os.path.isdir(item_path):
                directories.append(item)
            else:
                files.append(item)
        logging.info(f"Directories: [{','.join(directories)}]")
        logging.info(f"Files: [{','.join(files)}]")
        return directories, files

    @property
    def root(self):
        return self.__root

    @property
    def current_rel_path(self, relative=True) -> str:
        '''
        get current relative path
        '''
        return os.path.relpath(self.__current_path, start=self.__root)

    @property
    def current_abs_path(self, relative=True) -> str:
        '''
        get current absolute path
        '''
        return self.__current_path

    @property
    def current_dir(self) -> str:
        '''
        get current directory
        '''
        return os.path.dirname(self.__current_path)

    def get_current_dir_info(self) -> str:
        '''
        get a string with the current directory subfolders and files
        '''
        directories, files = self.ls()
        return f'''
        ---
        Current directory: {self.current_rel_path}
        Subfolders: {'","'.join(directories)}
        '''

    def relative_to_absolute_path(self, relative_path) -> str:
        '''
        convert a relative path to absolute path
        :param relative_path:
        '''
        return os.path.join(self.__root, relative_path)

    @staticmethod
    def cleanup_path_name(path_name) -> str:
        '''
        clean from special characters the directory passed by param
        :param path_name:
        '''
        # Rimozione dei caratteri proibiti
        path_name = re.sub(r'[<>:\"/\\|?*]', '', path_name)
        # Rimozione dei doppi spazi
        path_name = re.sub(r' +', ' ', path_name)
        # Rimozione degli spazi iniziali e finali
        path_name = path_name.strip()
        return path_name


# vfs = VirtualFileSystem(root=BASE_FOLDER)
# Esempio di utilizzo
# vfs.mkdir("dir1")
# vfs.mkdir("dir2")
# vfs.cd("dir1")
# vfs.mkdir("dir3")
# vfs.cd("../../data")
# vfs.cd("..")
# vfs.ls()
# vfs.mkdir("../banana")
