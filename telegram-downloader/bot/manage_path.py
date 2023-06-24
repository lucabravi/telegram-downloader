import os
import re
import logging
from distutils.util import strtobool
from pathlib import PurePath

from . import BASE_FOLDER

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class VirtualFileSystem:
    def __init__(self, root='/'):
        self.root = os.path.abspath(root)
        self.current_dir = self.root
        self.allow_root_folder = strtobool(os.getenv('ALLOW_ROOT_FOLDER', True))
        self.auto_folder = True

    def mkdir(self, directory_name):
        # Rimozione dei caratteri proibiti
        directory_name = re.sub(r'[<>:\"/\\|?*]', '', directory_name)
        # Rimozione dei doppi spazi
        directory_name = re.sub(r' +', ' ', directory_name)
        # Rimozione degli spazi iniziali e finali
        directory_name = directory_name.strip()

        if not directory_name:
            err = "Invalid directory name"
            logging.info(err)
            return False, err

        tmp_dir = os.path.join(self.current_dir, directory_name)
        if not PurePath(os.path.abspath(tmp_dir)).is_relative_to(self.root):
            err = "Cannot go beyond the virtual root directory"
            logging.info(err)
            return False, err

        os.makedirs(tmp_dir, exist_ok=True)
        logging.info(f"Created directory '{directory_name}'")
        return True, ''

    def cd(self, directory_name) -> (bool, str):
        tmp_dir = os.path.join(self.current_dir, directory_name)

        # if '\'' in directory_name:
        #     err = "Invalid directory name"
        #     logging.info(err)
        #     return False, err
        #
        # if directory_name == '..':
        #     if self.current_dir == self.root:
        #         err = "Already in root"
        #         logging.info(err)
        #         return False, err

        if not os.path.isdir(tmp_dir):
            err = f"Directory '{directory_name}' does not exist or is not accessible"
            logging.info(err)
            return False, err

        if not PurePath(os.path.abspath(tmp_dir)).is_relative_to(self.root):
            err = "Cannot go beyond the virtual root directory"
            logging.info(err)
            return False, err

        self.current_dir = tmp_dir
        return True, ''

    def ls(self):
        directories = []
        files = []
        for item in os.listdir(self.current_dir):
            item_path = os.path.join(self.current_dir, item)
            if os.path.isdir(item_path):
                directories.append(item)
            else:
                files.append(item)
        logging.info(f"Directories: [{','.join(directories)}]")
        logging.info(f"Files: [{','.join(files)}]")
        return directories, files


vfs = VirtualFileSystem(root="./test")

# Esempio di utilizzo
# vfs.mkdir("dir1")
# vfs.mkdir("dir2")
# vfs.cd("dir1")
# vfs.mkdir("dir3")
# vfs.cd("../../data")
# vfs.cd("..")
# vfs.ls()
# vfs.mkdir("../banana")
