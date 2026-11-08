// The Peptide & GLP-1 edition game screen: title, playback, battle stage, console, Test Inspector and ledger.
// One hero (the Alchemist) carries three hypothesis scrolls; the Gatekeeper Skeptic speaks at each gate.
// Every number drawn comes from a ledger row (pep-state.js folds them); nothing here computes a statistic.

const $ = (id) => document.getElementById(id);
const ROMAN = { 1: "I", 2: "II", 3: "III", 4: "IV" };
const FALLBACK_CAMPAIGNS = ["A", "B", "C", "D"];

const G = {
  campaigns: [], pick: "A", server: false, claude: false,
  mode: null, questId: null, poll: null, token: 0,
  state: initial(), pending: [], done: false,
  running: true, speed: 1, nextAt: 0, hold: false,
  reduced: window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  f: 0, fx: [], shake: 0, lunge: null, pinned: null, bubbleUntil: 0,
  filters: { agent: "", level: "", kind: "", text: "" },
  typer: null,
  seen: new Set(), interactive: false,   // ledger rows already applied; whether the Director's console is live
};

// ---------- title ----------

async function boot() {
  $("motion").setAttribute("aria-pressed", String(G.reduced));
  titleLoop();
  try {
    const st = await fetch("/api/status").then((r) => (r.ok ? r.json() : Promise.reject()));
    G.server = true; G.claude = !!st.claude;
  } catch { G.server = false; }
  try {
    if (!G.server) throw new Error("static");
    G.campaigns = await fetch("/api/campaigns").then((r) => r.json());
  } catch {
    G.campaigns = [];
    for (const L of FALLBACK_CAMPAIGNS) {
      try {
        const first = (await fetch(`demo/demo-${L}.jsonl`).then((r) => r.text())).split("\n", 1)[0];
        G.campaigns.push({ ...JSON.parse(first).result.campaign, simulated: true });
      } catch { /* missing demo */ }
    }
  }
  renderCards();
  $("llm-wrap").hidden = !G.claude;
  $("who").textContent = G.server
    ? (G.claude ? "Server ready. Claude can play the Alchemist, or the hero follows each scroll's scripted plan."
                : "Server ready. The Alchemist follows each scroll's scripted plan (add an API key to let Claude play).")
    : "No server here: Begin plays the recorded run of the campaign you pick.";
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("watch")) { G.pick = hash.get("watch").toUpperCase(); startGame("demo"); }
}

function renderCards() {
  $("cards").innerHTML = G.campaigns.map((c) => `
    <button class="card" role="radio" aria-checked="${c.letter === G.pick}" data-letter="${c.letter}">
      <span class="card-letter">${c.letter}</span>
      <strong>${esc(c.title)}</strong>
      <span class="card-q">${esc(c.question)}</span>
      <span class="card-meta">${esc(c.drug)} vs ${esc((c.comparator || "").replace(/ \(active comparator\)/, ""))} <em>SIMULATED</em></span>
    </button>`).join("");
  for (const b of document.querySelectorAll(".card")) {
    b.onclick = () => { G.pick = b.dataset.letter; renderCards(); };
  }
}

function titleLoop() {
  const ctx = crispContext($("title-canvas"));
  const tick = () => {
    if (!$("screen-title").hidden) { drawTitleScene(ctx, G.f++); }
    requestAnimationFrame(tick);
  };
  tick();
}

// ---------- starting, polling, exiting ----------

async function startGame(mode) {
  G.token += 1;
  const token = G.token;
  Object.assign(G, { mode, state: initial(), pending: [], done: false, running: true, hold: false, pinned: null,
                     fx: [], questId: null, nextAt: 0, seen: new Set(), interactive: false });
  $("screen-title").hidden = true; $("screen-room").hidden = true; $("screen-bridge").hidden = true; $("screen-game").hidden = false;
  $("ledger").tBodies[0].innerHTML = ""; $("f-agent").innerHTML = '<option value="">Everyone</option>';
  G.bubbleUntil = 0; $("gate-bubble").hidden = true;
  setRun(true); renderAll();
  ticker("Opening the campaign…", "");
  if (mode === "live" && G.server) {
    try {
      const res = await fetch("/api/quests", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign: G.pick, llm: G.claude && $("llm").checked, interactive: true }) });
      if (!res.ok) throw new Error(await res.text());
      G.questId = (await res.json()).quest_id;
      G.interactive = true;
      pollLive(token, 0);
    } catch (err) {
      ticker("Could not start a live campaign, so the recorded run plays instead.", String(err).slice(0, 160));
      loadDemo(token);
    }
  } else {
    loadDemo(token);
  }
  maybeTutorial();
}

