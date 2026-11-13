import hashlib
import json
import os
from pathlib import Path

from flask import jsonify

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "/app/shared/catalog.json"))

# legge il catalogo JSON e crea anche una mappa per trovare le materie tramite ID
def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    return catalog, {monster["id"]: monster for monster in catalog}

# aggiunge rarità, statistiche e URL dell’immagine. Le statistiche derivano dai CFU o dai valori del catalogo;
# una penalità indipendente per statistica viene ricavata dall’ID così resta stabile in tutti i servizi e le partite.
def add_stats(monster):
    cfu = monster["cfu"]
    base_stats = monster.get("baseStats") or {
        "hp": 95 + 7 * cfu,
        "attack": round(12 + 1.5 * cfu),
        "defense": round(8 + 1.2 * cfu),
    }
    stats = {
        stat: max(
            1,
            value - int.from_bytes(
                hashlib.sha256(f"{monster['id']}:{stat}".encode("utf-8")).digest()[:4],
                "big",
            ) % 11,
        )
        for stat, value in base_stats.items()
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
