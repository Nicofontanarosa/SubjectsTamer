#!non usare questo file per testare il servizio, ma solo per testare le funzioni interne del modulo game_manager.py
#!non aggiungerlo al dockerfile, non è necessario per il servizio in produzione.
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# Usa il catalogo locale quando il modulo carica il servizio durante i test.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
with patch.dict(
    os.environ,
    {"CATALOG_PATH": str(PROJECT_ROOT / "shared" / "catalog.json")},
):
    from game_manager import app as game_manager


#1
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"playerId": "p1"}, "p1"),
        (None, None),
        ([], None),
        ({}, None),
        ({"playerId": ""}, None),
        ({"playerId": 123}, None),
    ],
)
def test__player_id_from_request__accepts_only_non_empty_strings(body, expected):
    # Il playerId è valido solo se il corpo è un dizionario con una stringa non vuota.
    assert game_manager.player_id_from_request(body) == expected

#2
def test_alive_monster_in_team_excludes_knocked_out_members():
    battle = {
        "team": [            
            {"id": "alive", "currentHp": 1},
            {"id": "knocked-out", "currentHp": 0},
        ]
    }

    # I membri con zero HP non devono essere selezionati come vivi.
    assert game_manager.alive_monster_in_team(battle) == [
        {"id": "alive", "currentHp": 1}
    ]


#3 testo se calcola bene i moltiplicatori di vantaggio/svantaggio tra dipartimenti.
@pytest.mark.parametrize(
    ("attacker_department", "defender_department", "expected"),
    [
        ("Computer Science", "Engineering", (1.2, 0.8)),
        ("Engineering", "Computer Science", (1.0, 1.0)),
        ("Engineering", "Medicina e Chirurgia", (1.2, 0.8)),
        ("Medicina e Chirurgia", "Giurisprudenza", (1.2, 0.8)),
        ("Giurisprudenza", "Computer Science", (1.2, 0.8)),
    ],
)
def test_type_matchup_returns_expected_multipliers(
    attacker_department, defender_department, expected
):
    assert (
        game_manager.type_matchup_calculation(
            attacker_department, defender_department
        )
        == expected
    )


#4
def test_strike_applies_advantage_and_minimum_damage():
    attacker = {
        "department": "Computer Science",
        "stats": {"attack": 10},
    }
    defender = {
        "department": "Engineering",
        "stats": {"defense": 10},
    }

    # Sostituisce la componente casuale per rendere prevedibile il danno.
    with patch.object(game_manager.random, "uniform", return_value=1.8):
        assert game_manager.strike(attacker, defender, is_boss=False) == (
            19,
            True,
            True,
        )

    #caso con danno minimo
    attacker["stats"]["attack"] = 1
    defender["department"] = "Computer Science"
    defender["stats"]["defense"] = 100
    with patch.object(game_manager.random, "uniform", return_value=1.65):
        assert game_manager.strike(attacker, defender, is_boss=False) == (
            6,
            False,
            False,
        )


#5
def test_append_event__keeps_only_the_latest_24_events():
    battle = {
        "turns": 25,
        "events": [{"turn": turn, "text": str(turn)} for turn in range(24)],
        "latestEvent": "23",
    }

    game_manager.append_event(battle, "latest")

    # L'evento più vecchio viene eliminato e latestEvent riflette l'ultimo testo.
    assert len(battle["events"]) == 24
    assert battle["events"][0] == {"turn": 1, "text": "1"}
    assert battle["events"][-1] == {"turn": 25, "text": "latest"}
    assert battle["latestEvent"] == "latest"



#6
def test_make_boss_boosts_stats_without_mutating_the_monster():
    monster = {
        "id": "m1",
        "stats": {"hp": 11, "attack": 2, "defense": 3},
    }

    boss = game_manager.make_boss(monster)

    # Il boss riceve statistiche potenziate mentre il mostro sorgente resta invariato.
    assert boss["normalStats"] == {"hp": 11, "attack": 2, "defense": 3}
    assert boss["battleStats"] == {"hp": 28, "attack": 5, "defense": 8}
    assert boss["stats"] == boss["battleStats"]
    assert boss["currentHp"] == 28
    assert boss["isBoss"] is True
    assert monster["stats"] == {"hp": 11, "attack": 2, "defense": 3}


#7
def test_public_battle_exposes_battle_fields_only():
    battle = {
        "battleId": "b1",
        "playerId": "p1",
        "boss": {},
        "team": [],
        "initiative": "player",
        "activeTurn": "player",
        "turns": 0,
        "status": "in_progress",
        "result": None,
        "outcome": None,
        "reward": None,
        "events": [],
        "latestEvent": "",
        "startedAt": "start",
        "completedAt": None,
        "finalized": False,
        "lastActivityTime": "internal",
    }

    public = game_manager.public_battle(battle)

    # I dati interni di gestione non devono essere inclusi nella risposta pubblica.
    assert "lastActivityTime" not in public
    assert public["battleId"] == "b1"
    assert len(public) == len(battle) - 1


#8
def test_boss_turn_damages_a_living_ally_and_records_the_turn():
    battle = {
        "boss": {
            "name": "Boss",
            "department": "Computer Science",
            "battleStats": {"attack": 20},
        },
        "team": [
            {
                "name": "Ally",
                "department": "Computer Science",
                "stats": {"defense": 10},
                "currentHp": 20,
            }
        ],
        "turns": 0,
        "events": [],
    }

    
    with patch.object( #(sostituisce la scelta casuale del bersaglio con il primo alleato vivo per rendere il test prevedibile)
        game_manager.random, "choice", side_effect=lambda targets: targets[0]
    ):
        with patch.object(game_manager.random, "uniform", return_value=0.5):
            game_manager.boss_turn(battle)

    assert battle["team"][0]["currentHp"] == 12
    assert battle["turns"] == 1
    assert battle["events"][-1]["turn"] == 1
    assert "struck Ally for 8 damage" in battle["latestEvent"]


#9 questo test verifica che la funzione cleanup_expired rimuova correttamente le battaglie scadute e gli indici dei giocatori.
def test_cleanup_expired_removes_stale_battle_and_player_index():
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    active_at = datetime.now(timezone.utc).isoformat()
    battles = {
        "expired": {"playerId": "p1", "lastActivityTime": expired_at},
        "active": {"playerId": "p2", "lastActivityTime": active_at},
    }
    player_battles = {"p1": "expired", "p2": "active"}

    # Ripristina gli archivi globali dopo il test per non interferire con altri test.
    with patch.dict(game_manager.BATTLES, battles, clear=True):
        with patch.dict(game_manager.PLAYER_BATTLES, player_battles, clear=True):
            game_manager.cleanup_expired()

            assert "expired" not in game_manager.BATTLES
            assert "active" in game_manager.BATTLES
            assert "p1" not in game_manager.PLAYER_BATTLES
            assert game_manager.PLAYER_BATTLES["p2"] == "active"
