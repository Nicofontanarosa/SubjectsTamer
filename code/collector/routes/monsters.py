import sqlite3

from flask import Blueprint, current_app, jsonify, request, send_file

from common.game import error_response
from common.storage import connect
from routes.helpers import database_error_response, owned_ids

# Creates a Flask Blueprint called monsters_bp to group the monster routes defined in monsters.py.
# "monsters" is the blueprint's internal name, used by Flask to identify it.
# __name__ identifies the Python module where the blueprint is defined; Flask uses it to locate resources associated with the module.
# The blueprint does not activate its routes on its own. They become part of the application when app.py registers it with app.register_blueprint(monsters_bp).
monsters_bp = Blueprint("monsters", __name__)

# Handles GET requests to the /monsters endpoint.
# Returns a JSON list of catalog monsters and indicates which ones are owned by the player specified by playerId (optional).
@monsters_bp.get("/monsters")
def get_catalog():
    catalog = current_app.config["CATALOG"]
    player_id = request.args.get("playerId")
    try:
        with connect("collection.sqlite") as db:
            owned = set(owned_ids(db, player_id)) if player_id else set()
    except sqlite3.Error:
        return database_error_response("loading the monster catalog")
    monsters = [{**monster, "owned": monster["id"] in owned} for monster in catalog]
    return jsonify({"monsters": monsters}), 200

# Handles GET requests to the /monsters/<monster_id>/image endpoint.
# Returns the image for the monster specified by monster_id, if it exists.
# If the monster is not in the catalog or its image is unavailable, returns an appropriate JSON error.
@monsters_bp.get("/monsters/<monster_id>/image")
def get_monster_image(monster_id):
    monster = current_app.config["MONSTERS"].get(monster_id)
    if monster is None:
        return error_response("not_found", "Card not found", 404)
    image_path = current_app.config["ASSET_DIR"] / monster["image"]
    if not image_path.is_file():
        current_app.logger.error("Catalog image is missing for %s", monster_id)
        return error_response("image_unavailable", "Card artwork is unavailable", 500)
    return send_file(image_path, mimetype="image/jpeg", conditional=True, max_age=3600)
