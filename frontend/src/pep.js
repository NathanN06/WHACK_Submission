// The Peptide & GLP-1 edition game screen: title, playback, battle stage, console, Test Inspector and ledger.
// One hero (the Alchemist) carries one to six hypothesis scrolls; the Gatekeeper Skeptic speaks at each gate.
// Every number drawn comes from a ledger row (pep-state.js folds them); nothing here computes a statistic.

const $ = (id) => document.getElementById(id);
const ROMAN = { 1: "I", 2: "II", 3: "III", 4: "IV" };
const PACE = 1.45;   // every beat is held this much longer at 1x, so each ruling can be read and seen
const FALLBACK_CAMPAIGNS = ["A", "B", "C", "D"];

const G = {
  campaigns: [], pick: "A", server: false, claude: false,
  counts: {},   // campaign letter -> how many hypotheses the Scribe forms (2 to 6)
  champions: null,   // Challenger Mode: each campaign's title track and its reigning champion (GET /api/champions)
  mode: null, questId: null, poll: null, token: 0,
  state: initial(), pending: [], done: false,
  running: true, speed: 1, nextAt: 0, hold: false,
  reduced: window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  f: 0, fx: [], shake: 0, lunge: null, pinned: null, bubbleUntil: 0,
  filters: { agent: "", level: "", kind: "", text: "" },
  typer: null,
  seen: new Set(), interactive: false,   // ledger rows already applied; whether the Director's console is live
  // motion only (never a ledger number): where each sprite is drawn, what each bar shows while it glides
  pos: {}, hpShow: {}, hpTrail: {}, hitAt: {}, parts: [], wipe: null, shownLevel: 0,
  enemyKey: null, enemyT0: 0, lastNow: 0, shakeT0: 0, shakeDur: 0, shakeAmp: 0, flashT0: 0, cheer: {}, recoilT0: 0,
  cards: {},   // the party's DOM cards, kept between renders so bars and numbers can animate
};

function shakeStage(ms, amp) {
  if (G.reduced) return;
  G.shakeT0 = performance.now(); G.shakeDur = ms; G.shakeAmp = amp;
}

// ---------- title ----------

