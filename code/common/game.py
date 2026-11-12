import json
import os
from pathlib import Path

from flask import jsonify

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "/app/shared/catalog.json"))


def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    return catalog, {monster["id"]: monster for monster in catalog}


def add_stats(monster):
    cfu = monster["cfu"]
    stats = monster.get("baseStats") or {
        "hp": 95 + 7 * cfu,
        "attack": round(12 + 1.5 * cfu),
        "defense": round(8 + 1.2 * cfu),
    }
    return {
        **monster,
        "rarity": rarity(cfu),
        "stats": stats,
        "imageUrl": f"/monsters/{monster['id']}/image",
    }


def rarity(cfu):
    if cfu >= 15:
        return "Legendary"
    if cfu >= 12:
        return "Epic"
    if cfu >= 9:
        return "Rare"
    if cfu >= 6:
        return "Uncommon"
    return "Common"


def error_response(code, message, status):
    return jsonify({"error": code, "message": message}), status
