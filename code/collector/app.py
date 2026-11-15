# Imports Python's standard module for logging.
import logging
from pathlib import Path

from flask import Flask

from common.game import load_catalog
from common.storage import connect
from routes.collection import collection_bp
from routes.health import health_bp
from routes.monsters import monsters_bp
from routes.team import team_bp

app = Flask(__name__)
# Displays log messages at INFO level and above (INFO, WARNING, ERROR, CRITICAL) in the terminal. DEBUG messages are not shown.
app.logger.setLevel(logging.INFO)
# CATALOG is a list of all monsters, used, for example, to display them at /monsters.
# MONSTERS is a dictionary indexed by ID, useful for quickly finding a monster or checking whether it exists in the catalog.
app.config["CATALOG"], app.config["MONSTERS"] = load_catalog()
app.config["ASSET_DIR"] = Path("/app/shared/assets")

# connect() opens the SQLite database and creates the file if it does not exist. CREATE TABLE IF NOT EXISTS then creates
# the collection and teams tables without deleting existing data. Initialization runs at every startup, but creates
# the file and tables only if they are missing.
def initialize_database():
    with connect("collection.sqlite") as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS collection (
                player_id TEXT NOT NULL,
                monster_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (player_id, monster_id)
            );
            CREATE TABLE IF NOT EXISTS teams (
                player_id TEXT PRIMARY KEY,
                slot_1 TEXT NOT NULL,
                slot_2 TEXT NOT NULL,
                slot_3 TEXT NOT NULL
            );
            """
        )

# Tells Flask to attach the routes defined in a blueprint to the application. A blueprint groups endpoints separately;
# registering it adds those routes to the application so Flask can handle requests to them.
app.register_blueprint(collection_bp)
app.register_blueprint(team_bp)
app.register_blueprint(monsters_bp)
app.register_blueprint(health_bp)

initialize_database()
