const API_BASE = (window.MONSTER_TAMER_API || "http://localhost:5000").replace(/\/+$/, "");
localStorage.removeItem("monsterTamerToken");
const app = document.getElementById("app");
const toastElement = document.getElementById("toast");
const detailDialog = document.getElementById("detail-dialog");
const guideDialog = document.getElementById("guide-dialog");
const imageCache = new Map();
const avatarMarks = { ranger: "♧", scholar: "✧", warden: "⬟", sage: "◈" };
const departmentWheel = [
  "Computer Science",
  "Engineering",
  "Medicina e Chirurgia",
  "Giurisprudenza",
];
const state = {
  player: null,
  collection: [],
  teamIds: [],
  selectedTeam: new Set(),
  catalog: [],
  history: [],
  tutorial: null,
  page: "hall",
  filter: "all",
  department: "all",
  battle: null,
  justRegistered: false,
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function avatarMark(value) {
  return avatarMarks[String(value || "").toLowerCase()] || "✦";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      keepalive: Boolean(options.keepalive),
    });
  } catch {
    throw new ApiError(`The academy gateway at ${API_BASE} could not be reached. Start the backend and try again.`, 0);
  }
  if (options.raw && response.ok) return response.blob();
  if (response.status === 204) return null;
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    throw new ApiError(payload.message || `The request failed (${response.status}).`, response.status);
  }
  return payload;
}

function notify(message, type = "success") {
  toastElement.textContent = message;
  toastElement.className = `toast visible${type === "error" ? " error" : ""}`;
  window.clearTimeout(notify.timeout);
  notify.timeout = window.setTimeout(() => {
    toastElement.className = "toast";
  }, 4200);
}

function showLoading(message = "Opening the academy gates…") {
  app.innerHTML = `<section class="loading-screen" aria-live="polite"><span class="crest">✦</span><p>${escapeHtml(message)}</p></section>`;
}

function authScreen(mode = "login", message = "") {
  const registering = mode === "register";
  app.innerHTML = `
    <section class="auth-shell">
      <div class="auth-art">
        <div class="auth-wordmark">Subject Tamer</div>
        <div class="art-sigil" aria-hidden="true">✦</div>
        <div class="auth-copy">
          <h1>Bind the<br>ancient lessons.</h1>
          <p>Gather the knowledge of the represented halls, command your chosen team, and earn the right to graduate.</p>
        </div>
      </div>
      <div class="auth-panel">
        <form class="auth-card" data-form="${registering ? "register" : "login"}">
          <div class="eyebrow">${registering ? "Begin your journey" : "Welcome back, Tamer"}</div>
          <h2>${registering ? "Claim your place" : "Enter the halls"}</h2>
          ${registering ? "" : `<p class="subline">Your collection is kept safe between visits.</p>`}
          <div class="form-error" aria-live="polite">${escapeHtml(message)}</div>
          ${registering ? `<div class="field"><label for="nickname">Tamer name</label><input id="nickname" name="nickname" autocomplete="nickname" maxlength="32" required placeholder="e.g. Rowan of the Vale"></div>` : ""}
          <div class="field"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required maxlength="254" placeholder="you@example.com"></div>
          <div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="${registering ? "new-password" : "current-password"}" minlength="${registering ? "10" : "1"}" required placeholder="${registering ? "At least 10 characters" : "Your password"}"></div>
          <button class="button primary full" type="submit">${registering ? "Create account" : "Sign in"} <span aria-hidden="true">✦</span></button>
          <div class="auth-switch">${registering ? "Already sworn to the academy?" : "New to Ashenvale?"}
            <button type="button" class="text-button" data-action="auth-switch">${registering ? "Sign in" : "Create an account"}</button>
          </div>
        </form>
      </div>
    </section>`;
}

function rarityClass(rarity) {
  return String(rarity || "common").toLowerCase();
}

function matchupTemplate(monster) {
  const index = departmentWheel.indexOf(monster.department);
  if (index < 0) return "";
  const advantage = departmentWheel[(index + 1) % departmentWheel.length];
  const weakness = departmentWheel[(index - 1 + departmentWheel.length) % departmentWheel.length];
  return `
    <div class="card-matchups" aria-label="Department combat matchups">
      <span class="matchup-bonus"><strong>Bonus</strong> +20% ATK vs ${escapeHtml(advantage)}</span>
      <span class="matchup-weakness"><strong>Malus</strong> -20% DEF vs ${escapeHtml(weakness)}</span>
    </div>`;
}