async function loadDemo(token) {
  G.mode = "demo";
  const text = await fetch(`demo/demo-${G.pick}.jsonl`).then((r) => r.text());
  if (token !== G.token) return;
  G.pending.push(...text.split("\n").filter(Boolean).map((l) => JSON.parse(l)));
  G.done = true;
}

async function pollLive(token, after) {
  if (token !== G.token) return;
  try {
    const body = await fetch(`/api/quests/${G.questId}/events?after=${after}`).then((r) => r.json());
    G.pending.push(...body.events);
    after += body.events.length;
    if (body.done) { G.done = true; return; }
  } catch { /* transient: try again */ }
  G.poll = setTimeout(() => pollLive(token, after), 350);
}

function exitGame() {
  if (G.mode === "live" && G.questId && !G.state.finale) {
    fetch(`/api/quests/${G.questId}/stop`, { method: "POST" }).catch(() => {});
  }
  G.token += 1; clearTimeout(G.poll);
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  $("screen-game").hidden = true; $("screen-room").hidden = true; $("screen-bridge").hidden = true; $("screen-title").hidden = false;
  history.replaceState(null, "", location.pathname);
}

// ---------- playback ----------

function setRun(on) {
  G.running = on;
  $("run").textContent = on ? "Pause" : "Run";
  $("run").setAttribute("aria-pressed", String(on));
  if (on) G.nextAt = 0;
}

function apply(e, quiet = false) {
  if (G.seen.has(e.seq)) return;   // the console's own rows can arrive twice: in its reply and from the poll
  G.seen.add(e.seq);
  reduce(G.state, e);
  appendLedger(e);
  if (quiet) return;
  onEvent(e);
}

function onEvent(e) {
  const s = G.state;
  if (e.action === "quest_start") fillAgentFilter();
  if (e.action === "recruit") fillAgentFilter();
  if (e.line) ticker(e.line, e.explain || "");
  if (e.action === "level_start") banner(`Level ${ROMAN[e.level]}: ${e.result.name}`, e.result.trap);
  if (e.action === "encounter" && e.result.boss) banner(e.result.enemy.name, "BOSS");
  if (e.action === "result" || e.action === "mystery_result") {
    if (!G.pinned) inspect(e);
    const d = e.hp_delta || 0;
    if (d) G.fx.push({ id: e.agent_id, text: d > 0 ? `+${d}` : `${d}`, color: d > 0 ? "#5fd67a" : "#ff4a5a", t0: performance.now() });
    else if (e.passed) G.fx.push({ id: e.agent_id, text: "0", color: "#7fe0ff", t0: performance.now() });
    if (d < 0 && !G.reduced) G.shake = performance.now() + 220;
    G.lunge = { id: e.agent_id, t0: performance.now(), hit: d < 0 };
  }
  if (e.action === "shatter") {
    banner(`${s.agents[e.agent_id]?.name || "A scroll"} shatters`, "0 HP: research integrity gone");
    if (!G.reduced) G.shake = performance.now() + 380;
  }
  if (e.action === "gatekeeper" || e.action === "benchmark") speak(e.result.text, e.action === "benchmark");
  if (e.action === "level_complete") {
    showLevelDone(e.result);
    if (G.interactive) directorPost("advance", { level: e.result.level }).catch(() => {});  // the quest may compute the next level
  }
  if (typeof directorEvent === "function") directorEvent(e);
  if (typeof bridgeEvent === "function") bridgeEvent(e);
  if (e.action === "finale" && $("screen-bridge").hidden) finaleReached();
  if (e.action === "stopped" || e.action === "error") ticker(e.line, "");
  renderAll();
}

function step(now) {
  if (G.hold || !G.running || !G.pending.length) return;
  if (now < G.nextAt) return;
  const e = G.pending.shift();
  apply(e);
  G.nextAt = now + beat(e) / G.speed * (G.reduced ? 0.8 : 1);
}

function stepOnce() {
  setRun(false);
  if (G.hold) { closeLevelDone(); return; }
  // advance to the next row worth looking at
  while (G.pending.length) {
    const e = G.pending.shift();
    const big = ["result", "decision", "encounter", "level_start", "level_complete", "finale", "shatter", "gatekeeper",
                 "benchmark"].includes(e.action);
    apply(e, !big);
    if (big) break;
  }
  renderAll();
}