async function boot() {
  $("motion").setAttribute("aria-pressed", String(G.reduced));
  document.body.classList.toggle("reduced", G.reduced);
  watchScreens();
  revealScreen(700);
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
  $("count-wrap").hidden = !G.server;
  $("challenger-wrap").hidden = !G.server;
  $("count").onchange = () => { G.counts[G.pick] = $("count").value; };
  $("challenger").onchange = syncChampion;
  syncCount();
  refreshChampions();
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
    b.onclick = () => {
      G.pick = b.dataset.letter;
      for (const o of document.querySelectorAll(".card")) o.setAttribute("aria-checked", String(o === b));
      syncCount(); syncChampion();
    };
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

function syncCount() {   // the hypothesis picker shows the number chosen for the selected campaign
  // the Scribe always forms the scrolls (2 to 6, default 3); the hand-written set is no longer offered
  if (!(G.pick in G.counts)) G.counts[G.pick] = "3";
  if ($("count")) $("count").value = G.counts[G.pick];
}

// Challenger Mode: the selected campaign's title track, its reigning champion and its record (all from the registry)
async function refreshChampions() {
  if (!G.server) return;
  try { G.champions = await fetch("/api/champions").then((r) => (r.ok ? r.json() : null)); } catch { G.champions = null; }
  syncChampion();
}

function syncChampion() {
  const el = $("champ-line"), c = G.campaigns.find((x) => x.letter === G.pick);
  const track = c && c.track && G.champions && G.champions.tracks ? G.champions.tracks[c.track] : null;
  if (!G.server || !c || !c.track) { el.hidden = true; return; }
  const on = $("challenger").checked, ch = track && track.champion;
  const record = ch ? `won round ${ch.won_round}${ch.defended ? `, defended ${ch.defended}×` : ""}${ch.not_defended ? `, not defended ${ch.not_defended}×` : ""}` : "";
  el.hidden = false;
  el.classList.toggle("on", on);
  el.innerHTML = `<b>Title track ${esc(c.track)}</b> · ${ch
    ? `Champion <strong>${esc(ch.hid)}</strong> “${esc(ch.spec.title)}” (${esc(record)})`
    : track && track.rounds ? `the title is vacant after ${track.rounds} round${track.rounds === 1 ? "" : "s"}` : "no round played yet: the title is vacant"}
    ${on ? `<br><small>Next: round ${(track && track.rounds || 0) + 1}, on a fresh cohort (seed ${(track && track.rounds || 0) + 1}). ${ch
      ? "The champion's words are frozen; every challenger differs from it in outcome or archetype." : "Every challenger competes for the vacant title."}</small>` : ""}`;
}

// ---------- starting, polling, exiting ----------

async function startGame(mode) {
  G.token += 1;
  const token = G.token;
  Object.assign(G, { mode, state: initial(), pending: [], done: false, running: true, hold: false, pinned: null,
                     fx: [], questId: null, nextAt: 0, seen: new Set(), interactive: false,
                     pos: {}, hpShow: {}, hpTrail: {}, hitAt: {}, parts: [], wipe: null, shownLevel: 0, enemyKey: null, cheer: {} });
  $("party").innerHTML = ""; G.cards = {}; G.nodesHTML = "";
  $("screen-title").hidden = true; $("screen-room").hidden = true; $("screen-bridge").hidden = true; $("screen-game").hidden = false;
  $("ledger").tBodies[0].innerHTML = ""; $("f-agent").innerHTML = '<option value="">Everyone</option>';
  $("insp-id").textContent = ""; $("insp-body").innerHTML = '<p class="muted">When the Judge runs a test, it appears here.</p>';
  G.bubbleUntil = 0; $("gate-bubble").hidden = true;
  setRun(true); renderAll();
  ticker("Opening the campaign…", "");
  if (mode === "live" && G.server) {
    try {
      const res = await fetch("/api/quests", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign: G.pick, llm: G.claude && $("llm").checked, interactive: true,
                               challenger: $("challenger").checked,
                               ...(G.counts[G.pick] ? { scrolls: Number(G.counts[G.pick]) } : {}) }) });
      if (res.status === 429) {   // the server is full: say so plainly, then play the recording
        const j = await res.json().catch(() => ({}));
        throw new Error(`The server is busy: ${j.detail || "too many expeditions are running"}`);
      }
      if (!res.ok) throw new Error(await res.text());
      G.questId = (await res.json()).quest_id;
      G.interactive = true;
      pollLive(token, 0);
    } catch (err) {
      ticker("Could not start a live campaign, so the recorded run plays instead.", String(err.message || err).slice(0, 200));
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
  refreshChampions();
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
  if (e.action === "level_start") {
    if (G.shownLevel && e.level !== G.shownLevel && !G.reduced) {
      G.wipe = { t0: performance.now(), from: G.shownLevel, to: e.level, dur: 900 / Math.sqrt(G.speed) };
    } else G.shownLevel = e.level;
    banner(`Level ${ROMAN[e.level]}: ${e.result.name}`, e.result.trap);
  }
  if (e.action === "encounter" && e.result.boss) { banner(e.result.enemy.name, "BOSS"); shakeStage(420, 2); }
  if (e.action === "challenger_roster") {
    banner(`Challenger round ${e.result.round}`, e.result.incumbent ? `${e.result.incumbent.hid} defends the title` : "The title is vacant");
  }
  if (e.action === "champion_update") banner(e.result.result, e.result.winner_name || "");
  if (e.action === "result" || e.action === "mystery_result") {
    if (!G.pinned) inspect(e);
    const d = e.hp_delta || 0, id = e.agent_id;
    // the scroll only becomes the fighter on this row, so it is still flying out: the result lands when it arrives
    const p0 = G.pos[id], far = p0 && Math.hypot(p0.x - FRONT[0], p0.y - FRONT[1]) > 4;
    const lag = G.reduced || !far || e.action !== "result" ? 0 : 760 / Math.sqrt(G.speed);
    const t0 = performance.now() + lag;
    if (d) G.fx.push({ id, text: d > 0 ? `+${d}` : `${d}`, color: d > 0 ? "#5fd67a" : "#ff4a5a", t0 });
    else if (e.passed) G.fx.push({ id, text: "0", color: "#7fe0ff", t0 });
    G.lunge = { id, t0, hit: d < 0 };
    if (d < 0) G.hitAt[id] = t0;
    if (e.passed && d >= 0 && !(e.result && e.result.scout)) { G.cheer[id] = t0; G.recoilT0 = t0; }
    setTimeout(() => {
      if (d < 0) shakeStage(260, Math.min(3, 1 + -d / 12));
      const at = G.pos[id];
      if (!at || G.reduced) return;
      if (d < 0) burst(G.parts, at.x, at.y - 14, Math.min(26, 8 - d), ["#ff4a5a", "#ffd1d8", "#f3e9d2"], { speed: 70, life: 0.5 });
      else if (d > 0) burst(G.parts, at.x, at.y - 8, 14, ["#5fd67a", "#b6ffc4"], { speed: 22, up: 40, gravity: -30, life: 0.9 });
      else if (e.passed) burst(G.parts, at.x, at.y - 14, 8, ["#7fe0ff", "#ffffff"], { speed: 40, life: 0.4 });
    }, lag);
  }
  if (e.action === "shatter") {
    banner(`${s.agents[e.agent_id]?.name || "A scroll"} shatters`, "0 HP: research integrity gone");
    shakeStage(480, 4);
    const at = G.pos[e.agent_id];
    if (at && !G.reduced) {
      G.flashT0 = performance.now();
      burst(G.parts, at.x, at.y - 12, 40, ["#9a96a8", "#6a6880", "#3a3848", "#f3e9d2"], { speed: 55, up: 30, gravity: 90, life: 1.2 });
    }
  }
  if (e.action === "gatekeeper" || e.action === "benchmark") speak(e.result.text, e.action === "benchmark");
  if (e.action === "level_complete") {
    showLevelDone(e.result);
    if (G.interactive) directorPost("advance", { level: e.result.level }).catch(() => {});  // the quest may compute the next level
  }
  if (typeof directorEvent === "function") directorEvent(e);
  if (typeof bridgeEvent === "function") bridgeEvent(e);
  if (e.action === "finale" && $("screen-bridge").hidden) finaleReached();
  if (e.action === "stopped" || e.action === "error" || e.action === "timeout") ticker(e.line, "");
  renderAll();
}

