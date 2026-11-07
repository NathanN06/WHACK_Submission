// Hypothesis Gauntlet: follows a quest ledger and plays it as a pixel-art dungeon crawl.
// Every animation is triggered by a ledger event the backend wrote; nothing here decides
// a result or an HP change. quest-state.js folds the events; this file shows them.

const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ROMAN = ["", "I", "II", "III", "IV", "V"];
const ABILITY_COLOR = { fact_check: "#ffe08a", bias_detection: "#ff9aa8", replication_shield: "#7fe0ff",
                        ablation_strike: "#ff8a3a", temporal_guard: "#d08aff", preregister: "#e8b847" };
const LESSONS = {
  1: "Popularity is not proof. A claim many people repeat is a lead to investigate, not evidence that it is true.",
  2: "A first study can mislead. Ask whether the evidence adds anything beyond what is already known, and for whom.",
  3: "Real effects replicate in independent groups and beat scrambled data. Try many claims and some will look good by luck.",
  4: "Only information available at the time counts, and a claim must hold on people it has never seen.",
};
const ACTOR = { researcher: "Researcher", skeptic: "Skeptic", judge: "Judge", agent: "Agent", system: "Gauntlet" };

let state = initialState();
let speed = 1, paused = false, playing = 0;
const queue = [];
let streamDone = false;

// ---------- the canvas world ----------

const canvas = $("#game-canvas");
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;
const scene = { mode: "level", level: 1, cam: 0, camTarget: 0, fade: 0, portal: false, marker: null, mapLevel: 1 };
const vis = {};       // hero id -> { x, y, tx, ty, flash, shake, alpha, dead, ghost, cast, skin, slot }
let foe = null;       // { kind, head, x, y, alpha, ta, flash, lunge, dying }
let particles = [], floaters = [];
let frame = 0;

const FIGHT = { hx: 204, ex: 268, y: 150 };

function slotOf(i) { return { x: 50 + Math.floor(i / 2) * 18, y: i % 2 ? 152 : 134 }; }

function ensureVis(id) {
  if (!vis[id]) {
    const i = state.order.indexOf(id);
    const s = slotOf(i);
    vis[id] = { x: -14 - i * 6, y: s.y, tx: s.x, ty: s.y, flash: 0, shake: 0, alpha: 1, dead: false,
                ghost: false, cast: null, castT: 0, skin: i, slot: i };
  }
  return vis[id];
}

function home(id) { const v = ensureVis(id); const s = slotOf(v.slot); v.tx = s.x; v.ty = s.y; }

function step() {
  frame++;
  scene.cam += Math.sign(scene.camTarget - scene.cam) * Math.min(1.5, Math.abs(scene.camTarget - scene.cam));
  for (const v of Object.values(vis)) {
    const sp = 1.6 * Math.min(speed, 3);
    v.x += Math.sign(v.tx - v.x) * Math.min(sp, Math.abs(v.tx - v.x));
    v.y += Math.sign(v.ty - v.y) * Math.min(sp, Math.abs(v.ty - v.y));
    v.flash = Math.max(0, v.flash - 1); v.shake = Math.max(0, v.shake - 1); v.castT = Math.max(0, v.castT - 1);
    if (v.ghost) { v.alpha = Math.max(0, v.alpha - 0.01); }
  }
  if (foe) {
    foe.alpha += Math.sign(foe.ta - foe.alpha) * Math.min(0.08, Math.abs(foe.ta - foe.alpha));
    foe.flash = Math.max(0, foe.flash - 1); foe.lunge = Math.max(0, foe.lunge - 1);
    if (foe.dying) for (let i = 0; i < 2; i++) burst(foe.x + (Math.random() - 0.5) * 16, foe.y - Math.random() * 20, foe.dyeColor || "#ffffff", 1);
  }
  particles = particles.filter((p) => (p.life -= 1) > 0);
  for (const p of particles) { p.x += p.vx; p.y += p.vy; p.vy += p.g; }
  floaters = floaters.filter((t) => (t.life -= 1) > 0);
  for (const t of floaters) t.y -= 0.35;
}

function burst(x, y, color, n = 14, spread = 1.4) {
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2, s = Math.random() * spread;
    particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 0.4, g: 0.04, life: 20 + Math.random() * 20, color });
  }
}

function floatText(x, y, text, color) { floaters.push({ x, y, text, color, life: 70 }); }