function skipLevel() {
  if (G.hold) closeLevelDone();
  const lvl = G.state.level;
  while (G.pending.length) {
    const e = G.pending[0];
    if (e.action === "level_complete" || e.action === "finale") { G.pending.shift(); apply(e); return; }
    if (e.action === "level_start" && e.level !== lvl && lvl !== 0) break;
    G.pending.shift();
    apply(e, true);
  }
  const lastResult = [...G.state.events].reverse().find((x) => x.action === "result");
  if (lastResult && !G.pinned) inspect(lastResult);
  renderAll();
}

// ---------- the battle stage ----------

const HOME = [[36, 100], [70, 84], [104, 100]];  // where each scroll floats above the Alchemist (feet, 2x)
const HERO = [70, 168];
const FRONT = [170, 138];   // the scroll under test floats out to face the enemy
const GATE = [302, 166];    // the Gatekeeper watches from the far side
let STAGE = null;

function scrollAt(s, id) {
  const i = s.order.indexOf(id), a = s.agents[id];
  return s.fighter === id && s.enemy && a && a.status === "active" ? FRONT : HOME[i % HOME.length];
}

function stageLoop() {
  const ctx = crispContext($("stage"));
  STAGE = ctx;
  const frame = (now) => {
    if (!$("screen-game").hidden) {
      step(now);
      drawStage(ctx, now);
      G.f++;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function aura(ctx, x, y, r, rgb, k) {
  const g = ctx.createRadialGradient(x, y, 2, x, y, r);
  g.addColorStop(0, `rgba(${rgb},${k})`); g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
}

function drawStage(ctx, now) {
  const s = G.state;
  const level = Math.min(4, Math.max(1, s.level || 1));
  const f = G.reduced ? 0 : G.f;
  ctx.save();
  ctx.clearRect(0, 0, 320, 180);
  if (G.shake > now) ctx.translate(Math.round(Math.random() * 4 - 2), Math.round(Math.random() * 2 - 1));
  ctx.drawImage(bakeLevel(level), -20, 0);
  ctx.save(); ctx.translate(-20, 0); drawLevelFx(ctx, level, f); ctx.restore();
  if (s.secret && typeof drawSecretFx === "function") drawSecretFx(ctx, f);
  // the Gatekeeper Skeptic, once it has spoken this level
  if (s.gate) {
    if (s.benchmark && level === 4) aura(ctx, GATE[0], GATE[1] - 16, 34, "127,224,255", 0.22);
    const img = pepSprite("Gatekeeper");
    ctx.save(); ctx.translate(GATE[0], GATE[1]); ctx.scale(2, 2); blit(ctx, img, 0, 0, { flip: true }); ctx.restore();
  }
  // the enemy
  if (s.enemy && s.enemy.key) {
    aura(ctx, 252, 132, 70, "255,230,180", 0.34);  // a pool of light so dark foes read
    const L = G.lunge && now - G.lunge.t0 < 500 ? G.lunge : null;
    const ex = 252 - (L && L.hit && !G.reduced ? Math.sin((now - L.t0) / 500 * Math.PI) * 30 : 0);
    if (BOSSES[s.enemy.key]) drawBossOutlined(ctx, s.enemy.key, Math.round(ex), 162, f, 2);
    else { ctx.save(); ctx.translate(Math.round(ex), 162); ctx.scale(3, 3); drawEnemy(ctx, s.enemy.key, 0, 0, f, false); ctx.restore(); }
  }
  // the Alchemist
  const hero = pepSprite("Alchemist");
  const hb = G.reduced ? 0 : Math.round(Math.sin(G.f / 16) * 0.6);
  ctx.save(); ctx.translate(HERO[0], HERO[1] + hb); ctx.scale(3, 3); blit(ctx, hero, 0, 0); ctx.restore();
  // a thread of light from the flask to the scroll under test
  const fid = s.fighter && s.enemy && s.agents[s.fighter] && s.agents[s.fighter].status === "active" ? s.fighter : null;
  if (fid) for (let k = 1; k < 12; k++) {
    if ((k + Math.floor(f / 4)) % 3) continue;
    const t = k / 12, x = HERO[0] + 16 + (FRONT[0] - HERO[0] - 16) * t, y = HERO[1] - 22 + (FRONT[1] - 12 - HERO[1] + 22) * t;
    rect(ctx, x, y, 1, 1, "#7fe0ff");
  }
  // the three scrolls
  s.order.forEach((id, i) => {
    const a = s.agents[id];
    const [x, fy0] = scrollAt(s, id);
    if (a.status !== "active") {
      ctx.save(); ctx.translate(x, fy0 + 4); ctx.scale(2, 2); drawAsh(ctx, 0, 0); ctx.restore();
      return;
    }
    const fy = fy0 + (G.reduced ? 0 : Math.round(Math.sin(G.f / 12 + i * 2) * 1.5));
    const img = scrollSprite(a.archetype);
    const fighting = id === fid;
    if (fighting) aura(ctx, x, fy - 12, 26, "255,224,138", 0.5 + (G.reduced ? 0 : 0.15 * Math.sin(G.f / 6)));
    else if (s.active === id) aura(ctx, x, fy - 12, 18, "255,224,138", 0.28);
    const L = G.lunge && G.lunge.id === id && now - G.lunge.t0 < 400 ? G.lunge : null;
    const flash = L && L.hit && !G.reduced && (now - L.t0) % 120 < 60;
    ctx.save(); ctx.translate(x, fy); ctx.scale(2, 2);
    blit(ctx, flash ? flashOf(`scroll:${a.archetype}`, img) : img, 0, 0);
    ctx.restore();
    // floating HP bar, credit pips and buff dots
    const top = fy - img.height * 2 - 6;
    rect(ctx, x - 13, top, 26, 4, "#0d0b1e");
    const w = Math.round(24 * Math.max(0, a.hp) / 100);
    rect(ctx, x - 12, top + 1, w, 2, a.hp > 50 ? "#5fd67a" : a.hp > 25 ? "#e8b847" : "#ff4a5a");
    pixelText(ctx, String(a.hp), x, top - 7, "#f3e9d2");
    const c = Math.round(a.credits / 20);
    for (let k = 0; k < c; k++) rect(ctx, x - 12 + k * 4, top + 5, 3, 2, "#e8b847");
    a.buffs.slice(0, 6).forEach((_, k) => rect(ctx, x + 11, top + 9 + k * 4, 3, 3, "#7fe0ff"));
  });
  // floating damage numbers
  G.fx = G.fx.filter((p) => now - p.t0 < 1100);
  for (const p of G.fx) {
    if (!s.agents[p.id]) continue;
    const [fx, fy] = scrollAt(s, p.id);
    const rise = G.reduced ? 0 : (now - p.t0) / 1100 * 14;
    pixelText(ctx, p.text, fx + 18, fy - 34 - rise, p.color);
  }
  ctx.restore();
}

// The Gatekeeper's speech bubble over the stage.
function speak(text, benchmark) {
  const b = $("gate-bubble");
  b.innerHTML = `<small>${benchmark ? "The Gatekeeper sets the benchmark" : "Warden of the Null, the Gatekeeper Skeptic"}</small>${esc(text)}`;
  b.hidden = false;
  G.bubbleUntil = performance.now() + 3200 / G.speed;
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.hidden = true; renderEnemy(); }, 3200 / G.speed);
}

// ---------- HTML around the stage ----------

function renderAll() {
  renderNodes(); renderParty(); renderEnemy(); renderHud();
  $("ledger-count").textContent = `${G.state.events.length} rows`;
}

function renderNodes() {
  $("nodes").innerHTML = nodeStates(G.state).map((n) =>
    `<li class="${n.done ? "done" : ""} ${n.current ? "current" : ""}" title="${esc(n.name)}"><b>${n.numeral}</b><span>${esc(n.name)}</span></li>`)
    .join('<li class="arrow" aria-hidden="true">→</li>');
}

const portraitCache = {};
function portrait(key) {  // "hero", "gatekeeper", or a scroll archetype
  if (portraitCache[key]) return portraitCache[key];
  const img = key === "hero" ? pepSprite("Alchemist") : key === "gatekeeper" ? pepSprite("Gatekeeper") : scrollSprite(key);
  const big = img.width > 12, k = big ? 2 : 3, c = document.createElement("canvas");
  c.width = 48; c.height = 48;
  const ctx = c.getContext("2d"); ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, Math.round((48 - img.width * k) / 2), big ? 48 - img.height * k : Math.round((48 - img.height * k) / 2), img.width * k, img.height * k);
  return (portraitCache[key] = c.toDataURL());
}