function step(now) {
  if (G.hold || !G.running || !G.pending.length) return;
  if (now < G.nextAt) return;
  const e = G.pending.shift();
  apply(e);
  G.nextAt = now + beat(e) * PACE / G.speed * (G.reduced ? 0.8 : 1);
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

// where each scroll floats above the Alchemist (feet, 2x): a front row of three, then a back row for up to six
const HOME = [[36, 100], [70, 84], [104, 100], [19, 72], [53, 58], [121, 72]];
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
  const dt = Math.min(0.05, G.lastNow ? (now - G.lastNow) / 1000 : 0.016);
  G.lastNow = now;
  // a dungeon change plays the dissolve: close on the old level, open on the new one
  let level = Math.min(4, Math.max(1, s.level || 1)), wipeP = 0;
  if (G.wipe) {
    const t = (now - G.wipe.t0) / G.wipe.dur;
    if (t >= 1) { G.shownLevel = G.wipe.to; G.wipe = null; }
    else { level = t < 0.5 ? G.wipe.from : G.wipe.to; wipeP = t < 0.5 ? ease.inOut(t * 2) : 1 - ease.inOut((t - 0.5) * 2); }
  }
  const f = G.reduced ? 0 : G.f;
  ctx.save();
  ctx.clearRect(0, 0, 320, 180);
  const sk = now - G.shakeT0;
  if (sk < G.shakeDur) {
    const k = G.shakeAmp * (1 - sk / G.shakeDur);
    ctx.translate(Math.round(Math.sin(sk / 22) * k), Math.round(Math.cos(sk / 31) * k * 0.5));
  }
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
    if (s.enemy.key !== G.enemyKey) { G.enemyKey = s.enemy.key; G.enemyT0 = now; }
    const enter = G.reduced ? 1 : ease.out(clamp01((now - G.enemyT0) / 480));   // each foe slides in out of the dark
    aura(ctx, 252, 132, 70, "255,230,180", 0.34 * enter);  // a pool of light so dark foes read
    const L = G.lunge && now >= G.lunge.t0 && now - G.lunge.t0 < 500 ? G.lunge : null;
    const rc = now - G.recoilT0, recoil = rc >= 0 && rc < 520 && !G.reduced ? Math.sin(rc / 520 * Math.PI) * 16 : 0;   // knocked back by a pass
    const ex = 252 + (1 - enter) * 80 + recoil - (L && L.hit && !G.reduced ? Math.sin((now - L.t0) / 500 * Math.PI) * 30 : 0);
    ctx.save(); ctx.globalAlpha = enter * (rc >= 0 && rc < 300 && !G.reduced && Math.floor(rc / 60) % 2 ? 0.55 : 1);
    if (BOSSES[s.enemy.key]) drawBossOutlined(ctx, s.enemy.key, Math.round(ex), 162, f, 2);
    else { ctx.translate(Math.round(ex), 162); ctx.scale(3, 3); drawEnemy(ctx, s.enemy.key, 0, 0, f, false); }
    ctx.restore();
  } else G.enemyKey = null;
  // the Alchemist
  const hero = pepSprite("Alchemist");
  const hb = G.reduced ? 0 : Math.round(Math.sin(G.f / 16) * 0.6);
  ctx.save(); ctx.translate(HERO[0], HERO[1] + hb); ctx.scale(3, 3); blit(ctx, hero, 0, 0); ctx.restore();
  // a thread of light from the flask to the scroll under test
  const fid = s.fighter && s.enemy && s.agents[s.fighter] && s.agents[s.fighter].status === "active" ? s.fighter : null;
  const fp = fid && G.pos[fid];
  if (fp) for (let k = 1; k < 12; k++) {
    if ((k + Math.floor(f / 4)) % 3) continue;
    const t = k / 12, x = HERO[0] + 16 + (fp.x - HERO[0] - 16) * t, y = HERO[1] - 22 + (fp.y - 12 - HERO[1] + 22) * t;
    rect(ctx, x, y, 1, 1, "#7fe0ff");
  }
  // the scrolls
  s.order.forEach((id, i) => {
    const a = s.agents[id];
    const [tx, ty] = scrollAt(s, id);
    // scrolls travel on an arc: a short lift out to the front, a higher hop back home
    const p = G.pos[id] || (G.pos[id] = { x: tx, y: ty, fx: tx, fy: ty, tx, ty, t0: 0, dur: 0, arc: 0 });
    if (p.tx !== tx || p.ty !== ty) {
      Object.assign(p, { fx: p.x, fy: p.y, tx, ty, t0: now, dur: G.reduced ? 0 : 760 / Math.sqrt(G.speed), arc: tx < p.x ? 20 : 10 });
    }
    const k = p.dur ? clamp01((now - p.t0) / p.dur) : 1, e2 = ease.inOut(k);
    p.x = p.fx + (p.tx - p.fx) * e2; p.y = p.fy + (p.ty - p.fy) * e2 - Math.sin(Math.PI * k) * p.arc;
    const ch = G.reduced ? 1e9 : now - (G.cheer[id] || -1e9);          // the victory hop after a pass
    const hk = G.reduced ? 1e9 : now - (G.hitAt[id] || -1e9);          // knocked back by a hit
    const x = Math.round(p.x - (hk >= 0 && hk < 320 ? Math.sin(hk / 320 * Math.PI) * 9 : 0));
    const fy0 = Math.round(p.y - (ch >= 0 && ch < 820 ? Math.abs(Math.sin(ch / 820 * 2 * Math.PI)) * 8 : 0));
    if (a.status !== "active") {
      ctx.save(); ctx.translate(x, fy0 + 4); ctx.scale(2, 2); drawAsh(ctx, 0, 0); ctx.restore();
      return;
    }
    const fy = fy0 + (G.reduced ? 0 : Math.round(Math.sin(G.f / 12 + i * 2) * 1.5));
    const img = scrollSprite(a.archetype);
    const fighting = id === fid;
    if (fighting) aura(ctx, x, fy - 12, 26, "255,224,138", 0.5 + (G.reduced ? 0 : 0.15 * Math.sin(G.f / 6)));
    else if (s.active === id) aura(ctx, x, fy - 12, 18, "255,224,138", 0.28);
    const L = G.lunge && G.lunge.id === id && now >= G.lunge.t0 && now - G.lunge.t0 < 400 ? G.lunge : null;
    const flash = L && L.hit && !G.reduced && (now - L.t0) % 120 < 60;
    ctx.save(); ctx.translate(x, fy); ctx.scale(2, 2);
    blit(ctx, flash ? flashOf(`scroll:${a.archetype}`, img) : img, 0, 0);
    ctx.restore();
    // floating HP bar (it drains, with a pale trail of the HP just lost), credit pips and buff dots
    const hp = Math.max(0, a.hp);
    const goal = now < (G.hitAt[id] || 0) ? G.hpShow[id] : hp;   // the bar holds until the blow lands
    const show = G.hpShow[id] = G.reduced || G.hpShow[id] == null ? hp : approach(G.hpShow[id], goal, dt, 7);
    let trail = G.hpTrail[id] ?? hp;
    if (trail < show || G.reduced) trail = show;
    else if (now - (G.hitAt[id] || 0) > 420) trail = Math.max(show, trail - dt * 45);
    G.hpTrail[id] = trail;
    const top = fy - img.height * 2 - 6;
    rect(ctx, x - 13, top, 26, 4, "#0d0b1e");
    const w = Math.round(24 * show / 100), wt = Math.round(24 * trail / 100);
    if (wt > w) rect(ctx, x - 12 + w, top + 1, wt - w, 2, "#ffd1d8");
    rect(ctx, x - 12, top + 1, w, 2, show > 50 ? "#5fd67a" : show > 25 ? "#e8b847" : "#ff4a5a");
    pixelText(ctx, String(Math.round(show)), x, top - 7, "#f3e9d2");
    if (ch >= 0 && ch < 1100) {   // a gold ring opens around the scroll and a check mark rises over it
      const t = ch / 1100, r = 6 + ease.out(t) * 22;
      ctx.globalAlpha = 1 - t;
      for (let q = 0; q < 14; q++) {
        const a = q / 14 * Math.PI * 2 + t;
        rect(ctx, x + Math.cos(a) * r, fy - 12 + Math.sin(a) * r * 0.7, q % 2 ? 1 : 2, q % 2 ? 1 : 2, q % 3 ? "#ffe08a" : "#ffffff");
      }
      const cy = top - 20 - Math.round(ease.out(t) * 8), pts = [[-3, 0], [-2, 1], [-1, 2], [0, 1], [1, 0], [2, -1], [3, -2]];
      for (const [dx, dy] of pts) rect(ctx, x + dx * 2 - 1, cy + dy * 2 - 1, 4, 4, "#0d0b1e");   // outline
      for (const [dx, dy] of pts) rect(ctx, x + dx * 2, cy + dy * 2, 2, 2, "#5fd67a");
      ctx.globalAlpha = 1;
    }
    const c = Math.round(a.credits / 20);
    for (let k = 0; k < c; k++) rect(ctx, x - 12 + k * 4, top + 5, 3, 2, "#e8b847");
    a.buffs.slice(0, 6).forEach((_, k) => rect(ctx, x + 11, top + 9 + k * 4, 3, 3, "#7fe0ff"));
  });
  // floating damage numbers
  // floating damage numbers: they pop at double size, settle, rise and fade
  G.fx = G.fx.filter((p) => now - p.t0 < 1100);
  for (const p of G.fx) {
    if (!s.agents[p.id] || now < p.t0) continue;
    const at = G.pos[p.id] || { x: scrollAt(s, p.id)[0], y: scrollAt(s, p.id)[1] };
    const t = (now - p.t0) / 1100;
    const rise = G.reduced ? 0 : ease.out(t) * 16;
    const big = !G.reduced && t < 0.14;
    ctx.save();
    ctx.globalAlpha = t > 0.65 ? 1 - (t - 0.65) / 0.35 : 1;
    const nx = Math.round(at.x + 18), ny = Math.round(at.y - 34 - rise);
    if (big) { ctx.translate(nx, ny); ctx.scale(2, 2); pixelText(ctx, p.text, 0, -2, p.color); }
    else pixelText(ctx, p.text, nx, ny, p.color);
    ctx.restore();
  }
  stepParticles(ctx, G.parts, dt);
  if (now - G.flashT0 < 90) { ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.fillRect(-4, -4, 328, 188); }
  ctx.restore();
  drawDissolve(ctx, 320, 180, wipeP, 10, "#0d0b1e");
}