function draw() {
  ctx.clearRect(0, 0, 320, 180);
  if (scene.mode === "map") { drawWorldMap(ctx, frame, scene.mapLevel, scene.marker); return overlay(); }
  if (scene.mode === "overworld") {
    drawOverworld(ctx, frame);
    drawHeroes(0);
    drawFx(0);
    return overlay();
  }
  const cam = Math.round(scene.cam);
  ctx.drawImage(bakeLevel(scene.level), -cam, 0);
  ctx.save(); ctx.translate(-cam, 0); drawLevelFx(ctx, scene.level, frame); ctx.restore();
  if (scene.portal) { ctx.save(); ctx.translate(-cam, 0); portal(ctx, 336, 120, frame, "#e8b847"); ctx.restore(); }
  drawHeroes(cam);
  if (foe && foe.alpha > 0.02) {
    const lx = foe.lunge ? -Math.round(Math.sin(foe.lunge / 3) * 6) : 0;
    const shake = foe.flash ? (frame % 2 ? 1 : -1) : 0;
    const blink = foe.flash > 0 && frame % 4 < 2;
    drawEnemy(ctx, foe.kind, foe.x - cam + lx + shake, foe.y, frame, foe.head,
              { alpha: BOSSES[foe.kind] && blink ? foe.alpha * 0.4 : foe.alpha, flash: blink });
  }
  drawFx(cam);
  overlay();
}

function drawHeroes(cam) {
  const list = state.order.map((id) => [id, ensureVis(id)]).sort((a, b) => a[1].y - b[1].y);
  for (const [id, v] of list) {
    const h = state.heroes[id];
    const x = Math.round(v.x - cam), y = Math.round(v.y);
    if (v.dead) { tomb(ctx, x, y); continue; }
    if (v.alpha <= 0.02) continue;
    const moving = Math.abs(v.tx - v.x) > 0.5 || Math.abs(v.ty - v.y) > 0.5;
    const bob = moving ? (Math.floor(frame / 4) % 2) : 0;
    const shake = v.shake ? (frame % 2 ? 1 : -1) : 0;
    const img = heroSprite(h.cls, v.skin);
    ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.fillRect(x - 5, y - 1, 10, 2);
    blit(ctx, v.flash && frame % 4 < 2 ? flashOf(`hero:${h.cls}:${v.skin}`, img) : img, x + shake, y - bob,
         { alpha: v.ghost ? v.alpha * 0.6 : v.alpha });
    if (v.castT) { // ability aura
      const c = v.cast || "#ffe08a";
      for (let k = 0; k < 6; k++) { const a = frame / 6 + k; rect(ctx, x + Math.round(Math.cos(a) * 9), y - 8 + Math.round(Math.sin(a) * 9), 1, 1, c); }
    }
    if (!v.ghost) hpBar(x, y - 19, h.hp);
    if (h.prereg && scene.level === 4 && !v.ghost) lockIcon(x + 7, y - 20);
  }
}

function hpBar(x, y, hp) {
  rect(ctx, x - 6, y, 12, 2, "#0d0b1e");
  const w = Math.max(0, Math.round(hp / 100 * 12));
  rect(ctx, x - 6, y, w, 2, hp > 60 ? "#5fd67a" : hp > 30 ? "#e8b847" : "#e0405f");
}

function lockIcon(x, y) { rect(ctx, x, y + 2, 4, 3, "#e8b847"); rect(ctx, x + 1, y, 2, 2, "#e8b847"); rect(ctx, x + 1, y + 1, 2, 1, "#0d0b1e"); }

function tomb(c, x, y) {
  rect(c, x - 4, y - 10, 9, 10, "#4a4660"); rect(c, x - 3, y - 11, 7, 1, "#4a4660"); rect(c, x - 4, y - 10, 9, 1, "#6a6680");
  rect(c, x, y - 8, 1, 5, "#2a2838"); rect(c, x - 1, y - 7, 3, 1, "#2a2838");
}

function drawFx(cam) {
  for (const p of particles) rect(ctx, p.x - cam, p.y, 1, 1, p.color);
  for (const t of floaters) pixelText(ctx, t.text, t.x - cam, t.y, t.life < 12 && frame % 2 ? "#0d0b1e" : t.color);
}

function overlay() {
  if (scene.fade > 0) { // stepped fade, so it reads as pixel art
    ctx.fillStyle = `rgba(5,4,12,${(Math.round(scene.fade * 6) / 6).toFixed(2)})`;
    ctx.fillRect(0, 0, 320, 180);
  }
}

let lastTick = 0;
function loop(t) {
  if (t - lastTick >= 33) { lastTick = t; if (!paused) step(); draw(); }
  requestAnimationFrame(loop);
}

// ---------- timing ----------

let skipping = false;  // "Skip level": play events with no pauses until the level ends

async function wait(ms) {
  if (skipping) { await new Promise((r) => setTimeout(r, 0)); return; }
  let left = ms;
  while (left > 0) {
    await new Promise((r) => setTimeout(r, 30));
    if (!paused) left -= 30 * speed;
  }
}

