// The game state is a fold over the ledger: every number on screen comes from a ledger row.
// Pure enough to test in node:  const { initial, reduce, replay } = require("./pep-state.js").
//
// One hero, the Alchemist, carries three hypothesis scrolls (s.agents, in s.order). Each scroll has its
// own HP and credits and shatters at 0 HP. The Gatekeeper Skeptic is not a scroll: it speaks (s.gate)
// and holds the baseline the Guardian judges against.

const NODES = [
  { level: 1, numeral: "I" }, { level: 2, numeral: "II" }, { level: 3, numeral: "III" }, { level: 4, numeral: "IV" },
  { level: 5, numeral: "✦", name: "Bridge of Judgment" },
];

function initial() {
  return {
    campaign: null, rules: null, archetypes: null, hero: null, gatekeeper: null, simulated: true,
    level: 0, levelInfo: {}, levelDone: {},
    agents: {}, order: [], active: null,
    enemy: null, fighter: null, last: null, gate: null, benchmark: false,
    events: [], encounters: 0, traps: { faced: 0, falsified: 0 }, shattered: 0,
    finale: null, stopped: false, error: null,
    // the Research Director's console and the endgame
    chat: [], mysteries: {}, intakes: [], mystery: null, adjust: [], secret: null,
    bridge: null, assessment: null, choice: null, evolution: null, version: "V1", spec: null, trial: null,
  };
}

// A Mystery Boss fights the scroll as it stands at the end of the level on screen, so rows of that level still
// waiting to be shown carry HP snapshots from before the fight. adjust holds each fight's HP change and seq;
// a row older than a fight gets that fight's change added.
function hpFor(s, id, e) {
  let hp = e.hp;
  for (const x of s.adjust) if (x.id === id && x.seq > e.seq) hp += x.delta;
  return Math.max(0, Math.min(100, hp));
}

function agentFrom(a) {
  return {
    id: a.id, name: a.name, archetype: a.archetype, cls: a.cls, title: a.title, nickname: a.nickname,
    claim: a.claim, outcome: a.outcome, origin: a.origin, design: a.design, K: a.K,
    evidence: a.evidence || "simulated", realEvidence: a.real_evidence || null, how: "",
    hp: a.hp, credits: a.credits, buffs: a.buffs || [],
    status: "active", verdict: null, abilities: {}, lastDelta: null, lines: {},
  };
}

// Apply one ledger row. Returns the same (mutated) state object for speed; replay() starts fresh.
function reduce(s, e) {
  s.events.push(e);
  const r = e.result || {};
  const a = e.agent_id ? s.agents[e.agent_id] : null;
  if (a) {  // the row's snapshot of the scroll wins: it is what the Judge recorded
    if (e.hp != null) a.hp = hpFor(s, a.id, e);
    if (e.credits != null) a.credits = e.credits;
    const broken = s.adjust.some((x) => x.id === a.id && x.shatter && x.seq > e.seq);
    if (e.status && !broken) a.status = e.status;
    if (e.verdict) a.verdict = e.verdict;
    if (e.agent && Array.isArray(e.agent.buffs)) a.buffs = e.agent.buffs;
    if (a.status === "active") s.active = a.id;
  }
  switch (e.action) {
    case "quest_start":
      s.campaign = r.campaign; s.rules = r.rules; s.archetypes = r.archetypes; s.simulated = r.simulated !== false;
      s.hero = r.hero || null; s.gatekeeper = r.gatekeeper || null;
      break;
    case "hypotheses":
      s.hypotheses = r;   // how the Scribe formed the scrolls, and the real evidence counts it copied
      break;
    case "recruit": {
      const ag = agentFrom(r.agent);
      ag.how = e.explain || "";
      s.agents[ag.id] = ag;
      if (!s.order.includes(ag.id)) s.order.push(ag.id);
      break;
    }
    case "level_start":
      s.level = r.level; s.levelInfo[r.level] = r; s.enemy = null; s.fighter = null; s.gate = null;
      break;
    case "gatekeeper":
    case "benchmark":
      s.gate = { text: r.text, level: e.level, seq: e.seq };
      if (e.action === "benchmark") s.benchmark = true;
      break;
    case "decision":
      if (a) { a.abilities[e.level] = r.abilities || []; a.lines[e.level] = e.line; }
      break;
    case "encounter":
      s.enemy = { ...(r.enemy || {}), boss: !!r.boss }; s.fighter = null;
      break;
    case "result":
      s.fighter = e.agent_id; s.last = e;
      if (a) a.lastDelta = e.hp_delta;
      if (e.encounter) s.encounters += 1;
      if (e.passed != null) { s.traps.faced += 1; if (e.passed) s.traps.falsified += 1; }
      break;
    case "shatter":
      s.shattered += 1;
      if (s.mystery) s.adjust.push({ id: e.agent_id, seq: e.seq, delta: 0, shatter: true });
      if (s.active === e.agent_id) s.active = s.order.find((id) => s.agents[id].status === "active") || null;
      break;
    case "level_complete":
      s.levelDone[r.level] = r;
      break;
    case "finale":
      s.finale = r; s.level = 5; s.enemy = null; s.fighter = null; s.gate = null;
      for (const row of r.ranking || []) if (s.agents[row.id]) s.agents[row.id].verdict = row.verdict;
      break;
    case "stopped":
      s.stopped = true;
      break;
    // ---------- the Research Director's console ----------
    case "chat":
    case "hero_reply":
      s.chat.push({ seq: e.seq, who: e.action === "chat" ? "director" : "hero", text: r.text || e.line, mode: r.mode,
                    url: r.url, filename: r.filename, mystery: r.mystery, intake: r.intake, level: e.level });
      break;
    case "evidence_intake":
      if (r.intake) s.intakes.push(r.intake);
      break;
    case "mystery_offer":
    case "mystery_unresolved":
    case "mystery_saved":
    case "mystery_cancelled":
    case "mystery_summon":
    case "mystery_return":
      if (r.mystery) s.mysteries[r.mystery.id] = r.mystery;
      if (e.action === "mystery_return") { s.enemy = null; s.fighter = null; s.mystery = null; }
      if (e.action === "mystery_summon") s.mystery = r.mystery.id;
      break;
    case "secret_level_start":
      s.secret = r.secret;
      break;
    case "secret_level_complete":
      s.secret = null;
      break;
    case "mystery_encounter":
      s.enemy = { ...(r.enemy || {}) }; s.fighter = null;
      break;
    case "mystery_ability":
      s.fighter = e.agent_id;
      break;
    case "mystery_result":
      s.fighter = e.agent_id; s.last = e;
      if (a) a.lastDelta = e.hp_delta;
      if (r.mystery) s.mysteries[r.mystery.id] = r.mystery;
      if (e.hp_delta) s.adjust.push({ id: e.agent_id, seq: e.seq, delta: e.hp_delta });
      break;
    // ---------- the Bridge of Judgment ----------
    case "bridge_enter":
      s.bridge = { ...r, seq: e.seq }; s.level = 5; s.enemy = null; s.fighter = null; s.gate = null;
      break;
    case "self_assessment":
      s.assessment = r.assessment; s.choice = null;
      break;
    case "bridge_choice":
      s.choice = r;
      break;
    case "evolution_start":
      s.evolution = { plan: r.plan, v1: r.v1, cost: r.cost, links: r.causal_links, steps: [], done: null };
      break;
    case "evolution_transform":
      s.version = "V2";
      break;
    case "evolution_step":
      if (s.evolution) s.evolution.steps.push(e);
      break;
    case "evolution_complete":
      if (s.evolution) s.evolution.done = r;
      break;
    case "spec_locked":
      s.spec = { ...r.spec, sha256: r.sha256 };
      break;
    case "trial_result":
      s.trial = r.trial;
      break;
    case "error":
      s.error = e.line;
      break;
    default:
  }
  return s;
}

