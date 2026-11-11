"""Store imports (v1.56, docs/store-import.md): bring a reseller's customers from another bot into their store.

One adapter per source system (`mirza.py`); `engine.py` does the rest (preview, import, undo) the same way for all.
"""
from . import mirza

ADAPTERS = {mirza.NAME: mirza}


def detect(tables: dict):
    for a in ADAPTERS.values():
        if a.detect(tables):
            return a
    return None