function cardTemplate(monster, options = {}) {
  const stats = monster.stats || {};
  const selected = options.selectable && state.selectedTeam.has(monster.id);
  const owned = options.owned === true || monster.owned === true;
  return `
    <article class="subject-card${selected ? " is-selected" : ""}${options.battle && monster.currentHp <= 0 ? " battle-ally out" : ""}" data-card="${escapeHtml(monster.id)}">
      <button class="card-art" type="button" data-action="details" data-monster="${escapeHtml(monster.id)}" aria-label="View ${escapeHtml(monster.name)} details">
        <span class="rarity">${escapeHtml(monster.rarity)}</span>
        ${owned ? `<span class="owned-stamp">Owned</span>` : ""}
        <img alt="${escapeHtml(monster.name)} card artwork" data-art="${escapeHtml(monster.id)}" loading="lazy">
      </button>
      ${options.selectable ? `<input class="team-pick" type="checkbox" data-team-pick="${escapeHtml(monster.id)}" aria-label="Add ${escapeHtml(monster.name)} to your team" ${selected ? "checked" : ""}>` : ""}
      <div class="card-body">
        <h3 class="card-name">${escapeHtml(monster.name)}</h3>
        <div class="card-meta"><span>${escapeHtml(monster.department)}</span><span>${monster.cfu} CFU</span></div>
        <div class="card-stats">
          <div class="stat"><strong>${stats.hp ?? "—"}</strong><span>HP</span></div>
          <div class="stat"><strong>${stats.attack ?? "—"}</strong><span>ATK</span></div>
          <div class="stat"><strong>${stats.defense ?? "—"}</strong><span>DEF</span></div>
        </div>
        ${matchupTemplate(monster)}
        ${options.battle ? `
          <div class="hp-row" style="margin-top:.7rem"><span>Vitality</span><span>${Math.max(0, monster.currentHp)}/${stats.hp}</span></div>
          <div class="hp-track"><div class="hp-fill ally" style="width:${Math.max(0, Math.min(100, monster.currentHp / stats.hp * 100))}%"></div></div>
          <button class="attack-button" type="button" data-action="attack" data-monster="${escapeHtml(monster.id)}" ${state.battle?.activeTurn !== "player" || monster.currentHp <= 0 || state.battle?.status !== "in_progress" ? "disabled" : ""}>Strike</button>
        ` : ""}
      </div>
    </article>`;
}

function progressTemplate() {
  const total = state.catalog.length || 1;
  const owned = state.collection.length;
  const percent = Math.round(owned / total * 100);
  return `
    <div class="progress-panel">
      <div>
        <div class="progress-label"><span>Road to graduation</span><strong>${owned} / ${state.catalog.length}</strong></div>
        <div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>
      </div>
      <div class="progress-seal" aria-label="${percent}% complete">${percent === 100 ? "✦" : `${percent}%`}</div>
    </div>`;
}

function pageHeading(eyebrow, title, caption = "") {
  return `<div class="section-heading"><div><div class="eyebrow">${escapeHtml(eyebrow)}</div><h2>${escapeHtml(title)}</h2>${caption ? `<p>${escapeHtml(caption)}</p>` : ""}</div><div class="rule-line"></div></div>`;
}

function topbarTemplate() {
  const nav = [
    ["hall", "Hall"],
    ["collection", "My collection"],
    ["codex", "Card codex"],
    ["chronicle", "Chronicle"],
    ["field-guide", "Field guide"],
    ["profile", "Tamer"],
  ];
  return `
    <header class="topbar">
      <div class="brand"><div class="brand-mark"><span>✦</span></div><div>Subject Tamer</div></div>
      <div class="topbar-right">
        <div class="player-chip"><div class="avatar" aria-label="${escapeHtml(state.player?.avatar || "ranger")} emblem">${avatarMark(state.player?.avatar)}</div><span>${escapeHtml(state.player?.nickname || "Tamer")}</span></div>
        <button class="button ghost small" data-action="logout" type="button">Leave</button>
      </div>
    </header>
    <nav class="nav" aria-label="Main navigation">
      ${nav.map(([page, label]) => `<button class="nav-button${state.page === page ? " active" : ""}" data-page="${page}" type="button">${label}</button>`).join("")}
    </nav>`;
}

