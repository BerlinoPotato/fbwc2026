/* World Cup 2026 Tracker — client logic.
   Reads data/wc2026.json (committed by the GitHub Action) and renders it.
   No backend, no keys. Times convert from kickoff_utc to the viewer's local zone. */

"use strict";

const FAV_KEY = "wc2026.favs";
// Default favourites (FIFA codes). Editable via the highlight chips; persisted to localStorage.
const DEFAULT_FAVS = ["NED", "CUW", "ENG", "JPN", "GER", "BEL", "FRA"];

const state = {
  data: null,
  favs: new Set(),
  view: "groups",
  schedFilter: "upcoming",
  schedFavOnly: false,
  searchTeamId: null,
};

/* ---------- utils ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "local time";
const fmtTime = (iso) => {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (isNaN(d)) return "TBD";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};
const fmtDayKey = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? "TBD" : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
};
const fmtRelDate = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
};

const isFav = (code) => code && state.favs.has(code);
const matchHasFav = (m) =>
  (m.home && isFav(m.home.code)) || (m.away && isFav(m.away.code));

/* ---------- favourites ---------- */
function loadFavs() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    state.favs = new Set(raw ? JSON.parse(raw) : DEFAULT_FAVS);
  } catch {
    state.favs = new Set(DEFAULT_FAVS);
  }
}
function saveFavs() {
  try { localStorage.setItem(FAV_KEY, JSON.stringify([...state.favs])); } catch { /* ignore */ }
}
function toggleFav(code) {
  if (state.favs.has(code)) state.favs.delete(code);
  else state.favs.add(code);
  saveFavs();
  renderChips();
  renderActiveView();
}

function renderChips() {
  const host = $("#fav-chips");
  host.innerHTML = "";
  const teams = state.data ? [...state.data.teams].sort((a, b) => a.name.localeCompare(b.name)) : [];
  // Show favourite teams first (and any default favs even if not yet in data won't show — data drives it)
  const ordered = teams.sort((a, b) => (isFav(b.code) - isFav(a.code)) || a.name.localeCompare(b.name));
  for (const t of ordered) {
    const c = el("button", "chip" + (isFav(t.code) ? " is-on" : ""));
    c.type = "button";
    c.setAttribute("aria-pressed", isFav(t.code));
    c.innerHTML = `<img src="${esc(t.flag)}" alt="" loading="lazy" onerror="this.style.display='none'"><span>${esc(t.name)}</span>`;
    c.addEventListener("click", () => toggleFav(t.code));
    host.appendChild(c);
  }
}