async function fadeTo(target, ms = 360) {
  const from = scene.fade, steps = 6;
  for (let i = 1; i <= steps; i++) { scene.fade = from + (target - from) * (i / steps); await wait(ms / steps); }
}

// ---------- DOM panels ----------

function banner(title, text) {
  const b = $("#banner");
  if (!title) { b.hidden = true; return; }
  b.innerHTML = `<h2>${esc(title)}</h2>${text ? `<p>${esc(text)}</p>` : ""}`;
  b.hidden = false;
  b.style.animation = "none"; void b.offsetWidth; b.style.animation = "";
}

function speech(who, text) {
  const s = $("#speech");
  if (!text) { s.hidden = true; return; }
  s.className = `speech ${who.toLowerCase()}`;
  s.innerHTML = `<b>${esc(who)}:</b> ${esc(text)}`;
  s.hidden = false;
}

function portraitOf(canvasEl, draw) {
  const c = canvasEl.getContext("2d");
  c.imageSmoothingEnabled = false;
  c.clearRect(0, 0, canvasEl.width, canvasEl.height);
  draw(c);
}

function drawFoePortrait(kind, head) {
  portraitOf($("#foe-portrait"), (c) => {
    c.fillStyle = "#0d0b1e"; c.fillRect(0, 0, 48, 48);
    if (!kind) return;
    if (BOSSES[kind]) { c.save(); c.translate(24, 46); c.scale(0.75, 0.75); BOSSES[kind](c, 0, 0, frame, head); c.restore(); }
    else { const img = enemySprite(kind); c.drawImage(img, 8, 10, 32, 32); }
  });
}

function heroMini(id, size = 32) {
  const h = state.heroes[id], v = ensureVis(id);
  const c = document.createElement("canvas");
  c.width = 16; c.height = 16; c.className = "pixel";
  c.getContext("2d").drawImage(heroSprite(h.cls, v.skin), 0, 0);
  c.style.width = c.style.height = `${size}px`;
  return c;
}

function barClass(hp) { return hp > 60 ? "" : hp > 30 ? "mid" : "low"; }
function verdictTag(v) {
  if (!v) return "";
  const cls = v === "VALIDATED" ? "good" : (v === "FALLEN" || v === "LOOK-AHEAD") ? "bad" : "";
  return `<span class="tag-v ${cls}">${esc(v)}</span>`;
}

const hitAt = {};
function renderParty() {
  const list = $("#party-list");
  const activeId = state.encounter && state.encounter.hero;
  list.innerHTML = "";
  for (const id of state.order) {
    const h = state.heroes[id];
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = `member ${id === activeId ? "active" : ""} ${h.status !== "questing" && h.verdict !== "VALIDATED" ? "out" : ""}`;
    btn.type = "button";
    btn.appendChild(heroMini(id));
    const info = document.createElement("div");
    info.innerHTML = `<div class="nm"><b>${esc(h.name)}</b><span>${h.status === "questing" ? `HP ${h.hp} · ${h.credits} cr` : verdictTag(h.verdict || h.status.toUpperCase())}</span></div>
      <div class="cl">${esc(h.cls)} · ${esc(h.claim)}</div>
      <div class="bar ${barClass(h.hp)} ${hitAt[id] ? "hit" : ""}"><i style="width:${h.hp}%"></i></div>`;
    btn.appendChild(info);
    btn.addEventListener("click", () => showHero(id));
    li.appendChild(btn);
    list.appendChild(li);
  }
  for (const k in hitAt) delete hitAt[k];
  const all = state.order.map((id) => state.heroes[id]);
  $("#hud-standing").textContent = `${all.filter((h) => h.status === "questing").length}/${all.length}`;
  $("#hud-checks").textContent = all.reduce((n, h) => n + h.passed + h.failed, 0);
  $("#hud-caught").textContent = all.reduce((n, h) => n + h.failed, 0);
}

function renderHud() {
  const L = state.levels[state.level] || state.levels[String(state.level)];
  if (!L) return;
  $("#hud-num").textContent = ROMAN[state.level] || "";
  $("#hud-name").textContent = L.name;
  $("#hud-evidence").textContent = `Evidence: ${L.evidence}`;
}