function hallTemplate() {
  const activeBattle = state.battle && state.battle.status === "in_progress";
  return `
    <section class="hero">
      <div class="hero-copy">
        <div class="eyebrow">The old academy calls</div>
        <h1>${state.collection.length === state.catalog.length ? "Your name is<br>ready for the rolls." : "A realm of knowledge<br>awaits its tamer."}</h1>
        <div class="hero-actions">
          <button class="button primary" data-action="${activeBattle ? "resume-battle" : "begin-battle"}" type="button">${activeBattle ? "Return to encounter" : state.collection.length === state.catalog.length ? "View your honors" : "Seek an encounter"} <span aria-hidden="true">✦</span></button>
          <button class="button ghost" data-page="collection" type="button">Prepare team</button>
        </div>
      </div>
    </section>
  `;
}

function collectionTemplate() {
  state.selectedTeam = new Set(state.teamIds);
  return `
    ${pageHeading("Your bound cards", "The collection", `${state.collection.length} subjects gathered`)}
    ${progressTemplate()}
    <div class="toolbar" style="justify-content:space-between;margin:1.3rem 0 1rem">
      <p style="margin:0;color:var(--muted);font-size:.82rem">Select exactly three cards for your active team.</p>
      <div class="toolbar">
        <span class="eyebrow" id="team-count">${state.selectedTeam.size} / 3 selected</span>
        <button class="button primary small" data-action="save-team" type="button" ${state.selectedTeam.size !== 3 ? "disabled" : ""}>Save team</button>
      </div>
    </div>
    <div class="card-grid" id="collection-grid">${state.collection.map((monster) => cardTemplate(monster, { owned: true, selectable: true })).join("")}</div>`;
}

function codexTemplate() {
  const available = state.catalog.filter((monster) => {
    if (state.filter === "missing" && monster.owned) return false;
    if (state.filter === "owned" && !monster.owned) return false;
    if (state.department !== "all" && monster.department !== state.department) return false;
    return true;
  });
  const filters = [
    ["all", "All cards"],
    ["missing", "Uncollected"],
    ["owned", "Collected"],
  ];
  return `
    ${pageHeading("The card codex", "Subjects of the realm", "Every card carries its own art and measure of strength.")}
    <div class="toolbar" style="justify-content:space-between;margin:1.1rem 0">
      <div class="toolbar">${filters.map(([id, label]) => `<button class="button ${state.filter === id ? "primary" : "ghost"} small" data-filter="${id}" type="button">${label}</button>`).join("")}</div>
      <select class="select" data-department aria-label="Filter by department">
        <option value="all" ${state.department === "all" ? "selected" : ""}>All halls</option>
        <option value="Computer Science" ${state.department === "Computer Science" ? "selected" : ""}>Computer Science</option>
        <option value="Engineering" ${state.department === "Engineering" ? "selected" : ""}>Engineering</option>
        <option value="Medicina e Chirurgia" ${state.department === "Medicina e Chirurgia" ? "selected" : ""}>Medicina e Chirurgia</option>
        <option value="Giurisprudenza" ${state.department === "Giurisprudenza" ? "selected" : ""}>Giurisprudenza</option>
      </select>
    </div>
    <div class="card-grid">${available.length ? available.map((monster) => cardTemplate(monster, { owned: monster.owned })).join("") : `<div class="card-empty">Every card in this hall is already yours.</div>`}</div>`;
}