function renderParty() {
  const s = G.state;
  const standing = s.order.filter((id) => s.agents[id].status === "active").length;
  const hero = s.hero ? `<li class="pcard hero-card">
      <img src="${portrait("hero")}" alt="" width="48" height="48">
      <div class="pinfo"><strong>${esc(s.hero.short || s.hero.name)}</strong> <small>the hero</small>
        <div class="meta"><span>${standing} of ${s.order.length} scrolls intact</span></div>
        <div class="buffs"><span>chooses abilities, never numbers</span></div></div></li>` : "";
  $("party").innerHTML = hero + s.order.map((id) => {
    const a = s.agents[id];
    const st = a.status !== "active" ? "fallen" : (s.fighter === id && s.enemy ? "fighting" : "");
    const cast = a.abilities[s.level] || [];
    return `<li class="pcard ${st} a-${a.archetype}" title="${esc(a.claim)}">
      <img src="${portrait(a.archetype)}" alt="" width="48" height="48">
      <div class="pinfo"><strong>${esc(a.name.replace(/^The /, ""))}</strong> <small>${esc(a.title)}</small>
        <div class="hp"><i style="width:${Math.max(0, a.hp)}%"></i><span>${a.hp} HP</span></div>
        <div class="meta"><span title="Research credits left">◆ ${a.credits}</span>
          ${a.verdict ? `<span class="verdict v-${a.verdict.replace(/\s/g, "")}">${esc(a.verdict)}</span>` : ""}
          ${cast.map((k) => `<span class="cast">${esc(abilityName(k))}</span>`).join("")}</div>
        <div class="buffs">${a.buffs.map((b) => `<span>${esc(b)}</span>`).join("")}</div>
      </div></li>`;
  }).join("");
}