// The Gatekeeper's speech bubble over the stage.
function speak(text, benchmark) {
  const b = $("gate-bubble");
  b.innerHTML = `<small>${benchmark ? "The Gatekeeper sets the benchmark" : "Warden of the Null, the Gatekeeper Skeptic"}</small>${esc(text)}`;
  b.hidden = false;
  G.bubbleUntil = performance.now() + 4400 / G.speed;
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.hidden = true; renderEnemy(); }, 4400 / G.speed);
}

// ---------- HTML around the stage ----------

function renderAll() {
  renderNodes(); renderParty(); renderEnemy(); renderHud();
  $("ledger-count").textContent = `${G.state.events.length} rows`;
  renderProgress();
}

// Where playback is: a recording shows "row X / Y"; a live expedition shows how many rows wait to be shown.
function renderProgress() {
  const shown = G.state.events.length, total = shown + G.pending.length;
  const text = G.mode === "demo" ? (total ? `Replaying row ${shown} / ${total}` : "")
    : G.done ? `Row ${shown} / ${total}` : `Live · row ${shown}${G.pending.length ? ` · ${G.pending.length} queued` : ""}`;
  if ($("progress").textContent !== text) $("progress").textContent = text;
}

function renderNodes() {
  const html = nodeStates(G.state).map((n) =>
    `<li class="${n.done ? "done" : ""} ${n.current ? "current" : ""}" title="${esc(n.name)}"><b>${n.numeral}</b><span>${esc(n.name)}</span></li>`)
    .join('<li class="arrow" aria-hidden="true">→</li>');
  if (html === G.nodesHTML) return;   // only redraw on a real change, so the new current node animates once
  G.nodesHTML = html;
  $("nodes").innerHTML = html;
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
  const s = G.state, list = $("party");
  const standing = s.order.filter((id) => s.agents[id].status === "active").length;
  if (s.hero) {
    let li = G.cards.hero;
    if (!li) {
      li = G.cards.hero = document.createElement("li");
      li.className = "pcard hero-card";
      list.prepend(li);
    }
    const html = `<img src="${portrait("hero")}" alt="" width="48" height="48">
      <div class="pinfo"><strong>${esc(s.hero.short || s.hero.name)}</strong> <small>the hero</small>
        <div class="meta"><span>${standing} of ${s.order.length} scrolls intact</span></div>
        <div class="buffs"><span>chooses abilities, never numbers</span></div></div>`;
    if (li._html !== html) { li.innerHTML = html; li._html = html; }
  }
  // each scroll keeps its card, so its HP bar drains, its number counts down and a hit shakes it
  for (const id of s.order) {
    const a = s.agents[id];
    let li = G.cards[id];
    if (!li) {
      li = G.cards[id] = document.createElement("li");
      li.innerHTML = `<img src="${portrait(a.archetype)}" alt="" width="48" height="48">
        <div class="pinfo"><strong></strong> <small></small>
          <p class="claim"></p>
          <div class="hp"><b class="trail"></b><i></i><span data-v="${a.hp}">${a.hp} HP</span></div>
          <div class="meta"></div><div class="buffs"></div></div>`;
      li._buffs = [];
      li.tabIndex = 0; li.setAttribute("role", "button");
      li.onclick = () => openScroll(id);
      li.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openScroll(id); } };
      list.appendChild(li);
    }
    const st = a.status !== "active" ? "fallen" : (s.fighter === id && s.enemy ? "fighting" : "");
    li.className = `pcard ${st} a-${a.archetype}`;
    li.title = a.claim;
    li.querySelector("strong").textContent = a.name.replace(/^The /, "");
    li.querySelector("small").textContent = a.title;
    li.querySelector(".claim").textContent = a.claim;   // the hypothesis itself, not just the scroll's name
    const hp = Math.max(0, a.hp), span = li.querySelector(".hp span"), prev = Number(span.dataset.v);
    li.querySelector(".hp i").style.width = `${hp}%`;
    li.querySelector(".hp .trail").style.width = `${hp}%`;
    if (hp < prev) pulse(li, "hurt"); else if (hp > prev) pulse(li, "healed");
    tweenNumber(span, a.hp, G.reduced ? 0 : 500, " HP");
    const cast = a.abilities[s.level] || [];
    const meta = `<span title="Research credits left">◆ ${a.credits}</span>
      ${a.champion ? `<span class="champ-badge" title="The reigning champion of this title track: its words are frozen (hash ${esc((a.champion.claim_hash || "").slice(0, 12))}…)">♛ ${esc(a.champion.hid)}</span>` : ""}
      ${a.verdict ? `<span class="verdict v-${a.verdict.replace(/\s/g, "")}">${esc(a.verdict)}</span>` : ""}
      ${cast.map((k) => `<span class="cast">${esc(abilityName(k))}</span>`).join("")}`;
    const m = li.querySelector(".meta");
    if (m._html !== meta) { m.innerHTML = meta; m._html = meta; }
    if (a.buffs.join("|") !== li._buffs.join("|")) {
      const fresh = new Set(a.buffs.filter((b) => !li._buffs.includes(b)));
      li.querySelector(".buffs").innerHTML = a.buffs.map((b) => `<span class="${fresh.has(b) ? "fresh" : ""}">${esc(b)}</span>`).join("");
      li._buffs = [...a.buffs];
    }
  }
}

