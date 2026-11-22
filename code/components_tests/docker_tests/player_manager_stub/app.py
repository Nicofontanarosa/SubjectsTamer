"""Stub HTTP per le dipendenze di Player Manager (Collector, Encounter, Game Manager).

Espone gli endpoint reali chiamati dal Player Manager e strumenti di controllo
/__reset, /__configure e /__calls per i test Bruno.
"""

from collections import Counter
from threading import Lock
import time

from flask import Flask, jsonify, request

app = Flask(__name__)
lock = Lock()

DEFAULT_STATUSES = {
    "initialize": 201,
    "collector_delete": 204,
    "encounter_delete": 204,
    "game_manager_delete": 204,
}

calls = []
rules = {}


def reply(operation, player_id):
    with lock:
        rule = rules.get(operation, {})
        status = rule.get("status", DEFAULT_STATUSES[operation])
        delay = rule.get("delaySeconds", 0)
        calls.append({
            "operation": operation,
            "playerId": player_id,
            "method": request.method,
            "path": request.path,
            "status": status,
        })
    if delay:
        time.sleep(delay)
    if status == 204:
        return "", 204
    if status >= 400:
        return jsonify({"error": "simulated_dependency_error"}), status
    return jsonify({"status": "ok", "playerId": player_id}), status


@app.post("/internal/players/<player_id>/collection/initialize")
def initialize(player_id):
    return reply("initialize", player_id)


@app.delete("/internal/players/<player_id>/collection")
def delete_collection(player_id):
    return reply("collector_delete", player_id)


@app.delete("/internal/players/<player_id>/encounters")
def delete_encounters(player_id):
    return reply("encounter_delete", player_id)


@app.delete("/internal/players/<player_id>/battles")
def delete_battles(player_id):
    return reply("game_manager_delete", player_id)


@app.post("/__reset")
def reset():
    with lock:
        calls.clear()
        rules.clear()
    return jsonify({"status": "ok", "count": 0}), 200


@app.post("/__configure")
def configure():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid_configuration"}), 400
    operation = body.get("operation")
    status = body.get("status", DEFAULT_STATUSES.get(operation))
    delay = body.get("delaySeconds", 0)
    if (
        operation not in DEFAULT_STATUSES
        or type(status) is not int
        or not 200 <= status <= 599
        or type(delay) not in (int, float)
        or not 0 <= delay <= 10
    ):
        return jsonify({"error": "invalid_configuration"}), 400
    with lock:
        rules[operation] = {"status": status, "delaySeconds": delay}
    return jsonify({"status": "ok", "operation": operation, "responseStatus": status}), 200


@app.get("/__calls")
def received():
    with lock:
        snapshot = [dict(entry) for entry in calls]
    counts = Counter(call["operation"] for call in snapshot)
    latest = snapshot[-1] if snapshot else {}
    return jsonify({
        "calls": snapshot,
        "count": len(snapshot),
        "initializeCount": counts["initialize"],
        "collectorDeleteCount": counts["collector_delete"],
        "encounterDeleteCount": counts["encounter_delete"],
        "gameManagerDeleteCount": counts["game_manager_delete"],
        "lastOperation": latest.get("operation"),
        "lastMethod": latest.get("method"),
        "lastPath": latest.get("path"),
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "player-manager-dependencies-stub"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)