// Top-left HUD: the scroll the Alchemist is holding up right now.
function renderHud() {
  const s = G.state, a = s.agents[s.fighter && s.enemy ? s.fighter : s.active];
  const hud = $("hud");
  if (!a) { hud.hidden = true; return; }
  hud.hidden = false;
  hud.className = `hud a-${a.archetype} ${a.status !== "active" ? "fallen" : ""}`;
  hud.innerHTML = `<img src="${portrait(a.archetype)}" alt="" width="30" height="30"><div><strong>${esc(a.name)}</strong>
    <div class="hp"><i style="width:${Math.max(0, a.hp)}%"></i><span>${a.hp} HP</span></div>
    <small>◆ ${a.credits} · ${a.design === "new_user" || a.buffs.includes("TIME-ZERO ALIGNED") ? "time-zero aligned" : "as carried"}</small></div>`;
}

function abilityName(k) { return (G.state.rules && G.state.rules.abilities[k] && G.state.rules.abilities[k].name) || k; }

function renderEnemy() {
  const e = G.state.enemy, plate = $("enemy-plate");
  if (!e || !e.key || performance.now() < G.bubbleUntil) { plate.hidden = true; return; }
  plate.hidden = false;
  plate.innerHTML = `<strong>${esc(e.name)}</strong>${e.boss ? ' <em>BOSS</em>' : ""}<small>${esc(e.test || "")}</small>`;
}

function banner(title, sub) {
  const b = $("banner");
  b.innerHTML = `<strong>${esc(title)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}`;
  b.hidden = false;
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.hidden = true; }, 1800 / G.speed);
}

function ticker(line, explain) {
  clearInterval(G.typer);
  const el = $("tick-line");
  $("tick-explain").textContent = explain || "";
  if (G.reduced || G.speed >= 4) { el.textContent = line; return; }
  let i = 0;
  el.textContent = "";
  G.typer = setInterval(() => {
    i += 2 * G.speed;
    el.textContent = line.slice(0, i);
    if (i >= line.length) clearInterval(G.typer);
  }, 16);
}

// ---------- Test Inspector ----------

function enemyInfo(level, key) {
  const info = G.state.levelInfo[level];
  return (info && info.enemies.find((x) => x.key === key)) || {};
}

