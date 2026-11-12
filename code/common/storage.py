import os
import sqlite3
from pathlib import Path


def connect(database_name):
    database_path = Path(os.environ.get("DATA_DIR", "/data")) / database_name
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