/* ---------- groups / standings ---------- */
function renderGroups() {
  const host = $("#groups-grid");
  host.innerHTML = "";
  const standings = state.data.standings || [];
  if (!standings.length) {
    host.appendChild(el("div", "state", "<h3>No group data yet</h3><p>Standings appear once group matches kick off.</p>"));
    return;
  }
  for (const g of [...standings].sort((a, b) => a.group.localeCompare(b.group))) {
    const card = el("div", "group-card");
    card.appendChild(el("div", "group-head", `Group ${esc(g.group)}`));
    const table = el("table", "stand-table");
    table.innerHTML = `
      <thead><tr>
        <th class="team-col">Team</th>
        <th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th>
      </tr></thead>`;
    const tb = el("tbody");
    g.rows.forEach((r, i) => {
      const tr = el("tr", isFav(r.code) ? "fav-row" : "");
      if (i === 2) tr.classList.add("qualify-line"); // top-2 advance line
      tr.innerHTML = `
        <td class="team-col"><div class="team-cell"><span class="pos">${i + 1}</span>
          <img src="${esc(r.flag)}" alt="" loading="lazy" onerror="this.style.display='none'">
          <span class="nm">${esc(r.name)}</span></div></td>
        <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
        <td>${r.gf}</td><td>${r.ga}</td><td>${r.gd > 0 ? "+" + r.gd : r.gd}</td>
        <td class="pts">${r.pts}</td>`;
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    card.appendChild(table);
    host.appendChild(card);
  }
}

/* ---------- match card ---------- */
function statusPill(m) {
  if (m.finished) return `<span class="status-pill ft">FT</span>`;
  if (m.status === "LIVE" || (m.time_elapsed && /\d/.test(m.time_elapsed) && m.time_elapsed !== "notstarted"))
    return `<span class="status-pill live">${esc(m.time_elapsed && m.time_elapsed !== "notstarted" ? m.time_elapsed : "LIVE")}</span>`;
  return "";
}
function teamSide(side, m) {
  const t = m[side];
  const label = m[side + "_label"];
  if (t) {
    const favCls = isFav(t.code) ? " style=\"\"" : "";
    return `<div class="mc-team ${side}">
      ${side === "away" ? `<img src="${esc(t.flag)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ""}
      <span class="nm">${esc(t.name)}</span>
      ${side === "home" ? `<img src="${esc(t.flag)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ""}
    </div>`;
  }
  return `<div class="mc-team ${side}"><span class="nm tbd">${esc(label || "TBD")}</span></div>`;
}
function matchCard(m) {
  const card = el("div", "match-card" + (matchHasFav(m) ? " fav-match" : ""));
  let center;
  if (m.finished || m.status === "LIVE") {
    const hs = m.home_score == null ? "-" : m.home_score;
    const as = m.away_score == null ? "-" : m.away_score;
    center = `<div class="score">${hs}<span class="sep">:</span>${as}</div>
              <div class="mc-meta">${statusPill(m)}</div>`;
  } else {
    center = `<div class="mc-time">${fmtTime(m.kickoff_utc)}</div>
              <div class="mc-date">${fmtRelDate(m.kickoff_utc)}</div>`;
  }
  const venue = m.stadium ? `${esc(m.stadium.name)} · ${esc(m.stadium.city)}` : "";
  const tag = m.type === "group" ? `Group ${esc(m.group)}` : esc((m.group || m.type || "").toUpperCase());
  card.innerHTML = `
    ${teamSide("home", m)}
    <div class="mc-center">${center}</div>
    ${teamSide("away", m)}`;
  const foot = el("div", "mc-meta");
  foot.style.gridColumn = "1 / -1";
  foot.style.textAlign = "center";
  foot.innerHTML = `${tag}${venue ? " · " + venue : ""}`;
  card.appendChild(foot);
  return card;
}

/* ---------- schedule ---------- */
function renderSchedule() {
  const host = $("#schedule-list");
  host.innerHTML = "";
  let list = [...state.data.matches];

  if (state.schedFilter === "upcoming") list = list.filter((m) => !m.finished);
  else if (state.schedFilter === "finished") list = list.filter((m) => m.finished);
  if (state.schedFavOnly) list = list.filter(matchHasFav);

  list.sort((a, b) => new Date(a.kickoff_utc || 0) - new Date(b.kickoff_utc || 0));
  if (state.schedFilter === "finished") list.reverse();

  if (!list.length) {
    host.appendChild(el("div", "state", "<h3>Nothing here yet</h3><p>Try a different filter.</p>"));
    return;
  }

  let lastDay = null;
  for (const m of list) {
    const day = fmtDayKey(m.kickoff_utc);
    if (day !== lastDay) {
      host.appendChild(el("div", "day-head", esc(day)));
      lastDay = day;
    }
    host.appendChild(matchCard(m));
  }
}

/* ---------- search ---------- */
function teamById(id) { return state.data.teams.find((t) => t.id === id); }
function teamMatches(teamId) {
  return state.data.matches
    .filter((m) => (m.home && m.home.id === teamId) || (m.away && m.away.id === teamId))
    .sort((a, b) => new Date(a.kickoff_utc || 0) - new Date(b.kickoff_utc || 0));
}
function renderSuggest(q) {
  const box = $("#search-suggest");
  q = q.trim().toLowerCase();
  if (!q) { box.classList.add("hidden"); return; }
  const hits = state.data.teams.filter((t) =>
    t.name.toLowerCase().includes(q) || (t.code || "").toLowerCase().includes(q)
  ).slice(0, 8);
  if (!hits.length) { box.classList.add("hidden"); return; }
  box.innerHTML = "";
  hits.forEach((t) => {
    const item = el("div", "suggest-item");
    item.innerHTML = `<img src="${esc(t.flag)}" alt="" onerror="this.style.display='none'">
      <span>${esc(t.name)}</span><span class="grp">Group ${esc(t.group)}</span>`;
    item.addEventListener("click", () => {
      $("#team-search").value = t.name;
      box.classList.add("hidden");
      state.searchTeamId = t.id;
      renderTeamDetail();
    });
    box.appendChild(item);
  });
  box.classList.remove("hidden");
}
function renderTeamDetail() {
  const host = $("#team-detail");
  host.innerHTML = "";
  if (!state.searchTeamId) return;
  const t = teamById(state.searchTeamId);
  if (!t) return;

  const head = el("div", "td-head");
  head.innerHTML = `
    <img src="${esc(t.flag)}" alt="" onerror="this.style.display='none'">
    <div>
      <h2>${esc(t.name)}</h2>
      <div class="sub">${esc(t.code)} · Group ${esc(t.group)}</div>
    </div>`;
  const favBtn = el("button", "chip td-fav" + (isFav(t.code) ? " is-on" : ""));
  favBtn.type = "button";
  favBtn.textContent = isFav(t.code) ? "★ Highlighted" : "☆ Highlight";
  favBtn.addEventListener("click", () => { toggleFav(t.code); renderTeamDetail(); });
  head.appendChild(favBtn);
  host.appendChild(head);

  const matches = teamMatches(t.id);
  if (!matches.length) {
    host.appendChild(el("div", "state", "<p>No matches found for this team.</p>"));
    return;
  }
  const list = el("div", "match-list");
  let lastDay = null;
  for (const m of matches) {
    const day = fmtDayKey(m.kickoff_utc);
    if (day !== lastDay) { list.appendChild(el("div", "day-head", esc(day))); lastDay = day; }
    list.appendChild(matchCard(m));
  }
  host.appendChild(list);
}

/* ---------- view switching ---------- */
function renderActiveView() {
  if (!state.data) return;
  if (state.view === "groups") renderGroups();
  else if (state.view === "schedule") renderSchedule();
  else if (state.view === "search") { renderTeamDetail(); }
}
function switchView(v) {
  state.view = v;
  $$(".tab").forEach((t) => {
    const on = t.dataset.view === v;
    t.classList.toggle("is-active", on);
    t.setAttribute("aria-selected", on);
  });
  $$(".view").forEach((s) => s.classList.toggle("hidden", s.dataset.view !== v));
  renderActiveView();
}

/* ---------- boot ---------- */
function showError(msg) {
  $("#groups-grid").innerHTML = "";
  $("#groups-grid").appendChild(
    el("div", "state", `<h3>Couldn't load data</h3><p>${esc(msg)}</p>`)
  );
}
function applyMeta() {
  const m = state.data.meta || {};
  const d = m.last_updated ? new Date(m.last_updated) : null;
  $("#updated-label").textContent = d && !isNaN(d)
    ? "Updated " + d.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "";
  $("#sample-badge").classList.toggle("hidden", !m.is_sample);
  $("#tz-label").textContent = TZ;
}

async function init() {
  loadFavs();
  // wire events
  $$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  $$(".seg-btn[data-sched]").forEach((b) => b.addEventListener("click", () => {
    state.schedFilter = b.dataset.sched;
    $$(".seg-btn[data-sched]").forEach((x) => x.classList.toggle("is-active", x === b));
    renderSchedule();
  }));
  $("#sched-favonly").addEventListener("change", (e) => { state.schedFavOnly = e.target.checked; renderSchedule(); });
  $("#fav-clear").addEventListener("click", () => { state.favs.clear(); saveFavs(); renderChips(); renderActiveView(); });
  $("#team-search").addEventListener("input", (e) => renderSuggest(e.target.value));
  $("#team-search").addEventListener("focus", (e) => renderSuggest(e.target.value));
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-box")) $("#search-suggest").classList.add("hidden");
  });

  try {
    const res = await fetch("data/wc2026.json?_=" + Math.floor(Date.now() / 60000));
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.data = await res.json();
  } catch (err) {
    showError(err.message + " — make sure data/wc2026.json exists.");
    return;
  }
  applyMeta();
  renderChips();
  switchView("groups");
}

document.addEventListener("DOMContentLoaded", init);