function renderCombat() {
  const enc = state.encounter;
  if (!enc) return;
  const meta = ENEMIES[enc.enemy] || { name: enc.enemy };
  const h = state.heroes[enc.hero];
  $("#c-enemy").textContent = meta.head ? `${meta.name}: ${meta.head}` : meta.name;
  $("#c-hero").textContent = h ? `vs ${h.name} the ${h.cls}` : "";
  $("#c-attack").textContent = (enc.attack || "").replace(/^[^:]+:\s*/, "");
  $("#c-claim").textContent = h ? h.claim : "—";
  const ab = ABILITIES[enc.ability] || "—";
  $("#c-action").innerHTML = !enc.action
    ? (enc.cost ? `${esc(ab)} <small>(costs ${enc.cost} credit${enc.cost > 1 ? "s" : ""})</small>` : esc(ab))
    : enc.action.kind === "concede" ? `<span class="fail">Concede</span>: ${esc(enc.action.line)}`
    : `${esc(ab)}: ${esc(enc.action.line)}`;
  $("#c-test").textContent = TESTS[enc.test] || enc.test || "—";
  $("#c-result").innerHTML = enc.result == null ? (enc.action && enc.action.kind === "concede" ? "Not tested" : "…")
    : `<span class="${enc.untestable ? "" : enc.passed ? "pass" : "fail"}">${enc.untestable ? "?" : enc.passed ? "✓" : "✗"}</span> ${esc(enc.result)}`;
  const hp = $("#c-hp");
  hp.className = enc.delta < 0 ? "dmg" : enc.delta > 0 ? "heal" : "";
  hp.textContent = enc.delta == null ? "…" : enc.delta === 0 ? "±0" : `${enc.delta > 0 ? "+" : ""}${enc.delta}`;
  $("#c-explain").textContent = enc.explain || "…";
}

function renderFeed() {
  $("#feed").innerHTML = state.feed.slice(0, 200).map((f) => {
    const mark = f.passed === true ? `<span class="pass">✓</span> ` : f.passed === false ? `<span class="fail">✗</span> ` : "";
    const d = f.delta ? ` <b class="${f.delta < 0 ? "fail" : "pass"}">${f.delta > 0 ? "+" : ""}${f.delta} HP</b>` : "";
    return `<li><span class="who ${f.actor}">L${f.level ?? "-"} ${ACTOR[f.actor] || f.actor}</span>${f.hero ? `<b>${esc(f.hero)}</b> ` : ""}${mark}${esc(f.line)}${d}</li>`;
  }).join("");
}

function renderAll() { renderHud(); renderParty(); renderCombat(); renderFeed(); }

function showHero(id) {
  const h = state.heroes[id];
  const rows = state.feed.filter((f) => f.hero === h.name && (f.action === "result" || f.action === "concede" || f.action === "revise"))
    .slice().reverse().map((f) => `<tr><td>L${f.level}</td><td>${f.passed === true ? '<span class="pass">✓</span>' : f.passed === false ? '<span class="fail">✗</span>' : "·"} ${esc(f.line)}</td><td>${f.delta ? `${f.delta > 0 ? "+" : ""}${f.delta}` : ""}</td></tr>`).join("");
  const d = $("#hero-card");
  d.innerHTML = `<h2>${esc(h.name)} the ${esc(h.cls)}</h2>
    <p class="sub">${esc(h.claim)}</p>
    <div class="totals"><div><b>${h.hp}</b><small>HP</small></div><div><b>${h.credits}</b><small>credits left</small></div>
      <div><b>${h.passed}</b><small>checks passed</small></div><div><b>${h.failed}</b><small>checks failed</small></div>
      <div><b>${h.conceded}</b><small>challenges conceded</small></div></div>
    <p>Evidence used: <b>${esc((h.features || []).join(", "))}</b> · claimed direction: ${esc(h.direction)}${h.revised ? " (revised)" : ""}
      ${h.verdict ? ` · ${verdictTag(h.verdict)}` : ""}</p>
    <h3>Tests and decisions</h3>
    <table><tr><th>Lvl</th><th>What happened</th><th>HP</th></tr>${rows || "<tr><td colspan=3>Nothing yet.</td></tr>"}</table>
    <form method="dialog" class="actions"><button class="btn gold">Close</button></form>`;
  d.showModal();
}