// Click a scroll card: the full hypothesis, where it came from, its evidence and how it is faring.
function openScroll(id) {
  const s = G.state, a = s.agents[id], dlg = $("scroll-dlg");
  if (!a) return;
  const ev = a.realEvidence;
  const evidence = ev
    ? `<p><b>Real evidence</b> (topic: ${esc(ev.topic)}): ${ev.papers} papers from Europe PMC
         (${ev.species.human} human, ${ev.species.rodent} animal, ${ev.species["in vitro"]} in vitro) and
         ${ev.completed_rcts} completed randomized trial${ev.completed_rcts === 1 ? "" : "s"} on ClinicalTrials.gov.</p>
       ${ev.examples.length ? `<ul class="papers">${ev.examples.map((p) =>
         `<li><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a> ${p.year ? `(${p.year})` : ""}</li>`).join("")}</ul>` : ""}
       <p class="muted">Social posts and the patient cohort the Judge tests this claim on are simulated.</p>`
    : `<p class="muted">Simulated evidence: this scroll's papers, posts and patients come from the campaign's simulated world.</p>`;
  const lines = Object.keys(a.lines).sort().map((lv) =>
    `<li><b>Level ${ROMAN[lv] || lv}:</b> “${esc(a.lines[lv])}”${(a.abilities[lv] || []).length
      ? ` · cast ${a.abilities[lv].map((k) => esc(abilityName(k))).join(", ")}` : ""}</li>`).join("");
  dlg.innerHTML = `<p class="sub">${esc(a.title)} · ${esc(a.nickname || "")}</p>
    <h3>${esc(a.name)}</h3>
    <blockquote class="hyp">${esc(a.claim)}</blockquote>
    <table class="nums">
      <tr><th>Outcome tested</th><td>${esc(a.outcome || "")}${a.track ? ` <span class="muted">(track ${esc(a.track)})</span>` : ""}</td></tr>
      <tr><th>Where it came from</th><td>${esc(a.origin || "")}</td></tr>
      ${a.champion ? `<tr><th>Champion</th><td>${esc(a.champion.hid)}: won round ${a.champion.won_round}${a.champion.defended ? `, defended ${a.champion.defended}×` : ""}.
        Its words are frozen (SHA-256 ${esc((a.champion.claim_hash || "").slice(0, 16))}…); every number is measured again on this round's patients.</td></tr>` : ""}
      <tr><th>Status</th><td>${a.hp} HP · ◆ ${a.credits}${a.verdict ? ` · <span class="verdict v-${a.verdict.replace(/\s/g, "")}">${esc(a.verdict)}</span>` : ""}</td></tr>
    </table>
    ${evidence}
    ${lines ? `<h3>The Alchemist's choices</h3><ul class="lines">${lines}</ul>` : ""}
    <div class="dlg-buttons"><button class="btn gold" id="scroll-close">Close</button></div>`;
  $("scroll-close").onclick = () => dlg.close();
  dlg.showModal();
}

// Top-left HUD: the scroll the Alchemist is holding up right now.
function renderHud() {
  const s = G.state, a = s.agents[s.fighter && s.enemy ? s.fighter : s.active];
  const hud = $("hud");
  if (!a) { hud.hidden = true; return; }
  hud.hidden = false;
  const swap = hud._id !== a.id;
  if (swap) {   // a new scroll steps up: rebuild and slide it in, without animating the bar from the last one
    hud._id = a.id;
    hud.innerHTML = `<img alt="" width="30" height="30"><div><strong></strong>
      <div class="hp"><b class="trail"></b><i></i><span data-v="${a.hp}"></span></div><small></small></div>`;
    pulse(hud, "enter");
  }
  hud.className = `hud a-${a.archetype} ${a.status !== "active" ? "fallen" : ""} ${hud.classList.contains("enter") ? "enter" : ""}`;
  hud.querySelector("img").src = portrait(a.archetype);
  hud.querySelector("strong").textContent = a.name;
  for (const bar of hud.querySelectorAll(".hp i, .hp .trail")) bar.style.width = `${Math.max(0, a.hp)}%`;
  tweenNumber(hud.querySelector(".hp span"), a.hp, swap || G.reduced ? 0 : 500, " HP");
  hud.querySelector("small").textContent = `◆ ${a.credits} · ${a.design === "new_user" || a.buffs.includes("TIME-ZERO ALIGNED") ? "time-zero aligned" : "as carried"}`;
}

function abilityName(k) { return (G.state.rules && G.state.rules.abilities[k] && G.state.rules.abilities[k].name) || k; }

function renderEnemy() {
  const e = G.state.enemy, plate = $("enemy-plate");
  if (!e || !e.key || performance.now() < G.bubbleUntil) { plate.hidden = true; return; }
  const html = `<strong>${esc(e.name)}</strong>${e.boss ? ' <em>BOSS</em>' : ""}<small>${esc(e.test || "")}</small>`;
  const fresh = plate.hidden || plate._html !== html;
  plate.hidden = false;
  if (fresh) { plate.innerHTML = html; plate._html = html; pulse(plate, "enter"); }
}

function banner(title, sub) {
  const b = $("banner");
  b.innerHTML = `<strong>${esc(title)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}`;
  b.hidden = false;
  b.classList.remove("out");
  pulse(b, "in");
  clearTimeout(b._t); clearTimeout(b._t2);
  b._t = setTimeout(() => { b.classList.add("out"); b._t2 = setTimeout(() => { b.hidden = true; b.classList.remove("out"); }, 240); },
                    2600 / G.speed);
}

function ticker(line, explain) {
  clearInterval(G.typer);
  const el = $("tick-line");
  $("tick-explain").textContent = explain || "";
  if (G.reduced || G.speed >= 4) { el.textContent = line; return; }
  let i = 0;
  el.textContent = "";
  G.typer = setInterval(() => {
    i += 1.3 * G.speed;
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
    if (r.science) html += scienceHTML(r.science);
    if (r.chart) html += chartHTML(r.chart);
    const nums = Object.entries(r.numbers || {});
    if (nums.length) html += `<table class="nums">${nums.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${fmt(v)}</td></tr>`).join("")}</table>`;
    html += traceHTML(tele);
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
    if (e.encounter) html += traceHTML(e.encounter) + `<details><summary>Telemetry record</summary><pre>${esc(JSON.stringify(e.encounter, null, 2))}</pre></details>`;
    if (e.action === "sources_registered") html += sourcesHTML(r.sources || []);
    if (e.action === "source_registered" && r.source) html += sourcesHTML([r.source]);
    if (e.action === "decision") {
      const picks = (e.result && e.result.abilities) || [];
      html += `<p>Cast: ${picks.length ? picks.map((k) => `<span class="cast">${esc(abilityName(k))}</span>`).join(" ") : "nothing"}
        ${e.cost ? ` for ${e.cost} credits` : ""}. Chosen by ${esc((e.result && e.result.source) === "claude" ? "Claude, as the Alchemist" : "the scroll's scripted plan")}.</p>`;
    }
  }
  $("insp-body").innerHTML = html;
  pulse($("insp-body"), "swap");
  const un = $("unpin");
  if (un) un.onclick = () => { G.pinned = null; const last = [...s.events].reverse().find((x) => x.action === "result"); if (last) inspect(last); };
}

