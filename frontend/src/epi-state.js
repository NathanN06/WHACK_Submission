// The game state is a fold over the ledger: every number on screen comes from a ledger row.
// Pure enough to test in node:  const { initial, reduce, replay } = require("./epi-state.js").

const NODES = [
  { level: 1, numeral: "I" }, { level: 2, numeral: "II" }, { level: 3, numeral: "III" }, { level: 4, numeral: "IV" },
  { level: 5, numeral: "✦", name: "Situation Room" },
];

function initial() {
  return {
    campaign: null, rules: null, archetypes: null, simulated: true,
    level: 0, levelInfo: {}, levelDone: {},
    agents: {}, order: [],
    enemy: null, fighter: null, last: null,
    events: [], encounters: 0, traps: { faced: 0, falsified: 0 }, fallen: 0,
    finale: null, stopped: false, error: null,
  };
}

function agentFrom(a) {
  return {
    id: a.id, name: a.name, archetype: a.archetype, cls: a.cls, title: a.title, nickname: a.nickname,
    claim: a.claim, streams: a.streams || [], K: a.K, usesAr: a.uses_ar, cohortN: a.cohort_n,
    hp: a.hp, credits: a.credits, buffs: a.buffs || [], signature: a.signature || [],
    status: "active", verdict: null, abilities: {}, lastDelta: null, lines: {},
  };
}

// Apply one ledger row. Returns the same (mutated) state object for speed; replay() starts fresh.
function reduce(s, e) {
  s.events.push(e);
  const r = e.result || {};
  const a = e.agent_id ? s.agents[e.agent_id] : null;
  if (a) {  // the row's snapshot of the agent wins: it is what the Judge recorded
    if (e.hp != null) a.hp = e.hp;
    if (e.credits != null) a.credits = e.credits;
    if (e.status) a.status = e.status;
    if (e.verdict) a.verdict = e.verdict;
    if (e.agent && Array.isArray(e.agent.buffs)) a.buffs = e.agent.buffs;
  }
  switch (e.action) {
    case "quest_start":
      s.campaign = r.campaign; s.rules = r.rules; s.archetypes = r.archetypes; s.simulated = r.simulated !== false;
      break;
    case "recruit": {
      const ag = agentFrom(r.agent);
      s.agents[ag.id] = ag;
      if (!s.order.includes(ag.id)) s.order.push(ag.id);
      break;
    }
    case "level_start":
      s.level = r.level; s.levelInfo[r.level] = r; s.enemy = null; s.fighter = null;
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
    case "fall":
      s.fallen += 1;
      break;
    case "level_complete":
      s.levelDone[r.level] = r;
      break;
    case "finale":
      s.finale = r; s.level = 5; s.enemy = null; s.fighter = null;
      for (const row of r.ranking || []) if (s.agents[row.id]) s.agents[row.id].verdict = row.verdict;
      break;
    case "stopped":
      s.stopped = true;
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

// Ledger filter: by agent id, level, kind ("judge" | "agent" | "hp"), and free text.
function filterEvents(events, f = {}) {
  const q = (f.text || "").trim().toLowerCase();
  return events.filter((e) => {
    if (f.agent && e.agent_id !== f.agent) return false;
    if (f.level && String(e.level) !== String(f.level)) return false;
    if (f.kind === "judge" && e.action !== "result") return false;
    if (f.kind === "agent" && e.actor !== "agent") return false;
    if (f.kind === "hp" && !(e.hp_delta)) return false;
    if (q && !`${e.line || ""} ${e.explain || ""} ${e.enemy || ""} ${(e.encounter && e.encounter.encounterId) || ""}`
      .toLowerCase().includes(q)) return false;
    return true;
  });
}

// How long a row stays on screen at 1x, in ms.
function beat(e) {
  if (e.action === "result" && e.result && (e.result.scout || e.result.na) && !e.hp_delta) return 550;
  return { quest_start: 500, recruit: 800, level_start: 1500, decision: 950, encounter: 900, result: 1250,
           loot: 800, fall: 1500, benchmark: 1000, level_complete: 300, finale: 300 }[e.action] || 500;
}

function findEncounter(events, id) {
  return events.find((e) => e.encounter && e.encounter.encounterId === id) || null;
}

if (typeof module !== "undefined") {
  module.exports = { NODES, initial, reduce, replay, nodeStates, filterEvents, beat, findEncounter };
}