function showRules() {
  const r = state.rules;
  const d = $("#rules");
  const enc = r ? Object.entries(r.encounters) : [];
  const rows = enc.map(([k, e]) => `<tr><td>${ROMAN[e.level]}</td><td>${esc(e.head ? `${e.name}: ${e.head}` : e.name)}</td>
    <td>${e.kind === "gate" ? "always" : "Skeptic's choice"}</td><td>${esc((r.abilities || {})[e.ability] || e.ability)}</td>
    <td>${esc(TESTS[e.test] || e.test)}</td><td>${e.cost}</td>
    <td>${e.damage ? `−${e.damage}${e.damage_severe ? ` (−${e.damage_severe} if contradicted)` : ""}` : e.test === "coverage" || e.test === "provenance" ? "exit if untestable" : "0"}</td></tr>`).join("");
  d.innerHTML = `<h2 tabindex="-1">The Rulebook</h2>
    <p class="sub">HP is a game measure of research integrity, not a probability. Every change comes from one row below and one deterministic test.</p>
    <div class="lesson">Each hypothesis agent starts with <b>${r ? r.starting_hp : 100} HP</b> and <b>${r ? r.starting_credits : 18} research credits</b>.
      A passed check restores <b>+${r ? r.pass_heal : 5} HP</b>. The Skeptic sends up to two optional challenges per level; the agent either pays to defend
      (the test runs) or concedes (<b>−${r ? r.concede_damage : 5} HP</b>, claim stays unverified). Statistics are computed by the backend engine, never by an LLM.</div>
    ${r ? `<table class="rules-table"><tr><th>Lvl</th><th>Enemy</th><th>When</th><th>Ability</th><th>Test executed</th><th>Credits</th><th>HP if failed</th></tr>${rows}</table>
    <h3>Who wins</h3><div class="lesson">A claim is <b>VALIDATED</b> only if it passes the Preprint Mimic, the Chimera's overfitting test, the Publication Bias Knight,
      the Chronolock Guardian, the Leakage Reaper and the Guardian of False Discoveries. The best researcher has the highest defensibility score:
      HP left + ${r.score.level_cleared} per level cleared + ${r.score.check_passed} per check passed ${r.score.redundant} per redundant check
      + ${r.score.credit_left} per unspent credit + ${r.score.validated} if validated. Running more tests does not win on its own.</div>` :
      "<p>The rules load when a quest starts.</p>"}
    <form method="dialog" class="actions"><button class="btn gold">Close</button></form>`;
  d.showModal();
  d.scrollTop = 0; d.querySelector("h2").focus();
}

// ---------- level complete + finale ----------

let continueResolve = null;
async function levelComplete(e) {
  const L = e.result;
  scene.portal = true;
  foe = null;
  for (const id of state.order) if (state.heroes[id].status === "questing") home(id);
  banner("Level complete", "");
  await wait(900);
  banner(null);
  const rows = state.order.map((id) => {
    const h = state.heroes[id], b = h.byLevel[L.level];
    if (!b) return "";
    return `<tr><td>${heroMini(id, 24).outerHTML}${esc(h.name)} <small>${esc(h.cls)}</small></td>
      <td><span class="bar ${barClass(h.hp)}"><i style="width:${h.hp}%"></i></span>${h.hp}</td>
      <td>${b.spent}</td><td>${b.passed}</td><td>${b.failed}</td><td>${b.conceded}</td>
      <td>${h.status === "questing" ? (L.level < 4 ? "Onward" : "Survived") : verdictTag(h.verdict || h.status.toUpperCase())}</td></tr>`;
  }).join("");
  const d = $("#level-done");
  d.innerHTML = `<h2 tabindex="-1">Level complete</h2><p class="sub">${esc(L.name)} · ${L.cleared.length} of ${state.order.length} still standing</p>
    <table><tr><th>Agent</th><th>HP left</th><th>Credits spent</th><th>Passed</th><th>Failed</th><th>Conceded</th><th>Status</th></tr>${rows}</table>
    <div class="lesson"><b>Lesson:</b> ${esc(LESSONS[L.level] || "")}</div>
    <form method="dialog" class="actions"><button class="btn gold" value="go">${L.level < 4 ? "Enter the portal" : "Emerge into the world"}</button></form>`;
  d.showModal();
  d.scrollTop = 0; d.querySelector("h2").focus();
  await new Promise((r) => {
    continueResolve = r;
    d.addEventListener("close", r, { once: true });
    if (skipping) { skipping = false; $("#skip").disabled = false; }
    if (autoContinue) wait(9000).then(() => { if (d.open) d.close(); });
  });
  continueResolve = null;
  for (const id of state.order) if (state.heroes[id].status === "questing") { const v = ensureVis(id); v.tx = 340; v.ty = 122; }
  await wait(1400);
  await fadeTo(1);
  scene.portal = false;
}