function inspect(e) {
  const s = G.state;
  $("insp-id").textContent = e.encounter ? e.encounter.encounterId : `row ${e.seq}`;
  const a = e.agent_id ? s.agents[e.agent_id] : null;
  let html = "";
  if (G.pinned) html += `<p class="pin">Showing ledger row ${e.seq}. <button class="linkbtn" id="unpin">Follow the live fight</button></p>`;
  if (e.action === "result") {
    const r = e.result, en = enemyInfo(e.level, e.enemy), tele = e.encounter || {}, cr = tele.combatResolution || {};
    const dmax = s.rules ? s.rules.d_max[e.level] : "";
    html += `<div class="insp-head"><strong>${esc(en.name || e.enemy)}</strong> vs <strong>${esc(a ? a.name : "")}</strong>
      ${r.scout ? '<span class="tag">scout: measures, deals no damage</span>' : ""}
      ${r.na ? '<span class="tag">not applicable</span>' : ""}</div>
      <dl class="insp">
        <dt>Test</dt><dd>${esc(en.test || "")}</dd>
        <dt>Ability</dt><dd>${esc(tele.heroAction && tele.heroAction !== "NONE" ? abilityName(tele.heroAction) : "none used")}</dd>
        <dt>Formula</dt><dd><code>${esc(r.formula || "")}</code></dd>
        <dt>Result</dt><dd>${esc(e.line || "")}</dd>
        <dt>In plain English</dt><dd>${esc(e.explain || "")}</dd>
      </dl>`;
    if (r.chart) html += chartHTML(r.chart);
    const nums = Object.entries(r.numbers || {});
    if (nums.length) html += `<table class="nums">${nums.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${fmt(v)}</td></tr>`).join("")}</table>`;
    if (tele.encounterId) {
      html += `<div class="clamp"><span>ΔHP = −round(clamp(D<sub>raw</sub> × M, 0, D<sub>max</sub>))</span>
        <span>= −round(clamp(${fmt(cr.rawDamage)} × ${fmt(cr.abilityMultiplier)}, 0, ${dmax}))${r.heal ? ` + ${r.heal} heal` : ""}</span>
        <strong class="${cr.clampedHpDelta < 0 ? "neg" : cr.clampedHpDelta > 0 ? "pos" : ""}">= ${cr.clampedHpDelta > 0 ? "+" : ""}${cr.clampedHpDelta} HP</strong></div>
        <details><summary>Telemetry record (PepEncounterTelemetry)</summary><pre>${esc(JSON.stringify(tele, null, 2))}</pre></details>`;
    }
  } else {
    const r = e.result || {};
    html += `<div class="insp-head"><strong>${esc(e.action.replace(/_/g, " "))}</strong>${a ? ` · ${esc(a.name)}` : ""}
      ${e.encounter && e.encounter.mysteryId ? `<span class="tag">Mystery ${esc(e.encounter.mysteryId)}</span>` : ""}</div>
      <p>${esc(e.line || "")}</p>${e.explain ? `<p class="muted">${esc(e.explain)}</p>` : ""}`;
    if (r.formula) html += `<dl class="insp"><dt>Rule</dt><dd><code>${esc(r.formula)}</code></dd></dl>`;
    if (r.chart) html += chartHTML(r.chart);
    const nums = Object.entries(r.numbers || {});
    if (nums.length) html += `<table class="nums">${nums.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${fmt(v)}</td></tr>`).join("")}</table>`;
    if (e.encounter) html += `<details><summary>Telemetry record</summary><pre>${esc(JSON.stringify(e.encounter, null, 2))}</pre></details>`;
    if (e.action === "decision") {
      const picks = (e.result && e.result.abilities) || [];
      html += `<p>Cast: ${picks.length ? picks.map((k) => `<span class="cast">${esc(abilityName(k))}</span>`).join(" ") : "nothing"}
        ${e.cost ? ` for ${e.cost} credits` : ""}. Chosen by ${esc((e.result && e.result.source) === "claude" ? "Claude, as the Alchemist" : "the scroll's scripted plan")}.</p>`;
    }
  }
  $("insp-body").innerHTML = html;
  const un = $("unpin");
  if (un) un.onclick = () => { G.pinned = null; const last = [...s.events].reverse().find((x) => x.action === "result"); if (last) inspect(last); };
}

// ---------- ledger ----------

function whoOf(e) {
  const a = e.agent_id && G.state.agents[e.agent_id];
  if (e.action === "gatekeeper" || e.action === "benchmark") return "Gatekeeper";
  if (e.actor === "director") return "Director";
  if (e.action === "hero_reply" || e.action === "self_assessment") return "Hero";
  return a ? a.name.replace(/^The /, "") : e.actor === "judge" ? "Judge" : "System";
}

function rowHTML(e) {
  const d = e.hp_delta;
  return `<tr data-seq="${e.seq}" class="k-${e.action}"><td>${e.seq}</td><td>${ROMAN[e.level] || ""}</td><td>${esc(whoOf(e))}</td>
    <td>${esc(e.line || e.action)}</td><td class="${d < 0 ? "neg" : d > 0 ? "pos" : ""}">${d ? (d > 0 ? "+" : "") + d : ""}</td></tr>`;
}

function appendLedger(e) {
  if (!filterEvents([e], G.filters).length) return;
  $("ledger").tBodies[0].insertAdjacentHTML("afterbegin", rowHTML(e));
}

function rebuildLedger() {
  $("ledger").tBodies[0].innerHTML = filterEvents(G.state.events, G.filters).reverse().map(rowHTML).join("");
}

function fillAgentFilter() {
  const sel = $("f-agent"), cur = sel.value;
  sel.innerHTML = '<option value="">Everyone</option>' + G.state.order.map((id) =>
    `<option value="${id}">${esc(G.state.agents[id].name)}</option>`).join("") + '<option value="gatekeeper">The Gatekeeper</option>';
  sel.value = cur;
}

// ---------- level complete ----------

