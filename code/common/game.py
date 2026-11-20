import json
import os
from pathlib import Path

from flask import jsonify

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "/app/shared/catalog.json"))

# read the JSON catalog and also create a map to find subjects by ID
def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    return catalog, {monster["id"]: monster for monster in catalog}

# returns a JSON object with an error message and the specified HTTP status. It is used to respond to invalid requests or when errors occur.
def error_response(code, message, status):
    return jsonify({"error": code, "message": message}), status