async function finale(e) {
  const F = e.result;
  scene.mode = "overworld";
  $("#hud-num").textContent = "✦";
  $("#hud-name").textContent = "The Overworld";
  $("#hud-evidence").textContent = `${F.validated} hypothes${F.validated === 1 ? "is" : "es"} emerged validated`;
  for (const id of state.order) {
    const v = ensureVis(id), h = state.heroes[id];
    v.dead = false; v.ghost = false;
    const ok = F.ranking.find((r) => r.id === id);
    v.alpha = ok && ok.verdict === "VALIDATED" ? 1 : 0;
    v.x = 30; v.y = 150; const rank = F.ranking.indexOf(ok);
    v.tx = 90 + rank * 16; v.ty = 150;
  }
  await fadeTo(0);
  await wait(1200);
  const rank = F.ranking.map((r, i) => `<tr><td>${i + 1}</td><td>${heroMini(r.id, 24).outerHTML}${esc(r.name)} <small>${esc(r.cls)}</small></td>
    <td>${esc(r.claim)}</td><td>${verdictTag(r.verdict)}</td><td>${r.hp}</td><td>${r.score}</td></tr>`).join("");
  const decoys = F.decoys.map((d) => `<li><b>${esc(d.name)}</b> was secretly <i>${esc(d.decoy.replace(/_/g, " "))}</i>: ${d.caught ? '<span class="pass">caught</span>' : '<span class="fail">slipped through</span>'} (${esc(d.verdict)})</li>`).join("");
  const t = F.totals;
  const dlg = $("#finale");
  dlg.innerHTML = `<h2 tabindex="-1">${F.validated ? "Out of the dungeon" : "The evidence is inconclusive"}</h2>
    <p class="conclusion">${esc(F.conclusion)}</p>
    <div class="totals"><div><b>${t.tests_attempted}</b><small>tests attempted</small></div><div><b>${t.credits_spent}</b><small>credits spent</small></div>
      <div><b>${t.invalid_claims_detected}</b><small>weak claims detected</small></div><div><b>${t.useful_evidence}</b><small>checks passed</small></div>
      <div><b>${t.redundant}</b><small>redundant checks</small></div><div><b>${F.caught}/${F.decoys.length}</b><small>impostors caught</small></div></div>
    <h3>Final standings</h3>
    <table><tr><th>#</th><th>Agent</th><th>Hypothesis</th><th>Verdict</th><th>HP</th><th>Score</th></tr>${rank}</table>
    ${decoys ? `<h3>The impostors revealed</h3><ul>${decoys}</ul><div class="lesson">Impostors are hypotheses whose truth we planted:
      pure noise, the luckiest of 100 noise columns, a copy of carbs, and a score built from the answer. Catching them shows the gauntlet can tell luck from discovery.</div>` : ""}
    <form method="dialog" class="actions"><button class="btn gold" value="again">New quest</button><button class="btn" value="stay">Stay and inspect</button></form>`;
  dlg.showModal();
  dlg.scrollTop = 0; dlg.querySelector("h2").focus();
}

$("#finale").addEventListener("close", () => { if ($("#finale").returnValue === "again") location.href = location.pathname; });

// ---------- playing one event ----------

let autoContinue = true;