function historyItemTemplate(entry) {
  const won = entry.result === "win";
  const date = new Date(entry.completedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return `
    <article class="history-item">
      <img class="history-thumb" data-art="${escapeHtml(entry.boss.id)}" alt="${escapeHtml(entry.boss.name)} card artwork">
      <div><h3>${escapeHtml(entry.boss.name)}</h3><p>${escapeHtml(date)} · ${entry.turns} turns · ${escapeHtml(entry.teamUsed.map((card) => card.name).join(", "))}</p></div>
      <div class="history-actions"><span class="outcome ${won ? "win" : "loss"}">${won ? "Victory" : entry.outcome === "abandoned" ? "Withdrawn" : "Defeat"}</span><button class="button ghost small" data-action="history-details" data-battle="${escapeHtml(entry.battleId)}" type="button">Inspect</button></div>
    </article>`;
}

function chronicleTemplate() {
  return `
    ${pageHeading("Your personal history", "The chronicle", "Every concluded encounter, kept in your own record.")}
    ${state.history.length ? `<div class="history-list">${state.history.map((entry) => historyItemTemplate(entry)).join("")}</div>` : `<div class="card-empty">No encounters have been recorded yet.</div>`}`;
}

function fieldGuideTemplate() {
  if (!state.tutorial) return `<div class="card-empty">The field guide is unavailable.</div>`;
  return `
    ${pageHeading("A tamer's field guide", state.tutorial.title, state.tutorial.objective)}
    <div class="guide-grid">${state.tutorial.rules.map((rule, index) => `<article class="guide-card"><span>${String(index + 1).padStart(2, "0")}</span><p>${escapeHtml(rule)}</p></article>`).join("")}</div>
    <div style="margin-top:1.4rem">${pageHeading("The department wheel", "Strengths & vulnerabilities", "Each department has an advantage against the next in the wheel.")}</div>
    <div class="guide-grid">
      <article class="guide-card"><span>Ⅰ</span><p>Computer Science gains 20% Attack against Engineering.</p></article>
      <article class="guide-card"><span>Ⅱ</span><p>Engineering gains 20% Attack against Medicina e Chirurgia.</p></article>
      <article class="guide-card"><span>Ⅲ</span><p>Medicina e Chirurgia gains 20% Attack against Giurisprudenza.</p></article>
      <article class="guide-card"><span>Ⅳ</span><p>Giurisprudenza gains 20% Attack against Computer Science.</p></article>
    </div>`;
}

function profileTemplate() {
  return `
    ${pageHeading("The keeper of your journey", "Tamer's profile")}
    <div class="battle-side" style="max-width:760px">
      <form class="side-panel" data-form="profile">
        <h3>Profile details</h3>
        <div class="field"><label for="profile-nickname">Tamer name</label><input id="profile-nickname" name="nickname" maxlength="32" required value="${escapeHtml(state.player.nickname)}"></div>
        <div class="field"><label for="profile-avatar">Icon</label><select id="profile-avatar" name="avatar">
          ${["ranger", "scholar", "warden", "sage"].map((avatar) => `<option value="${avatar}" ${state.player.avatar === avatar ? "selected" : ""}>${avatar[0].toUpperCase() + avatar.slice(1)}</option>`).join("")}
        </select></div>
        <div class="field"><label for="profile-bio">Personal history</label><textarea id="profile-bio" name="bio" maxlength="500" placeholder="A few words about your journey…">${escapeHtml(state.player.bio || "")}</textarea></div>
        <button class="button primary" type="submit">Save profile</button>
      </form>
      <section class="side-panel">
        <h3>Account</h3>
        <p style="color:var(--muted);font-size:.84rem">${escapeHtml(state.player.email)}</p>
        <button class="button danger small" data-action="delete-account" type="button">Delete account</button>
      </section>
    </div>`;
}

function battleTemplate() {
  const battle = state.battle;
  if (!battle) return `<div class="card-empty">No encounter is open.</div>`;
  const boss = battle.boss;
  const bossHp = boss.currentHp ?? boss.stats.hp;
  const bossPercent = Math.max(0, Math.min(100, bossHp / boss.stats.hp * 100));
  const result = battle.status !== "in_progress";
  return `
    ${pageHeading("The encounter", result ? (battle.result === "win" ? "Victory" : "Defeat") : "A wild subject appears", result ? `${battle.turns} strikes exchanged` : `A ${boss.rarity.toLowerCase()} challenge rises from the halls.`)}
    <div class="battle-layout">
      <section class="battle-arena">
        <div class="battle-top"><span class="eyebrow">Battle ${escapeHtml(battle.battleId.slice(0, 8))}</span><span class="turn-pill">${result ? "Encounter ended" : `${escapeHtml(battle.activeTurn)} turn`}</span></div>
        ${result ? `<div class="result-banner"><div class="eyebrow">${battle.outcome === "abandoned" ? "Withdrawn with honor" : battle.result === "win" ? "Subject acquired" : "The trial is over"}</div><h2>${battle.result === "win" ? "The card is yours." : battle.outcome === "abandoned" ? "You withdrew." : "Gather your strength."}</h2><p>${battle.result === "win" ? `${escapeHtml(boss.name)} joined your collection at normal strength.` : battle.outcome === "abandoned" ? "Your team has been restored; this encounter is recorded as a defeat." : "Your team has been restored. No card was lost."}</p></div>` : ""}
        <div class="boss-stage">
          <img class="boss-art" data-art="${escapeHtml(boss.id)}" alt="${escapeHtml(boss.name)} card artwork">
          <div class="boss-details">
            <div class="eyebrow">${escapeHtml(boss.rarity)} · ${boss.cfu} CFU</div>
            <h2>${escapeHtml(boss.name)}</h2>
            <p>${escapeHtml(boss.department)} · Wild boss · +150% battle stats</p>
            <div class="hp-row"><span>Boss vitality</span><span>${Math.max(0, bossHp)} / ${boss.stats.hp}</span></div>
            <div class="hp-track"><div class="hp-fill" style="width:${bossPercent}%"></div></div>
            <div class="boss-stats"><span>ATK ${boss.stats.attack}</span><span>DEF ${boss.stats.defense}</span></div>
            ${matchupTemplate(boss)}
          </div>
        </div>
        <div class="battle-team">${battle.team.map((monster) => cardTemplate(monster, { battle: true })).join("")}</div>
        ${!result ? `<div class="battle-actions"><span class="eyebrow">Choose a living companion to strike</span><button class="button danger small" data-action="abandon" type="button">Withdraw</button></div>` : `<div class="battle-actions"><button class="button primary" data-action="return-hall" type="button">Return to the hall</button><button class="button ghost small" data-action="new-battle" type="button">Seek another</button></div>`}
      </section>
      <aside class="battle-side">
        <section class="side-panel"><h3>Turn ${battle.turns}</h3><p style="margin:0;color:var(--muted);font-size:.8rem">Initiative: ${escapeHtml(battle.initiative === "player" ? "You struck first" : "The boss struck first")}</p></section>
        <section class="side-panel"><h3>Battle log</h3><div class="event-log">${battle.events.slice(-8).reverse().map((event) => `<div class="event-line">${escapeHtml(event.text)}</div>`).join("")}</div></section>
        <section class="side-panel"><h3>Encounter rule</h3><p style="margin:0;color:var(--muted);font-size:.78rem;line-height:1.6">Your team must outlast the boss. A victory adds the normal card; a defeat restores your team with no reward.</p></section>
      </aside>
    </div>`;
}

function currentPageTemplate() {
  switch (state.page) {
    case "hall": return hallTemplate();
    case "collection": return collectionTemplate();
    case "codex": return codexTemplate();
    case "chronicle": return chronicleTemplate();
    case "field-guide": return fieldGuideTemplate();
    case "profile": return profileTemplate();
    case "battle": return battleTemplate();
    default: return hallTemplate();
  }
}

function render() {
  app.innerHTML = `<div class="game-shell">${topbarTemplate()}<main>${currentPageTemplate()}</main><footer class="footer-mark">by Nicolò, Sara, Antonio e Riccardo</footer></div>`;
  hydrateImages(app);
}

async function getImageUrl(monsterId) {
  if (!imageCache.has(monsterId)) {
    imageCache.set(
      monsterId,
      api(`/monsters/${encodeURIComponent(monsterId)}/image`, { raw: true })
        .then((blob) => URL.createObjectURL(blob))
        .catch((error) => {
          imageCache.delete(monsterId);
          throw error;
        }),
    );
  }
  return imageCache.get(monsterId);
}

function hydrateImages(root) {
  root.querySelectorAll("img[data-art]").forEach(async (image) => {
    try {
      image.src = await getImageUrl(image.dataset.art);
    } catch (error) {
      image.alt = `${image.alt} (unavailable)`;
      if (error.status !== 401) notify(error.message, "error");
    }
  });
}

async function refreshGameData() {
  const [profile, collection, catalog, history, tutorial] = await Promise.all([
    api(`/players/${encodeURIComponent(state.player.playerId)}`),
    api(`/players/${encodeURIComponent(state.player.playerId)}/collection`),
    api(`/monsters?playerId=${encodeURIComponent(state.player.playerId)}`),
    api(`/players/${encodeURIComponent(state.player.playerId)}/encounters?limit=100`),
    api("/tutorial"),
  ]);
  state.player = profile.player;
  state.collection = collection.monsters;
  state.teamIds = collection.team;
  state.catalog = catalog.monsters;
  state.history = history.encounters;
  state.tutorial = tutorial;
}

async function enterGame() {
  showLoading("The halls remember you…");
  try {
    const storedPlayer = localStorage.getItem("monsterTamerPlayer");
    state.player = storedPlayer ? JSON.parse(storedPlayer) : null;
    if (!state.player?.playerId) {
      authScreen("login");
      return;
    }
    await refreshGameData();
    localStorage.setItem("monsterTamerPlayer", JSON.stringify(state.player));
    state.page = "hall";
    render();
    if (state.justRegistered) {
      state.justRegistered = false;
      starterReveal();
    }
  } catch (error) {
    if (error.status === 404) {
      localStorage.removeItem("monsterTamerPlayer");
      authScreen("login", "Your session has ended. Sign in to continue.");
    } else {
      authScreen("login", error.message);
    }
  }
}

function openPage(page) {
  state.page = page;
  if (page === "collection") state.selectedTeam = new Set(state.teamIds);
  render();
}

async function submitAuth(form) {
  const mode = form.dataset.form;
  const data = Object.fromEntries(new FormData(form).entries());
  const button = form.querySelector('button[type="submit"]');
  const errorSlot = form.querySelector(".form-error");
  button.disabled = true;
  errorSlot.textContent = "";
  try {
    const response = mode === "register"
      ? await api("/players", { method: "POST", body: { ...data, bio: "" } })
      : await api("/auth/login", { method: "POST", body: data });
    state.player = response.player;
    state.justRegistered = mode === "register";
    localStorage.setItem("monsterTamerPlayer", JSON.stringify(state.player));
    await enterGame();
  } catch (error) {
    errorSlot.textContent = error.message;
    button.disabled = false;
  }
}

async function saveTeam() {
  if (state.selectedTeam.size !== 3) {
    notify("Choose exactly three companions.", "error");
    return;
  }
  try {
    await api(`/players/${encodeURIComponent(state.player.playerId)}/team`, {
      method: "PUT",
      body: { monsterIds: [...state.selectedTeam] },
    });
    state.teamIds = [...state.selectedTeam];
    notify("Your team is ready.");
    openPage("collection");
  } catch (error) {
    notify(error.message, "error");
  }
}

async function startBattle() {
  try {
    const battle = await api("/battles", {
      method: "POST",
      body: { playerId: state.player.playerId },
    });
    state.battle = battle;
    state.page = "battle";
    render();
    notify(battle.initiative === "player" ? "The coin favors you. Strike first." : "The boss won initiative.");
  } catch (error) {
    if (error.status === 409 && error.message.includes("active")) {
      notify(error.message, "error");
      return;
    }
    notify(error.message, "error");
  }
}

async function attack(monsterId, button) {
  button.disabled = true;
  button.textContent = "Resolving…";
  try {
    state.battle = await api(`/battles/${encodeURIComponent(state.battle.battleId)}/actions`, {
      method: "POST",
      body: { actionType: "attack", moveId: monsterId, playerId: state.player.playerId },
    });
    if (state.battle.finalized) await refreshGameData();
    render();
    if (state.battle.status === "won") notify(`${state.battle.boss.name} joined your collection.`);
    if (state.battle.status === "lost") notify("The encounter is over. Your team is restored.");
  } catch (error) {
    button.disabled = false;
    button.textContent = "Strike";
    notify(error.message, "error");
  }
}

async function abandonBattle() {
  if (!window.confirm("Withdraw from this encounter? It will be recorded as a defeat.")) return;
  try {
    state.battle = await api(`/battles/${encodeURIComponent(state.battle.battleId)}/actions`, {
      method: "POST",
      body: { actionType: "abandon", playerId: state.player.playerId },
    });
    await refreshGameData();
    render();
  } catch (error) {
    notify(error.message, "error");
  }
}

function openDetails(monsterId) {
  const monster = (state.battle?.boss.id === monsterId ? state.battle.boss : null)
    || state.catalog.find((entry) => entry.id === monsterId)
    || state.collection.find((entry) => entry.id === monsterId)
    || null;
  if (!monster) return;
  const stats = monster.stats || {};
  detailDialog.innerHTML = `
    <div class="detail-content">
      <img class="detail-image" data-art="${escapeHtml(monster.id)}" alt="${escapeHtml(monster.name)} card artwork">
      <div class="detail-copy">
        <button class="dialog-close" data-action="close-detail" aria-label="Close details" type="button">×</button>
        <div class="eyebrow">${escapeHtml(monster.rarity)} · ${monster.cfu} CFU</div>
        <h2>${escapeHtml(monster.name)}</h2>
        <p>${escapeHtml(monster.department)} · ${monster.owned ? "In your collection" : "Uncollected"}</p>
        <div class="detail-stat-grid">
          <div class="detail-stat"><strong>${stats.hp}</strong><span>Health</span></div>
          <div class="detail-stat"><strong>${stats.attack}</strong><span>Attack</span></div>
          <div class="detail-stat"><strong>${stats.defense}</strong><span>Defense</span></div>
        </div>
        ${matchupTemplate(monster)}
        <p>Higher credit value means greater rarity and stronger base statistics. In a wild encounter, a boss temporarily gains 150% to all three attributes (2.5x total).</p>
        <button class="button ghost small" data-action="close-detail" type="button">Close</button>
      </div>
    </div>`;
  detailDialog.showModal();
  hydrateImages(detailDialog);
}

function openHistoryDetails(battleId) {
  const encounter = state.history.find((entry) => entry.battleId === battleId);
  if (!encounter) return;
  const won = encounter.result === "win";
  detailDialog.innerHTML = `
    <div style="padding:clamp(20px,4vw,40px)">
      <button class="dialog-close" data-action="close-detail" aria-label="Close encounter details" type="button">×</button>
      <div class="eyebrow">${won ? "Victory" : encounter.outcome === "abandoned" ? "Withdrawn" : "Defeat"} · ${encounter.turns} turns</div>
      <h2 style="margin:.5rem 0 1.3rem;font:600 1.7rem var(--serif)">Encounter details</h2>
      <div class="detail-content">
        <img class="detail-image" data-art="${escapeHtml(encounter.boss.id)}" alt="${escapeHtml(encounter.boss.name)} card artwork">
        <div class="detail-copy">
          <div class="eyebrow">${escapeHtml(encounter.boss.rarity)} · ${encounter.boss.cfu} CFU</div>
          <h2>${escapeHtml(encounter.boss.name)}</h2>
          <p>${escapeHtml(encounter.boss.department)} · ${escapeHtml(new Date(encounter.completedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }))}</p>
          <div class="detail-stat-grid">
            <div class="detail-stat"><strong>${encounter.boss.stats.hp}</strong><span>Boss HP</span></div>
            <div class="detail-stat"><strong>${encounter.boss.stats.attack}</strong><span>Attack</span></div>
            <div class="detail-stat"><strong>${encounter.teamUsed.length}</strong><span>Companions</span></div>
          </div>
          ${matchupTemplate(encounter.boss)}
        </div>
      </div>
      <div class="eyebrow" style="margin:1.4rem 0 .8rem">Team used</div>
      <div class="card-grid">${encounter.teamUsed.map((card) => cardTemplate(card)).join("")}</div>
    </div>`;
  detailDialog.showModal();
  hydrateImages(detailDialog);
}

async function openGuide() {
  try {
    if (!state.tutorial) state.tutorial = await api("/tutorial");
    guideDialog.innerHTML = `
      <button class="dialog-close" data-action="close-guide" aria-label="Close field guide" type="button">×</button>
      <div class="eyebrow">A tamer's field guide</div><h2>${escapeHtml(state.tutorial.title)}</h2>
      <ol>${state.tutorial.rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ol>
      <button class="button primary" data-action="close-guide" type="button">Understood</button>`;
    guideDialog.showModal();
  } catch (error) {
    notify(error.message, "error");
  }
}

async function updateProfile(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await api(`/players/${encodeURIComponent(state.player.playerId)}`, {
      method: "PUT",
      body: data,
    });
    state.player = response.player;
    localStorage.setItem("monsterTamerPlayer", JSON.stringify(state.player));
    render();
    notify("Your profile has been inscribed.");
  } catch (error) {
    notify(error.message, "error");
  }
}

