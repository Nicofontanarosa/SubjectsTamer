# 🎓 Subject Tamer
### A project by the GRASP group

A single-player university-subject card game inspired by the University of Pisa, where each card represents an official course from various university departments, illustrated with artwork stored in `shared/assets/`. The browser client is built in plain JavaScript, while all game logic and saved progress are managed entirely by the backend.

# 📌 Requirements

- Docker with the Compose plugin
- Python 3 only if you want to serve the frontend without Docker

# 🤸 Quickstart

Open a terminal in the `code/` directory and start the backend services:

```sh
docker compose up --build
```

Wait until the services report that they are healthy. The API Gateway is then available at [http://localhost:5000](http://localhost:5000). Keep this terminal running.

Open a second terminal in the same `code/` directory and start the frontend with Docker:

```sh
docker build -f frontend/Dockerfile -t monster-tamer-frontend .
docker run --rm -p 8000:8080 monster-tamer-frontend
```

Open [http://localhost:8000](http://localhost:8000), register a tamer, and begin exploring. The frontend connects only to the API Gateway; it never calls an internal service or a database. The frontend container is not part of Compose and is not attached to the backend network.

To stop the frontend, press `Ctrl+C` in its terminal. To stop the backend services, press `Ctrl+C` in the Compose terminal, then run:

```sh
docker compose down
```

This stops the services but preserves player accounts, collections, and history. To permanently delete that data as well, run `docker compose down --volumes` instead.

Player Manager, Collector, and Encounter each own a persistent SQLite database. Active battle state is held in Game Manager memory and is discarded after 30 minutes of inactivity or when Game Manager restarts. Completed history and rewards are saved before a battle is reported complete.

# ⚙️ How does it work?

For detailed architectural and functional specifications, please refer to the `doc/` directory. The OpenAPI specification files for the microservices are located in the `docs/openapi/` directory and can be viewed via Swagger UI.

## Game loop

1. Register with an email, password, and tamer name. Three distinct random 6/9-CFU cards are bound to your first team.
2. Inspect your collection and the complete playable codex; edit and save a three-card team.
3. Start an encounter. Game Manager selects an unowned subject with CFU-weighted odds, raises its HP/Attack/Defense by 150% (2.5x total), and tosses initiative.
4. Choose a living companion to strike. The boss answers against a random living companion. A victory awards the normal, unboosted subject; a defeat awards nothing.
5. View your chronicle and graduation progress. The entire team heals after every concluded encounter; there are no stamina limits.

Department advantages form a wheel: 

- Computer Science > Engineering > Medicina e Chirurgia > Giurisprudenza > Computer Science. 

An advantaged strike gains 20% Attack and the defender receives 20% less Defense. HP, Attack, and Defense start from catalog values or scale with CFU, then each receives an independent, stable pseudo-random **reduction of 0-10 points per card**. The reduction is derived from the card ID, so a card's stats match across services and do not change between requests. The battle engine scales player and boss strike power separately to keep encounters playable while retaining the stat buff and department modifiers.

### Image-backed catalog

Only subjects with matching artwork in `shared/assets/` are enabled: 15 Computer Science courses, 14 Engineering courses, 16 Medicina e Chirurgia courses, and 18 Giurisprudenza courses (63 in total). Their catalog records, department, CFU, derived rarity/stats, and artwork paths are in `shared/catalog.json`; the corresponding card images are served by the Collector. New subjects are not added unless matching project artwork is provided.

### Project structure

```text
code/
├── collector/            Persistent owned-card collection and team validation
├── common/               Shared catalog and SQLite helpers
├── encounter/            Persistent encounter history
├── frontend/             Responsive fantasy UI and image assets
├── game_manager/         In-memory turn-based battle lifecycle and rewards
├── gateway/              The only host-published REST entry point
├── player_manager/       Registration, password login, profiles, and tutorial
├── shared/               Image-backed catalog, tutorial, and card artwork
├── docs/openapi/         Public and service REST API contracts
└── docker-compose.yml    Backend deployment
```

## Services and REST API

| Service | Responsibility | Main endpoints |
|---|---|---|
| API Gateway | Plain HTTP route dispatch | `GET /health`, all public routes below |
| Player Manager | Account creation/login, profile, deletion coordination, tutorial | `POST /players`, `POST /auth/login`, `POST /auth/logout`, `GET/PUT/DELETE /players/{playerId}`, `GET /tutorial` |
| Collector | Collection, image delivery, exact-three team validation | `GET /monsters`, `GET /players/{playerId}/collection`, `GET /monsters/{monsterId}/image`, `PUT /players/{playerId}/team` |
| Game Manager | Boss selection, initiative, turn processing, outcomes, reward orchestration | `POST /battles`, `POST /battles/{battleId}/actions` |
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

# API calls on startup and login

When the frontend opens with no player profile saved in the browser, it displays the login page without making an API request. Submitting the login form sends `POST /auth/login` with the email and password to the API Gateway; because the request uses JSON from a different origin, the browser first sends an `OPTIONS /auth/login` CORS preflight. The Gateway forwards the `POST` to Player Manager. A successful response contains the player profile, which the frontend saves in `localStorage`.

The frontend then loads the data needed by the game with five `GET` requests in parallel through the Gateway:

| Request | Service |
|---|---|
| `GET /players/{playerId}` | Player Manager |
| `GET /players/{playerId}/collection` | Collector |
| `GET /monsters?playerId={playerId}` | Collector |
| `GET /players/{playerId}/encounters?limit=100` | Encounter |
| `GET /tutorial` | Player Manager |

Once these requests succeed, the frontend renders the Hall; rendering that page does not trigger additional API calls. The current Hall has no card images. If a profile is already saved in `localStorage` when the frontend opens, it skips the login page and loads the same five resources directly.

### Collection progress and image cache

The Collector responses include progress counts, but the frontend calculates the “Road to graduation” display from the loaded lists: `state.collection.length` is the number owned, `state.catalog.length` is the catalog total, and the percentage is `Math.round(owned / total * 100)`. For example, 8 owned cards out of 63 gives `8 / 63` and `13%`.

Card artwork is fetched from `GET /monsters/{monsterId}/image`. In the frontend, `imageCache` keeps a promise for each card's downloaded image blob and its generated object URL, keyed by monster ID. This reuses the same download when an image is requested again during that page session and avoids duplicate concurrent requests. If a download fails, its cache entry is removed so a later render can retry. Object URLs are revoked and the map cleared on logout; URLs are also revoked when the page is left. The Collector marks image responses as conditionally cacheable for one hour, but the frontend's shared `fetch` helper sets `cache: "no-store"` on API requests, so browser HTTP caching is not relied on by these calls.

### Battle API shapes

- `POST /battles` accepts `{ "playerId": "<player-id>" }`. The response contains the `battleId`, boosted boss stats, team HP, initiative, and battle status.

- `POST /battles/{battleId}/actions` accepts `{ "actionType": "attack", "moveId": "<living-team-card-id>", "playerId": "<player-id>" }` to attack, or `{ "actionType": "abandon", "playerId": "<player-id>" }` to withdraw. The server validates the action and, for attacks, the turn order and living HP; withdrawal is recorded as a loss.

The response contains the updated state and any final result. A repeated `POST /battles` resumes the player's existing in-memory battle instead of creating a second battle.

# 🔐 Architecture & Security Gaps

1. Missing Explicit Authentication & Authorization (Security Gap): Across almost all flows, the frontend passes identifiers directly without microservices (Collector, Game Manager, Encounter) verifying user permissions. This allows potential unauthorized read/write access to any playerId.

The login screen only checks the password and selects a local player profile.

2. Lack of Distributed Transactions for Deletion: Player deletion is coordinated by Player Manager without distributed transactions. Partial failures return a 502 error and leave orphan data in downstream services unless the client retries the idempotent DELETE requests.

3. Missing Automated Testing: There are currently no unit, integration, or end-to-end (E2E) tests implemented across the microservices or the frontend client.

# 🙌 DISCLAIMER

While We do our best to detect code anomalies, We cannot guarantee that this software is error-free. Please ensure that you respect users' privacy and have proper authorization to use it. Additionally, while preparing our documentation, we apologize if any information regarding services or implementation choices is missing or incomplete.

# 👥 Authors & Acknowledgments

This project was developed as part of an academic project at the [University of Pisa](https://github.com/Unipisa) by the GRASP group, by the following contributors:

* [@diperanto](https://github.com/diperanto) | a.diperna@studenti.unipi.it
* [@riccardo-cristofani](https://github.com/riccardo-cristofani) | r.cristofani@studenti.unipi.it
* [@SaraCroft02](https://github.com/SaraCroft02) | s.boscardin1@studenti.unipi.it
* [@Nicofontanarosa](https://github.com/Nicofontanarosa) | n.fontanarosa@studenti.unipi.it

![GitHub followers](https://img.shields.io/github/followers/Nicofontanarosa?style=social)