async function play(e) {
  const before = state.encounter && state.encounter.hero;
  reduce(state, e);
  if (e.agent_id) ensureVis(e.agent_id);
  const id = e.agent_id, v = id && vis[id], h = id && state.heroes[id];
  switch (e.action) {
    case "quest_start":
      renderAll();
      break;
    case "recruit":
      renderParty(); renderFeed();
      await wait(120);
      break;
    case "level_start": {
      foe = null; speech(null); banner(null);
      await fadeTo(1);
      scene.mode = "map";
      const from = MAP_NODES[Math.max(0, e.level - 2)], to = MAP_NODES[e.level - 1];
      scene.mapLevel = e.level; scene.marker = { x: from.x, y: from.y };
      await fadeTo(0);
      const L = state.levels[e.level];
      banner(`Level ${ROMAN[e.level]} · ${L.name}`, `${L.evidence}. ${L.blurb}`);
      for (let i = 0; i <= 20; i++) { scene.marker = { x: from.x + (to.x - from.x) * i / 20, y: from.y + (to.y - from.y) * i / 20 }; await wait(60); }
      await wait(1300);
      await fadeTo(1);
      banner(null);
      scene.mode = "level"; scene.level = e.level; scene.cam = 0; scene.camTarget = 0;
      for (const hid of state.order) {
        const hv = ensureVis(hid), hh = state.heroes[hid];
        if (hh.status === "questing") { hv.x = -12 - hv.slot * 8; hv.y = slotOf(hv.slot).y; home(hid); hv.alpha = 1; hv.dead = false; hv.ghost = false; }
        else { hv.alpha = 0; hv.dead = false; hv.x = -40; }
      }
      renderAll();
      await fadeTo(0);
      banner(L.name, L.blurb);
      await wait(1400);
      banner(null);
      break;
    }
    case "plan":
      speech("Skeptic", `${h.name}: ${e.line}`);
      renderParty();
      await wait(450);
      break;
    case "encounter": {
      speech(null);
      if (before && before !== id && vis[before] && state.heroes[before].status === "questing") home(before);
      v.tx = FIGHT.hx; v.ty = FIGHT.y;
      const meta = ENEMIES[e.enemy] || {};
      const sameFoe = foe && foe.kind === e.enemy && foe.alpha > 0.5 && !foe.dying;
      if (!sameFoe) foe = { kind: e.enemy, head: meta.head, x: FIGHT.ex, y: FIGHT.y, alpha: 0, ta: 1, flash: 0, lunge: 0, dying: false };
      foe.head = meta.head;
      scene.camTarget = 40;
      drawFoePortrait(e.enemy, meta.head);
      renderCombat(); renderParty(); renderFeed();
      await wait(sameFoe ? 450 : (meta.boss ? 1200 : 700));
      break;
    }
    case "defend":
      v.cast = ABILITY_COLOR[state.encounter && state.encounter.ability] || "#ffe08a"; v.castT = 30;
      burst(v.x, v.y - 8, v.cast, 10, 0.8);
      speech("Researcher", `${h.name}: ${e.line}`);
      renderCombat(); renderParty();
      await wait(500);
      speech(null);
      break;
    case "concede":
      v.flash = 10; v.shake = 8; hitAt[id] = true;
      floatText(v.x, v.y - 24, `${e.hp_delta}`, "#e0405f");
      speech("Researcher", `${h.name}: ${e.line}`);
      if (foe) foe.lunge = 12;
      renderCombat(); renderParty(); renderFeed();
      await wait(900);
      speech(null);
      if (foe) foe.ta = 0;
      break;
    case "prereg":
      v.cast = "#e8b847"; v.castT = 40; burst(v.x, v.y - 20, "#e8b847", 16, 0.6);
      speech("Researcher", e.line);
      renderFeed();
      await wait(900);
      speech(null);
      break;
    case "result": {
      const ab = state.encounter && state.encounter.ability;
      const col = ABILITY_COLOR[ab] || "#ffe08a";
      if (v) { v.cast = col; v.castT = 14; }
      // the ability bolt travels to the enemy
      if (foe && v) for (let i = 0; i < 8; i++) { const t = i / 8; particles.push({ x: v.x + (foe.x - v.x) * t, y: v.y - 10, vx: 0.4, vy: 0, g: 0, life: 6 + i * 2, color: col }); }
      await wait(300);
      if (e.result && e.result.untestable) {
        floatText(v.x, v.y - 24, "0", "#b9b0cc");
      } else if (e.passed) {
        if (foe) { foe.flash = 12; foe.dying = true; foe.dyeColor = col; foe.ta = 0; }
        burst(foe ? foe.x : v.x, v.y - 12, col, 22);
        if (e.hp_delta > 0) floatText(v.x, v.y - 24, `+${e.hp_delta}`, "#5fd67a");
      } else {
        if (foe) foe.lunge = 14;
        v.flash = 14; v.shake = 10; hitAt[id] = true;
        burst(v.x, v.y - 8, "#e0405f", 14);
        if (e.hp_delta) floatText(v.x, v.y - 24, `${e.hp_delta}`, "#e0405f");
        scene.camTarget = 38;
      }
      renderCombat(); renderParty(); renderFeed();
      await wait(e.passed ? 1000 : 1400);
      if (foe && !e.passed) foe.ta = 0;
      break;
    }
    case "fall":
      v.flash = 20; burst(v.x, v.y - 8, "#b9b0cc", 24);
      banner(`${h.name} has fallen`, e.explain);
      renderParty(); renderFeed();
      await wait(1100);
      v.dead = true; home(id);
      banner(null);
      if (foe) foe.ta = 0;
      break;
    case "exit":
      v.ghost = true; v.tx = -30;
      speech("Judge", `${e.line} ${e.explain}`);
      renderParty(); renderFeed();
      await wait(1100);
      speech(null);
      break;
    case "broke":
      speech("Judge", e.line);
      renderParty(); renderFeed();
      await wait(900);
      speech(null);
      break;
    case "census":
      banner("The Publication Bias Knight", e.line);
      for (const hid of state.order) if (state.heroes[hid].status === "questing") home(hid);
      renderFeed();
      await wait(1800);
      banner(null);
      break;
    case "revise":
      v.cast = "#7fe0ff"; v.castT = 30; burst(v.x, v.y - 10, "#7fe0ff", 12, 0.7);
      speech("Researcher", `${h.name}: ${e.line}`);
      renderParty(); renderFeed();
      await wait(1000);
      speech(null);
      break;
    case "level_complete":
      renderAll();
      await levelComplete(e);
      break;
    case "finale":
      renderAll();
      await finale(e);
      break;
    case "error":
      banner("The quest was halted", e.line);
      renderFeed();
      break;
    default:
      renderFeed();
      if (e.line && e.actor === "system") { speech("Gauntlet", e.line); await wait(900); speech(null); }
  }
}