function showLevelDone(r) {
  const s = G.state, dlg = $("level-done");
  G.hold = true;
  const rows = r.rows.map((x) => `<tr class="${x.status !== "active" ? "fallen" : ""}"><td>${esc(x.name)}</td>
    <td>${x.hp}${x.hp_lost ? ` <span class="neg">−${x.hp_lost}</span>` : ""}</td><td>${x.credits}</td>
    <td>${x.abilities.map((k) => esc(abilityName(k))).join(", ") || "—"}</td>
    <td>${x.falsified.map(esc).join(", ") || "—"}</td><td class="neg">${x.sprung.map(esc).join(", ") || "—"}</td></tr>`).join("");
  const md = r.most_damaging;
  dlg.innerHTML = `<h2>Level ${ROMAN[r.level]} cleared</h2><p class="sub">${esc(r.name)} · ${r.standing} of ${s.order.length} scrolls intact</p>
    <table><thead><tr><th>Scroll</th><th>HP</th><th>Credits</th><th>Abilities cast</th><th>Traps falsified</th><th>Traps sprung</th></tr></thead>
    <tbody>${rows}</tbody></table>
    ${md ? `<p class="most">Most damaging enemy: <strong>${esc(md.name)}</strong> (${esc(md.trap)}), ${md.hp_dealt} HP dealt.</p>` : ""}
    <div class="dlg-buttons"><button class="btn gold" id="ld-go">Continue <span id="ld-count"></span></button></div>`;
  dlg.showModal();
  $("ld-go").onclick = closeLevelDone;
  let n = Math.ceil(6 / G.speed);
  const tick = () => {
    if (!dlg.open) return;
    if (!G.running) { $("ld-count").textContent = ""; dlg._t = setTimeout(tick, 500); return; }
    $("ld-count").textContent = `(${n})`;
    if (n-- <= 0) closeLevelDone(); else dlg._t = setTimeout(tick, 1000);
  };
  tick();
}

function closeLevelDone() {
  const dlg = $("level-done");
  clearTimeout(dlg._t);
  if (dlg.open) dlg.close();
  G.hold = false; G.nextAt = 0;
}

function finaleReached() {
  banner("The Citadel opens", "To the Research Brief");
  setTimeout(() => { if (G.state.finale && !$("screen-game").hidden) showRoom(); }, 2200 / G.speed);
}

// ---------- tutorial and how it works ----------

const TUTORIAL = [
  ["The battle stage", "One hero, the Alchemist-Epidemiologist, carries three hypothesis scrolls into four dungeons. Each scroll has its own research integrity (HP, the bar above it), credits (gold pips) and buffs (blue dots). A scroll at 0 HP shatters into ash; the hero walks on."],
  ["The Gatekeeper", "The Warden of the Null speaks at every gate and sets the benchmark in the Citadel: the matched active comparator with no drug effect. It is not a scroll. A scroll is validated only if it predicts unseen patients better than that benchmark."],
  ["The combat console", "Every ruling is typed out here. Run or pause, change the speed, Step one ruling at a time, or skip the rest of a level."],
  ["The Test Inspector", "Each fight shows the test the Statistical Judge ran, the data behind it, the formula with its numbers, and the clamp that turns it into HP."],
  ["The evidence ledger", "Every row is append-only and filterable. The hero only chooses abilities: every number comes from the Judge. Click any row to inspect it."],
];

function maybeTutorial(force = false) {
  let seen = false;
  try { seen = localStorage.getItem("pep-tutorial") === "1"; } catch { /* private mode */ }
  if (seen && !force) return;
  let i = 0;
  const dlg = $("tutorial"), was = G.running;
  setRun(false);
  const show = () => {
    const [t, b] = TUTORIAL[i];
    dlg.innerHTML = `<h3>${i + 1} / ${TUTORIAL.length} · ${esc(t)}</h3><p>${esc(b)}</p>
      <div class="dlg-buttons"><button class="btn ghost" id="tut-skip">Skip</button><button class="btn gold" id="tut-next">${i < TUTORIAL.length - 1 ? "Next" : "Start"}</button></div>`;
    $("tut-next").onclick = () => { if (++i < TUTORIAL.length) show(); else done(); };
    $("tut-skip").onclick = done;
  };
  const done = () => { try { localStorage.setItem("pep-tutorial", "1"); } catch { /* ignore */ } dlg.close(); setRun(was || !force); };
  show();
  dlg.showModal();
}

