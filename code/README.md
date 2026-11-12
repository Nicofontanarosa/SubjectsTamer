# Monster Tamer — Academy of Ashenvale

A single-player university-subject collecting game. Each card is a course from the source specification, illustrated only with artwork already present in the workspace's `icons/` directory. The browser client is plain JavaScript; all game rules and saved progress live in the backend.

## Get started

Requirements: Docker with the Compose plugin, and Python 3 for the standalone static frontend.

From this directory:

```sh
cp .env.example .env
# Replace the three development secrets in .env with long, unique values.
docker compose up --build
```

The first launch builds the five backend containers and creates a local certificate authority and service certificates in Docker-managed volumes. The API Gateway is the only service published on the host: `https://localhost:5000`.

The gateway certificate is issued by the local development CA. Download the public CA certificate and trust it in your browser/OS (or open the gateway origin and accept its local certificate warning):

```sh
curl --insecure https://localhost:5000/ca.pem --output monster-tamer-local-ca.pem
```

For a local Debian/Ubuntu desktop, add the development CA to the operating-system trust store and restart the browser:

```sh
sudo install -m 0644 monster-tamer-local-ca.pem /usr/local/share/ca-certificates/monster-tamer-local-ca.crt
sudo update-ca-certificates
```

For other operating systems, import `monster-tamer-local-ca.pem` as a trusted certificate authority. This certificate is local-development-only and is regenerated with the Docker certificate volumes.

Serve the frontend separately, outside Docker Compose and its network:

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

## Configuration and persistence

Copy `.env.example` to `.env` and set:

- `JWT_SECRET`: signs player access tokens.
- `INTERNAL_TOKEN`: authenticates service-to-service requests.
- `DATA_ENCRYPTION_KEY`: encrypts player email and biography fields in Player Manager's database.

Keep the encryption key stable while data exists. Replacing it makes existing encrypted profile fields unreadable. The bundled values are explicitly for local development; use independently generated secrets for any shared deployment.

`docker compose down` stops the services and keeps progress. `docker compose down --volumes` permanently deletes player accounts, collections, history, and local certificates.

All backend services use HTTPS with service-specific certificates issued by the local CA. Application containers run as an unprivileged user. Only the Gateway publishes a port. Persistent SQLite files are owned independently by Player Manager, Collector, and Encounter. Active battle state is intentionally in Game Manager memory and is discarded after inactivity (30-minute TTL) or a Game Manager restart; completed history and rewards are persisted before a battle is reported complete.

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
├── cert_init/          Local CA and per-service TLS certificate generation
├── collector/          Persistent owned-card collection and team validation
├── common/             Shared catalog, JWT, internal-auth, TLS, and SQLite helpers
├── encounter/           Persistent encounter history
├── frontend/            Responsive fantasy UI and image assets
├── game_manager/       In-memory turn-based battle lifecycle and rewards
├── gateway/             The only public REST entry point
├── player_manager/     Registration, sessions, profile, and tutorial
├── shared/              Image-backed catalog and tutorial JSON
├── docs/openapi/         Public and private REST API contracts
└── docker-compose.yml    Backend deployment
```

## Services and REST API

| Service | Responsibility | Main endpoints |
|---|---|---|
| API Gateway | HTTPS entry point, authentication-session check, route dispatch | `GET /health`, all public routes below |
| Player Manager | Account creation/login/logout, profile, deletion coordination, tutorial | `POST /players`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`, `GET/PUT/DELETE /players/{playerId}`, `GET /tutorial` |
| Collector | Collection, image delivery, exact-three team validation | `GET /monsters`, `GET /players/{playerId}/collection`, `GET /monsters/{monsterId}/image`, `PUT /players/{playerId}/team` |
| Game Manager | Boss selection, initiative, turn processing, outcomes, reward orchestration | `POST /battles`, `POST /battles/{battleId}/actions`, `POST /battles/{battleId}` (abandon) |
| Encounter | Idempotent result persistence and player history | `GET /players/{playerId}/encounters` |

Internal service-only endpoints are documented separately under `docs/openapi/`. The gateway rejects internal paths, and no internal service port is published.

### Account examples

Register:

```json
{
  "email": "tamer@example.com",
  "password": "a-long-password",
  "nickname": "Rowan",
  "avatar": "ranger",
  "bio": "A student of the old halls."
}
```

The response contains the created `player`, a JWT `accessToken`, and HTTP 201. Send the token on protected API calls:

```http
Authorization: Bearer <accessToken>
```

Login uses `POST /auth/login` with `{ "email": "...", "password": "..." }`. Profile reads and edits are restricted to the player represented by the token.

### Battle API shapes

`POST /battles` accepts `{ "playerId": "<authenticated-player-id>" }`. The response contains the `battleId`, boosted boss stats, team HP, initiative, and battle status.

`POST /battles/{battleId}/actions` accepts `{ "actionType": "attack", "moveId": "<living-team-card-id>" }`. The server validates ownership, turn order, and living HP, then returns updated state and any final result.

`POST /battles/{battleId}` withdraws from an active encounter; withdrawal is recorded as a loss. A repeated `POST /battles` resumes the player's existing in-memory battle instead of creating a second battle.

## Verification

No automated test suite or test collection was created, as requested. The user-facing flows can be checked manually in the browser. The source functional-requirements PDF asks for Bruno/Postman component/integration tests, Locust performance tests, and CI security analysis; those deliverables are intentionally not included because this request explicitly prohibited developing tests. No final course report PDF or GitHub Actions workflow was present in the workspace.

## Scope decisions and limitations

- The provided image directory contains course artwork rather than item/resource icons. The game therefore has a course-card collection and no separate material inventory.
- The source lists Computer Science, Engineering, Medicine, and Law, but only Computer Science and Engineering courses have supplied images. Only those two represented departments are playable; no missing department art or course cards were invented.
- The source specification mentions unexpected client closure cleanup. Browsers cannot reliably notify a server on abrupt process termination; idle battles are instead purged by Game Manager's 30-minute inactivity TTL.
- The source security document asks for static/dependency analysis and a final report. No CI workflow or final course report was supplied, and these are outside the executable game's scope.