function replay(events) { return events.reduce(reduce, initial()); }

// The node bar: which nodes are done, which is current.
function nodeStates(s) {
  return NODES.map((n) => ({
    ...n, name: n.name || (s.levelInfo[n.level] && s.levelInfo[n.level].name) || `Level ${n.numeral}`,
    done: n.level < 5 ? !!s.levelDone[n.level] : !!s.finale,
    current: s.level === n.level,
  }));
}

// Ledger filter: by scroll id ("gatekeeper" for the Skeptic's lines), level, kind, and free text.
function filterEvents(events, f = {}) {
  const q = (f.text || "").trim().toLowerCase();
  return events.filter((e) => {
    if (f.agent === "gatekeeper" && !["gatekeeper", "benchmark"].includes(e.action)) return false;
    if (f.agent && f.agent !== "gatekeeper" && e.agent_id !== f.agent) return false;
    if (f.level && String(e.level) !== String(f.level)) return false;
    if (f.kind === "judge" && e.action !== "result") return false;
    if (f.kind === "agent" && e.actor !== "agent") return false;
    if (f.kind === "director" && !(e.actor === "director" || /^(mystery|evidence|secret|hero_reply)/.test(e.action))) return false;
    if (f.kind === "hp" && !(e.hp_delta)) return false;
    if (q && !`${e.line || ""} ${e.explain || ""} ${e.enemy || ""} ${(e.encounter && e.encounter.encounterId) || ""}`
      .toLowerCase().includes(q)) return false;
    return true;
  });
}

// How long a row stays on screen at 1x, in ms.
function beat(e) {
  if (e.action === "result" && e.result && e.result.scout && !e.hp_delta) return 650;
  return { quest_start: 500, hypotheses: 2200, recruit: 900, gatekeeper: 2200, benchmark: 2000, level_start: 1500, decision: 950,
           encounter: 900, result: 1300, shatter: 1700, level_complete: 300, finale: 300,
           chat: 0, hero_reply: 0, evidence_intake: 0, mystery_offer: 0, mystery_unresolved: 0, mystery_saved: 0,
           mystery_cancelled: 0, mystery_summon: 1100, mystery_encounter: 1300, mystery_ability: 1000, mystery_result: 2200,
           mystery_return: 900, secret_level_start: 1800, secret_level_complete: 1200,
           bridge_enter: 2600, self_assessment: 600, bridge_choice: 1200, evolution_start: 1500, evolution_transform: 2600,
           evolution_step: 1500, evolution_complete: 1800, spec_locked: 1800, trial_result: 3600 }[e.action] || 500;
}

function findEncounter(events, id) {
  return events.find((e) => e.encounter && e.encounter.encounterId === id) || null;
}

if (typeof module !== "undefined") {
  module.exports = { NODES, initial, reduce, replay, nodeStates, filterEvents, beat, findEncounter, hpFor };
}
