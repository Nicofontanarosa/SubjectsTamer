"""Caricamento dei dati del tutorial, senza costruire risposte HTTP."""

import json
import logging
import os
from pathlib import Path

from .exceptions import StorageError

logger = logging.getLogger(__name__)

# il percorso è configurabile da docker; per default il file è in /app/tutorial.json.
TUTORIAL_PATH = Path(os.environ.get("TUTORIAL_PATH", "/app/tutorial.json"))


# la funzione restituisce i dati python letti dal file (dizionario o lista).
# sarà app.py a serializzarli nella risposta json.
def tutorial():
    try:
        with TUTORIAL_PATH.open(encoding="utf-8") as tutorial_file:
            return json.load(tutorial_file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Tutorial file could not be read")
        raise StorageError("tutorial_unavailable", "The field guide is unavailable") from exc