async function showHow() {
  const dlg = $("how-dlg");
  let rules = null;
  try {
    rules = G.server ? await fetch("/api/quests-rules").then((r) => r.json())
      : JSON.parse((await fetch(`demo/demo-${G.pick}.jsonl`).then((r) => r.text())).split("\n", 1)[0]).result.rules;
  } catch { /* shown without the tables */ }
  const levels = rules ? Object.entries(rules.levels).map(([l, v]) => `<tr><td>${ROMAN[l]}</td><td>${esc(v.name)}</td><td>${esc(v.trap)}</td><td><code>${esc(v.rule)}</code></td><td>${rules.d_max[l]}</td></tr>`).join("") : "";
  const abil = rules ? Object.values(rules.abilities).map((a) => `<tr><td>${esc(a.name)}</td><td>${ROMAN[a.level]}</td><td>${a.cost}</td><td>${esc(a.effect)}</td></tr>`).join("") : "";
  dlg.innerHTML = `<h2>How it works</h2>
    <p>Each campaign is a <strong>simulated</strong> world with planted, known effects: an EHR cohort across five sites,
    a social-media corpus, a literature base and a trial registry for each claim. Nothing in it is a real finding or
    medical advice. The truth is revealed at the end so you can see whether the Judge got it right.</p>
    <p>One hero, the Alchemist-Epidemiologist, carries three hypothesis scrolls: a Hype Scroll found on social media,
    a Mechanistic Scroll framed by a clinician, and a Preprint Scroll from a small study. Each scroll starts with
    100 HP (research integrity) and 100 credits, and the hero buys abilities for it each level. The hero never
    produces a number: the deterministic Statistical Judge measures everything and applies fixed rules,
    <code>ΔHP = −round(clamp(D_raw × M, 0, D_max))</code>. A scroll at 0 HP shatters.</p>
    <p>The final boss, the Guardian of False Discoveries, matches unseen holdout patients on the propensity score and
    compares each scroll's predictions with the Gatekeeper's benchmark: the active comparator with no drug effect.
    A scroll is <strong>validated</strong> only if it lowers the prediction loss (SS<sub>oos</sub> &gt; 0.002) and a
    paired loss test says the gain is unlikely to be luck (p &lt; 0.05). If none is, the verdict is
    <strong>Baseline Holds</strong>.</p>
    ${levels ? `<h3>Levels</h3><table><thead><tr><th></th><th>Level</th><th>Trap</th><th>Damage rule</th><th>D<sub>max</sub></th></tr></thead><tbody>${levels}</tbody></table>` : ""}
    ${abil ? `<h3>Abilities</h3><table><thead><tr><th>Ability</th><th>Level</th><th>Cost</th><th>Effect</th></tr></thead><tbody>${abil}</tbody></table>` : ""}
    <h3>Composite score</h3><p>0.35 × out-of-sample skill + 0.25 × HP + 0.25 × traps falsified + 0.15 × efficiency (lift per credit).</p>
    <div class="dlg-buttons"><button class="btn gold" id="how-close">Close</button></div>`;
  dlg.showModal();
  $("how-close").onclick = () => dlg.close();
}

// ---------- wiring ----------

function wire() {
  $("begin").onclick = () => startGame(G.server ? "live" : "demo");
  $("demo").onclick = () => startGame("demo");
  $("how").onclick = showHow;
  $("run").onclick = () => setRun(!G.running);
  for (const b of document.querySelectorAll(".speed")) {
    b.onclick = () => {
      G.speed = Number(b.dataset.speed);
      for (const o of document.querySelectorAll(".speed")) o.setAttribute("aria-pressed", String(o === b));
    };
  }
  $("step").onclick = stepOnce;
  $("skip").onclick = skipLevel;
  $("exit").onclick = exitGame;
  $("tutorial-btn").onclick = () => maybeTutorial(true);
  $("motion").onclick = () => { G.reduced = !G.reduced; $("motion").setAttribute("aria-pressed", String(G.reduced)); };
  const refilter = () => {
    G.filters = { agent: $("f-agent").value, level: $("f-level").value, kind: $("f-kind").value, text: $("f-text").value };
    rebuildLedger();
  };
  for (const id of ["f-agent", "f-level", "f-kind"]) $(id).onchange = refilter;
  $("f-text").oninput = refilter;
  $("ledger").tBodies[0].onclick = (ev) => {
    const tr = ev.target.closest("tr");
    if (!tr) return;
    const e = G.state.events.find((x) => x.seq === Number(tr.dataset.seq));
    if (e) { G.pinned = e.seq; inspect(e); }
  };
  document.addEventListener("keydown", (ev) => {
    if ($("screen-game").hidden || ev.target.matches("input, select, textarea") || document.querySelector("dialog[open]")) return;
    if (ev.code === "Space") { ev.preventDefault(); setRun(!G.running); }
    if (ev.code === "ArrowRight") stepOnce();
  });
}

wire();
stageLoop();
boot();