// The scientific status of the question at the Guardian: the drug's risk ratio on unseen matched patients.
function scienceHTML(sc) {
  return `<div class="science s-${esc(sc.status.replace(/\s/g, ""))}"><small>Scientific status of the question</small>
    <strong>${esc(sc.status)}</strong>${sc.below_sesoi ? ' <span class="tag">smaller than the smallest effect of interest</span>' : ""}
    <p>${esc(sc.why || "")}</p>
    <p class="muted small">Smallest effect of interest: risk ratio ${fmt(sc.sesoi_rr)}${sc.mde_rr ? ` · detectable with 80% power: ${fmt(sc.mde_rr)}` : ""}${sc.method ? ` · ${esc(sc.method)} interval` : ""}.
      Prediction (the verdict) and causation (this status) are judged separately.</p></div>`;
}

// The Archivist's Ledger: which method measured this encounter, and which registered sources it read.
function traceHTML(tele) {
  if (!tele || !tele.methodId) return "";
  const s = G.state, desc = (s.methods || {})[tele.methodId] || "";
  const srcs = (tele.sourceIds || []).map((id) => {
    const x = s.sources.find((y) => y.id === id);
    return `<li><code>${esc(id)}</code> ${x ? `<span class="stype t-${esc(x.type)}">${esc(x.type.replace(/_/g, " "))}</span> ${esc(x.label)}` : ""}</li>`;
  }).join("");
  return `<dl class="insp trace"><dt>Method</dt><dd><code>${esc(tele.methodId)}</code> ${esc(desc)}</dd>
    <dt>Sources</dt><dd>${srcs ? `<ul class="srcs">${srcs}</ul>` : "none (not measured)"}</dd>
    ${tele.rulesetVersion ? `<dt>Ruleset</dt><dd><code>${esc(tele.rulesetVersion)}</code></dd>` : ""}</dl>`;
}