async function deleteAccount() {
  if (!window.confirm("Delete your account, collection, and encounter chronicle? This cannot be undone.")) return;
  try {
    await api(`/players/${encodeURIComponent(state.player.playerId)}`, { method: "DELETE" });
    clearSession();
    authScreen("register", "Your account and game records have been removed.");
  } catch (error) {
    notify(error.message, "error");
  }
}

function clearSession() {
  localStorage.removeItem("monsterTamerPlayer");
  for (const urlPromise of imageCache.values()) {
    urlPromise.then((url) => URL.revokeObjectURL(url)).catch(() => {});
  }
  imageCache.clear();
  state.player = null;
  state.collection = [];
  state.teamIds = [];
  state.catalog = [];
  state.history = [];
  state.battle = null;
}

async function logout() {
  clearSession();
  authScreen("login");
}

function starterReveal() {
  const starters = state.collection.filter((monster) => state.teamIds.includes(monster.id));
  detailDialog.innerHTML = `
    <div style="padding:clamp(20px,4vw,40px)">
      <div class="eyebrow">Your first companions</div><h2 style="margin:.5rem 0 1.3rem;font:600 1.7rem var(--serif)">The three cards choose their keeper.</h2>
      <div class="card-grid">${starters.map((monster) => cardTemplate(monster, { owned: true })).join("")}</div>
      <div style="margin-top:1.2rem;text-align:right"><button class="button primary" data-action="close-starters" type="button">Enter the academy</button></div>
    </div>`;
  detailDialog.showModal();
  hydrateImages(detailDialog);
}