async function pump() {
  if (playing) return;
  playing = 1;
  while (queue.length) await play(queue.shift());
  playing = 0;
}

function enqueue(events) { queue.push(...events); pump(); }

// ---------- sources: live backend, or a recorded ledger file ----------

async function follow(questId) {
  let after = 0;
  for (;;) {
    const res = await fetch(`/api/quests/${questId}/events?after=${after}`);
    if (!res.ok) { banner("Lost the quest", await res.text()); return; }
    const body = await res.json();
    enqueue(body.events);
    after += body.events.length;
    if (body.done && body.events.length === 0) { streamDone = true; return; }
    await new Promise((r) => setTimeout(r, 700));
  }
}

async function playFile(url) {
  const text = await (await fetch(url)).text();
  enqueue(text.trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)));
  streamDone = true;
}

// ---------- screens + controls ----------

let stopTitle = false;
function titleLoop() {
  const c = $("#title-canvas").getContext("2d");
  c.imageSmoothingEnabled = false;
  let f = 0;
  const tick = () => { if (stopTitle) return; f++; drawTitleScene(c, f); setTimeout(() => requestAnimationFrame(tick), 33); };
  tick();
}

function enterGame() {
  stopTitle = true;
  $("#screen-title").hidden = true;
  $("#screen-game").hidden = false;
  scene.fade = 1;
  requestAnimationFrame(loop);
}

function clampParty(n) { return Math.max(1, Math.min(12, Math.round(Number(n)) || 1)); }
$("#fewer").addEventListener("click", () => { $("#party").value = clampParty(Number($("#party").value) - 1); });
$("#more").addEventListener("click", () => { $("#party").value = clampParty(Number($("#party").value) + 1); });
$("#party").addEventListener("change", () => { $("#party").value = clampParty($("#party").value); });

$("#begin").addEventListener("click", async () => {
  $("#begin").disabled = true;
  try {
    const res = await fetch("/api/quests", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify({ max_heroes: clampParty($("#party").value) }) });
    if (!res.ok) throw new Error(await res.text());
    const { quest_id } = await res.json();
    enterGame();
    follow(quest_id);
  } catch (err) {
    $("#who").textContent = `The gauntlet server isn't answering (${err.message.slice(0, 80)}). Try the recorded quest.`;
    $("#begin").disabled = false;
  }
});

$("#demo").addEventListener("click", () => { enterGame(); playFile("demo-quest.jsonl"); });
$("#how").addEventListener("click", async () => {
  if (!state.rules) {
    try { const r = await (await fetch("/api/quests-rules")).json(); state.rules = r; }
    catch {
      try { const first = (await (await fetch("demo-quest.jsonl")).text()).split("\n")[0]; state.rules = JSON.parse(first).result; } catch { /* stays empty */ }
    }
  }
  showRules();
});
$("#rulebook").addEventListener("click", showRules);

$("#pause").addEventListener("click", () => {
  paused = !paused;
  $("#pause").setAttribute("aria-pressed", String(paused));
  $("#pause").textContent = paused ? "Resume" : "Pause";
});
for (const b of document.querySelectorAll(".speed")) b.addEventListener("click", () => {
  speed = Number(b.dataset.speed);
  for (const o of document.querySelectorAll(".speed")) o.setAttribute("aria-pressed", String(o === b));
});
document.addEventListener("keydown", (ev) => {
  if (!$("#screen-title").hidden && (ev.key === "Enter")) { ev.preventDefault(); $("#begin").click(); }
  if ($("#screen-game").hidden || document.querySelector("dialog[open]")) return;
  if (ev.key === " ") { ev.preventDefault(); $("#pause").click(); }
  if (["1", "2", "4"].includes(ev.key)) document.querySelector(`.speed[data-speed="${ev.key}"]`).click();
});

async function loadStatus() {
  try {
    const { claude } = await (await fetch("/api/status")).json();
    $("#who").textContent = claude ? "Claude plays the Researcher and the Skeptic. The statistics engine is the Judge."
                                   : "Scripted Researcher and Skeptic tonight (no API key in .env). The statistics engine is the Judge.";
  } catch {
    $("#who").textContent = "No gauntlet server running: watch the recorded quest.";
  }
}

const params = new URLSearchParams(location.search);
if (params.get("file") || params.has("demo")) { enterGame(); playFile(params.get("file") || "demo-quest.jsonl"); }
else { titleLoop(); loadStatus(); }
if (params.has("fast")) document.querySelector('.speed[data-speed="4"]').click();
$("#skip").addEventListener("click", () => { if (state.level >= 1 && state.level <= 4) { skipping = true; $("#skip").disabled = true; } });