function sourcesHTML(list) {
  return `<ul class="srcs">${list.map((x) => `<li><code>${esc(x.id)}</code> <span class="stype t-${esc(x.type)}">${esc(x.type.replace(/_/g, " "))}</span>
    ${esc(x.label)} <span class="muted small">(${esc((x.usage || "").replace(/_/g, " ").toLowerCase())})</span></li>`).join("")}</ul>`;
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
  const body = $("ledger").tBodies[0];
  body.insertAdjacentHTML("afterbegin", rowHTML(e));
  if (!G.reduced) pulse(body.firstElementChild, "new");
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
  let n = Math.ceil(8 / G.speed);
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
  ["The battle stage", "One hero, the Alchemist-Epidemiologist, carries two to six hypothesis scrolls into four dungeons. Each scroll has its own research integrity (HP, the bar above it), credits (gold pips) and buffs (blue dots). A scroll at 0 HP shatters into ash; the hero walks on."],
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
    <p>One hero, the Alchemist-Epidemiologist, carries 2 to 6 hypothesis scrolls formed by the Scribe, no two with the
    same outcome and archetype, each with real papers and trial counts copied from Europe PMC and ClinicalTrials.gov.
    With an API key, Claude writes their words; without one, the campaign's own scrolls come first: a Hype Scroll
    found on social media, a Mechanistic Scroll framed by a clinician, and a Preprint Scroll from a small study.
    Each scroll starts with 100 HP (research integrity) and 100 credits, and the hero buys abilities for it each level. The hero never produces a number:
    the deterministic Statistical Judge measures everything and applies fixed rules,
    <code>ΔHP = −round(clamp(D_raw × M, 0, D_max))</code>. A scroll at 0 HP shatters.</p>
    <p>Levels I to III see only the training years, and every patient's follow-up is cut at the training cutoff, so
    no test reads an outcome from the future. The final boss, the Guardian of False Discoveries, matches unseen
    holdout patients on the propensity score and compares each scroll's predictions with the Gatekeeper's benchmark:
    the active comparator with no drug effect. A scroll is <strong>validated</strong> only if it lowers the
    prediction loss (SS<sub>oos</sub> &gt; 0.002) and a paired loss test says the gain is unlikely to be luck
    (p &lt; 0.05). If none is, the verdict is <strong>Baseline Holds</strong>.</p>
    <p>Prediction and causation are judged separately. The Guardian also measures the drug's risk ratio on the same
    matched patients, with a 95% interval (exact for rare events), and gives the question a <strong>scientific
    status</strong>: SUPPORTED (the interval excludes no effect), REFUTED (it excludes the smallest effect of
    interest), or INCONCLUSIVE (it includes both), with the smallest effect these patients could detect. A champion
    is crowned for each outcome track, never across different questions.</p>
    <p>In the console, the seven boss chips each summon one registered test. The same test on an unchanged scroll is
    not run again, and a kind of test that already rewarded a scroll earns it nothing more. The
    <strong>Archivist's Ledger</strong> in the brief names the method and the sources behind every encounter, and its
    manifest can be downloaded. A <strong>Challenger round</strong> replays a campaign's title on a fresh cohort:
    the champion's words are frozen and it must win again against challengers that differ from it.</p>
    ${levels ? `<h3>Levels</h3><table><thead><tr><th></th><th>Level</th><th>Trap</th><th>Damage rule</th><th>D<sub>max</sub></th></tr></thead><tbody>${levels}</tbody></table>` : ""}
    ${abil ? `<h3>Abilities</h3><table><thead><tr><th>Ability</th><th>Level</th><th>Cost</th><th>Effect</th></tr></thead><tbody>${abil}</tbody></table>` : ""}
    <h3>Composite score</h3><p>0.35 × out-of-sample skill + 0.25 × HP + 0.25 × traps falsified + 0.15 × efficiency (lift per credit).</p>
    ${rules && rules.ruleset_version ? `<p class="muted small">Ruleset ${esc(rules.ruleset_version)}.</p>` : ""}
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
  $("motion").onclick = () => {
    G.reduced = !G.reduced;
    $("motion").setAttribute("aria-pressed", String(G.reduced));
    document.body.classList.toggle("reduced", G.reduced);
  };
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
