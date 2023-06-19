from . import BASE_FOLDER

_dfolder: str = ''
_dautofolder: bool = False
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