app.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  if (form.dataset.form === "login" || form.dataset.form === "register") submitAuth(form);
  if (form.dataset.form === "profile") updateProfile(form);
});

app.addEventListener("change", (event) => {
  if (event.target.matches("[data-team-pick]")) {
    const monsterId = event.target.dataset.teamPick;
    if (event.target.checked) {
      if (state.selectedTeam.size >= 3) {
        event.target.checked = false;
        notify("Your active team has room for three cards.", "error");
        return;
      }
      state.selectedTeam.add(monsterId);
    } else {
      state.selectedTeam.delete(monsterId);
    }
    const card = event.target.closest(".subject-card");
    card?.classList.toggle("is-selected", event.target.checked);
    document.getElementById("team-count").textContent = `${state.selectedTeam.size} / 3 selected`;
    const saveButton = app.querySelector('[data-action="save-team"]');
    if (saveButton) saveButton.disabled = state.selectedTeam.size !== 3;
  }
  if (event.target.matches("[data-department]")) {
    state.department = event.target.value;
    render();
  }
});

document.addEventListener("click", async (event) => {
  const pageButton = event.target.closest("[data-page]");
  if (pageButton) {
    openPage(pageButton.dataset.page);
    return;
  }
  const filterButton = event.target.closest("[data-filter]");
  if (filterButton) {
    state.filter = filterButton.dataset.filter;
    render();
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  switch (button.dataset.action) {
    case "auth-switch":
      authScreen(app.querySelector('[data-form="login"]') ? "register" : "login");
      break;
    case "logout":
      await logout();
      break;
    case "save-team":
      await saveTeam();
      break;
    case "begin-battle":
    case "new-battle":
      await startBattle();
      break;
    case "resume-battle":
      state.page = "battle";
      render();
      break;
    case "attack":
      await attack(button.dataset.monster, button);
      break;
    case "abandon":
      await abandonBattle();
      break;
    case "return-hall":
      state.battle = null;
      openPage("hall");
      break;
    case "details":
      openDetails(button.dataset.monster);
      break;
    case "history-details":
      openHistoryDetails(button.dataset.battle);
      break;
    case "close-detail":
      detailDialog.close();
      break;
    case "close-guide":
      guideDialog.close();
      break;
    case "close-starters":
      detailDialog.close();
      break;
    case "delete-account":
      await deleteAccount();
      break;
    case "open-guide":
      await openGuide();
      break;
  }
});

detailDialog.addEventListener("click", (event) => {
  if (event.target === detailDialog) detailDialog.close();
});
guideDialog.addEventListener("click", (event) => {
  if (event.target === guideDialog) guideDialog.close();
});
window.addEventListener("pagehide", () => {
  for (const urlPromise of imageCache.values()) {
    urlPromise.then((url) => URL.revokeObjectURL(url)).catch(() => {});
  }
});

if (localStorage.getItem("monsterTamerPlayer")) {
  enterGame();
} else {
  authScreen("login");
}
