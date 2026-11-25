import json
import os
import time
from collections import Counter
from threading import Lock

from flask import Flask, Response, jsonify, request

app = Flask(__name__)
catalog_path = os.environ.get("CATALOG_PATH", "/app/catalog-test.json")
with open(catalog_path, encoding="utf-8") as catalog_file:
    CATALOG = json.load(catalog_file)

TEAM_IDS = (
    "programming-algorithms",
    "misure-elettroniche",
    "biologia-molecolare",
)
MONSTERS = {monster["id"]: monster for monster in CATALOG}
lock = Lock()
reward_calls = Counter()


def test_team():
    team = []
    for monster_id in TEAM_IDS:
        monster = dict(MONSTERS[monster_id])
        monster["stats"] = {
            "hp": 1000000,
            "attack": 1000000,
            "defense": 1000000,
        }
        team.append(monster)
    return team


@app.get("/internal/players/<player_id>/team")
def get_team(player_id):
    if player_id == "collector-team-unavailable":
        return jsonify({"error": "simulated_collector_unavailable"}), 503
    if player_id == "collector-team-timeout":
        time.sleep(6)
    if player_id == "collector-team-invalid-json":
        return Response("{", status=200, mimetype="application/json")
    if player_id == "collector-team-invalid-shape":
        return jsonify({"team": "not-a-list", "ownedIds": []}), 200

    owned_ids = list(TEAM_IDS)
    if player_id == "collector-graduated":
        owned_ids = [monster["id"] for monster in CATALOG]
    return jsonify(
        {"playerId": player_id, "team": test_team(), "ownedIds": owned_ids}
    ), 200


@app.post("/internal/players/<player_id>/collection/monsters")
def add_reward(player_id):
    if player_id == "reward-timeout":
        time.sleep(6)
    if player_id == "reward-retry":
        with lock:
            reward_calls[player_id] += 1
            first_attempt = reward_calls[player_id] == 1
        if first_attempt:
            return jsonify({"error": "simulated_reward_failure"}), 503

    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.get("monsterId") not in MONSTERS:
        return jsonify({"error": "invalid_reward_request"}), 400
    return jsonify({"playerId": player_id, "monsterId": body["monsterId"]}), 201


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "collector-stub"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)
