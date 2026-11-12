# Subject Tamer

A single-player university-subject collecting game. Each card is a course from the source specification, illustrated only with artwork already present in the workspace's `icons/` directory. The browser client is plain JavaScript; all game rules and saved progress live in the backend.

## Get started

Requirements: Docker with the Compose plugin, and Python 3 for the standalone static frontend.

From this directory:

```sh
docker compose up --build
```

The API Gateway is available at [http://localhost:5000](http://localhost:5000). Serve the frontend separately:

```sh
python -m http.server 8000 --directory frontend
```

Open [http://localhost:8000](http://localhost:8000), register a tamer, and begin exploring. The browser connects only to the API Gateway; it never calls an internal service or a database.

An optional standalone frontend image is also available:

```sh
docker build -f frontend/Dockerfile -t monster-tamer-frontend .
docker run --rm -p 8000:8080 monster-tamer-frontend
```

The frontend container is not part of Compose and is not attached to the backend network.

## Local-only setup

This version intentionally runs over plain HTTP with no API/session tokens and no internal-service token checks. Player profiles and game endpoints are not access-controlled; the login screen only checks the password and selects a local player profile. Do not expose this setup to the internet or use real personal information. Passwords continue to be stored as password hashes; email and biography fields are stored as ordinary profile data.

The gateway binds to `127.0.0.1:5000`. Backend services are not published as host ports. `docker compose down` stops the services and keeps progress. Do not use `docker compose down --volumes` unless you intend to permanently delete player accounts, collections, and history.

Persistent SQLite files are owned independently by Player Manager, Collector, and Encounter. Active battle state is intentionally in Game Manager memory and is discarded after inactivity (30-minute TTL) or a Game Manager restart; completed history and rewards are persisted before a battle is reported complete.

## Game loop

1. Register with an email, password, and tamer name. Three distinct random 6/9-CFU cards are bound to your first team.
2. Inspect your collection and the complete playable codex; edit and save a three-card team.
3. Start an encounter. Game Manager selects an unowned subject with CFU-weighted odds, raises its HP/Attack/Defense by 50%, and tosses initiative.
4. Choose a living companion to strike. The boss answers against a random living companion. A victory awards the normal, unboosted subject; a defeat awards nothing.
5. View your chronicle and graduation progress. The entire team heals after every concluded encounter; there are no stamina limits.

Computer Science receives its documented 20% Attack advantage against Engineering; Engineering's documented 20% Defense vulnerability to Computer Science is also applied. HP, Attack, and Defense scale linearly with CFU. The battle engine scales player and boss strike power separately to keep the boss encounter playable while retaining the documented stat buff and department modifiers.

## Image-backed catalog

Only the 18 pictured subjects are enabled: 15 Computer Science courses and 3 Engineering courses. Their catalog records, department, CFU, derived rarity/stats, and artwork paths are in `shared/catalog.json`; the Collector serves the corresponding existing card images. New subjects are not added unless matching project artwork is provided.

## Project structure

```text
code/
├── collector/           Persistent owned-card collection and team validation
├── common/              Shared catalog and SQLite helpers
├── encounter/            Persistent encounter history
├── frontend/             Responsive fantasy UI and image assets
├── game_manager/         In-memory turn-based battle lifecycle and rewards
├── gateway/              The only host-published REST entry point
├── player_manager/       Registration, password login, profiles, and tutorial
├── shared/               Image-backed catalog and tutorial JSON
├── docs/openapi/          Public and service REST API contracts
└── docker-compose.yml     Backend deployment
```

## Services and REST API

| Service | Responsibility | Main endpoints |
|---|---|---|
| API Gateway | Plain HTTP route dispatch | `GET /health`, all public routes below |
| Player Manager | Account creation/login, profile, deletion coordination, tutorial | `POST /players`, `POST /auth/login`, `POST /auth/logout`, `GET/PUT/DELETE /players/{playerId}`, `GET /tutorial` |
| Collector | Collection, image delivery, exact-three team validation | `GET /monsters`, `GET /players/{playerId}/collection`, `GET /monsters/{monsterId}/image`, `PUT /players/{playerId}/team` |
| Game Manager | Boss selection, initiative, turn processing, outcomes, reward orchestration | `POST /battles`, `POST /battles/{battleId}/actions`, `POST /battles/{battleId}` (abandon) |
| Encounter | Idempotent result persistence and player history | `GET /players/{playerId}/encounters` |

Service-to-service endpoints are documented separately under `docs/openapi/`. The gateway does not forward `/internal/` paths, and no internal service port is published. There are no bearer-token or internal-token headers.

### Account examples

Register:

```json
{
  "email": "tamer@example.com",
  "password": "a-long-password",
  "nickname": "Rowan",
  "bio": "A student of the old halls."
}
```

The response contains the created `player` profile and HTTP 201. The frontend stores that profile locally to reopen the same player after a page refresh. `POST /auth/login` accepts `{ "email": "...", "password": "..." }` and returns the matching profile; this is not an access-control mechanism.

### Battle API shapes

`POST /battles` accepts `{ "playerId": "<player-id>" }`. The response contains the `battleId`, boosted boss stats, team HP, initiative, and battle status.

`POST /battles/{battleId}/actions` accepts `{ "actionType": "attack", "moveId": "<living-team-card-id>", "playerId": "<player-id>" }`. The server validates the team, turn order, and living HP, then returns updated state and any final result.

`POST /battles/{battleId}` accepts `{ "playerId": "<player-id>" }` to withdraw from an active encounter; withdrawal is recorded as a loss. A repeated `POST /battles` resumes the player's existing in-memory battle instead of creating a second battle.

## Verification

No automated test suite or test collection was created, as requested. The user-facing flows can be checked manually in the browser. The source functional-requirements PDF asks for Bruno/Postman component/integration tests, Locust performance tests, and CI security analysis; those deliverables are intentionally not included.
