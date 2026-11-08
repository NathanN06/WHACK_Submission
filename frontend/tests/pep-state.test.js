// The reducer folds a recorded ledger into the game state; every number must match the ledger.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { replay, initial, reduce, nodeStates, filterEvents, beat, findEncounter } = require("../src/pep-state.js");

const load = (L) => fs.readFileSync(path.join(__dirname, `../src/demo/demo-${L}.jsonl`), "utf8")
  .split("\n").filter(Boolean).map((l) => JSON.parse(l));

for (const L of ["A", "B", "C", "D"]) {
  test(`campaign ${L} replays to the finale with the ledger's numbers`, () => {
    const events = load(L);
    const s = replay(events);
    const fin = events[events.length - 1];
    assert.strictEqual(fin.action, "finale");
    assert.strictEqual(s.finale, fin.result);
    assert.strictEqual(s.order.length, 3);
    assert.ok(s.hero && s.gatekeeper);
    assert.ok(s.events.some((e) => e.action === "gatekeeper"));
    for (const r of fin.result.ranking) {
      assert.strictEqual(s.agents[r.id].hp, r.hp, `${r.name} HP`);
      assert.strictEqual(s.agents[r.id].verdict, r.verdict);
      assert.strictEqual(100 - s.agents[r.id].credits, r.spent, `${r.name} credits`);
    }
    assert.strictEqual(s.encounters, fin.result.totals.encounters);
    assert.strictEqual(s.shattered, fin.result.totals.shattered);
    assert.ok(nodeStates(s).every((n) => n.done));
    assert.ok(s.simulated);
  });
}

test("B, C and D end with the baseline holding; A crowns a validated champion", () => {
  for (const L of ["B", "C", "D"]) assert.strictEqual(replay(load(L)).finale.baseline_holds, true);
  const a = replay(load("A")).finale;
  assert.strictEqual(a.champion.verdict, "VALIDATED");
});

test("every brief citation points at a real encounter", () => {
  for (const L of ["A", "B", "C", "D"]) {
    const events = load(L), b = replay(events).finale.brief;
    for (const ev of [...b.evidence, ...b.misleading]) assert.ok(findEncounter(events, ev.cite), `${L} ${ev.cite}`);
  }
});

test("a partial ledger shows the level in progress", () => {
  const events = load("A");
  const upTo = events.findIndex((e) => e.action === "level_start" && e.level === 2);
  const s = events.slice(0, upTo + 1).reduce(reduce, initial());
  const nodes = nodeStates(s);
  assert.ok(nodes[0].done && nodes[1].current && !nodes[1].done && !nodes[4].done);
  assert.strictEqual(s.finale, null);
});

test("ledger filters", () => {
  const events = load("A");
  const judge = filterEvents(events, { kind: "judge" });
  assert.ok(judge.length && judge.every((e) => e.action === "result"));
  assert.ok(filterEvents(events, { agent: "pioneer", level: 4 }).every((e) => e.agent_id === "pioneer" && e.level === 4));
  assert.ok(filterEvents(events, { kind: "hp" }).every((e) => e.hp_delta));
  assert.ok(filterEvents(events, { text: "E030" }).length >= 1);
  assert.ok(filterEvents(events, { agent: "gatekeeper" }).every((e) => ["gatekeeper", "benchmark"].includes(e.action)));
  assert.ok(beat(events[0]) > 0);
});

test("a shattered scroll stays shattered and the active scroll moves on", () => {
  const events = load("A");
  const at = events.findIndex((e) => e.action === "shatter");
  const s = events.slice(0, at + 1).reduce(reduce, initial());
  const gone = s.agents[events[at].agent_id];
  assert.strictEqual(gone.status, "shattered");
  assert.strictEqual(gone.hp, 0);
  assert.notStrictEqual(s.active, gone.id);
});

test("every recorded campaign ends on the Bridge with a locked spec and a Trial of Truth", () => {
  for (const L of ["A", "B", "C", "D"]) {
    const s = replay(load(L));
    assert.ok(s.bridge && s.assessment && s.choice, `${L}: bridge rows`);
    assert.ok(s.trial && s.trial.outcome, `${L}: trial`);
    assert.strictEqual(s.finale.overworld.trial.outcome, s.trial.outcome);
    if (s.trial.evaluated) assert.ok(s.spec && s.spec.sha256);
  }
});

test("a Mystery Boss's HP change survives the older rows of the level still being shown", () => {
  const s = initial();
  reduce(s, { seq: 1, action: "recruit", result: { agent: { id: "p", name: "P", archetype: "PIONEER", hp: 100, credits: 100 } } });
  // the fight happened server-side after row 3 was written, but is shown before it
  reduce(s, { seq: 9, action: "mystery_result", agent_id: "p", hp: 90, hp_delta: -10, result: {} });
  assert.strictEqual(s.agents.p.hp, 90);
  reduce(s, { seq: 3, action: "result", agent_id: "p", hp: 80, hp_delta: -20, result: {} });
  assert.strictEqual(s.agents.p.hp, 70);            // 80 as recorded, minus the later fight's 10
  reduce(s, { seq: 12, action: "result", agent_id: "p", hp: 70, result: {} });
  assert.strictEqual(s.agents.p.hp, 70);            // rows after the fight already include it
});

test("the console's rows land in the chat and the mystery book", () => {
  const s = initial();
  reduce(s, { seq: 1, action: "chat", actor: "director", result: { mode: "CHALLENGE", text: "luck?" } });
  reduce(s, { seq: 2, action: "mystery_offer", result: { mystery: { id: "M01", status: "offered", boss: "The Probability Phantom" } } });
  reduce(s, { seq: 3, action: "hero_reply", result: { text: "A fair challenge.", mystery: "M01" } });
  assert.deepStrictEqual(s.chat.map((m) => m.who), ["director", "hero"]);
  assert.strictEqual(s.mysteries.M01.status, "offered");
  assert.strictEqual(filterEvents(s.events, { kind: "director" }).length, 3);
});

test("the Archivist's Ledger: every encounter names a registered method and registered sources", () => {
  for (const L of ["A", "B", "C", "D"]) {
    const events = load(L), s = replay(events);
    assert.ok(s.sources.length >= 6 && Object.keys(s.methods).length >= 10, `${L}: sources registered`);
    assert.ok(s.rulesetVersion && s.dataset && s.dataset.fingerprints.train, `${L}: commitments published at the start`);
    const known = new Set(s.sources.map((x) => x.id));
    for (const e of events.filter((x) => x.encounter)) {
      const t = e.encounter;
      assert.ok(s.methods[t.methodId], `${L} ${t.encounterId}: method ${t.methodId}`);
      for (const id of t.sourceIds) assert.ok(known.has(id), `${L} ${t.encounterId}: source ${id}`);
      assert.strictEqual(t.rulesetVersion, s.rulesetVersion);
    }
    const arc = s.finale.archive;
    assert.ok(arc.check.complete, `${L}: ${arc.check.problems.join("; ")}`);
    assert.strictEqual(arc.check.encounters, events.filter((x) => x.encounter).length);
    assert.match(arc.sha256, /^[0-9a-f]{64}$/);
    assert.deepStrictEqual(arc.fingerprints, s.dataset.fingerprints);
  }
});

test("each question gets a scientific status, and champions never cross questions", () => {
  for (const L of ["A", "B", "C", "D"]) {
    const events = load(L), f = replay(events).finale;
    assert.ok(f.tracks.length >= 1 && f.tracks.some((t) => t.primary));
    for (const t of f.tracks) {
      assert.ok(["SUPPORTED", "REFUTED", "INCONCLUSIVE", "NOT ASSESSED"].includes(t.science.status), `${L} ${t.outcome}`);
      if (t.cite) assert.ok(findEncounter(events, t.cite), `${L} ${t.cite}`);
      if (t.champion) assert.strictEqual(f.ranking.find((r) => r.id === t.champion).track, t.outcome);
    }
    for (const r of f.ranking) assert.ok(f.tracks.some((t) => t.outcome === r.track), `${L} ${r.id} has a track`);
  }
  assert.strictEqual(replay(load("A")).finale.tracks[0].science.status, "SUPPORTED");
  assert.strictEqual(replay(load("B")).finale.tracks[0].science.status, "REFUTED");
});

test("sources, Challenger rounds and timeouts fold into the state", () => {
  const s = initial();
  reduce(s, { seq: 1, action: "sources_registered", result: { sources: [{ id: "S-TRAIN", type: "SIMULATED" }], methods: { M: "m" } } });
  reduce(s, { seq: 2, action: "source_registered", result: { source: { id: "S-X01", type: "USER_UPLOADED", usage: "CONTEXT" } } });
  reduce(s, { seq: 3, action: "source_registered", result: { source: { id: "S-X01", type: "USER_UPLOADED", usage: "EXCLUDED" } } });
  assert.deepStrictEqual(s.sources.map((x) => x.id), ["S-TRAIN", "S-X01"]);
  assert.strictEqual(s.sources[1].usage, "EXCLUDED");
  reduce(s, { seq: 4, action: "challenger_roster", result: { round: 2, incumbent: { hid: "H-1" }, challengers: ["pioneer"] } });
  reduce(s, { seq: 5, action: "recruit", result: { agent: { id: "champion", name: "C", archetype: "PIONEER", hp: 100, credits: 100,
                                                            track: "alcohol", champion: { hid: "H-1", defended: 0 } } } });
  assert.strictEqual(s.challenger.round, 2);
  assert.strictEqual(s.agents.champion.champion.hid, "H-1");
  assert.strictEqual(s.agents.champion.track, "alcohol");
  reduce(s, { seq: 6, action: "champion_update", result: { result: "CHAMPION DEFENDED", winner: "champion" } });
  assert.strictEqual(s.championUpdate.result, "CHAMPION DEFENDED");
  reduce(s, { seq: 7, action: "timeout", line: "Nobody watched." });
  assert.ok(s.stopped && s.timedOut);
  assert.ok(beat({ action: "challenger_roster" }) > 0 && beat({ action: "source_registered" }) === 0);
});

test("a repeated test changes nothing", () => {
  const s = initial();
  reduce(s, { seq: 1, action: "recruit", result: { agent: { id: "p", name: "P", archetype: "PIONEER", hp: 100, credits: 100 } } });
  reduce(s, { seq: 2, action: "mystery_result", agent_id: "p", hp: 90, hp_delta: -10, result: { outcome: "FALLEN", mystery: { id: "M01", status: "fallen" } } });
  reduce(s, { seq: 3, action: "mystery_result", agent_id: "p", hp: 90, hp_delta: 0,
              result: { outcome: "REPEAT", mystery: { id: "M02", status: "repeat", repeat_of: "M01" } } });
  assert.strictEqual(s.agents.p.hp, 90);
  assert.strictEqual(s.adjust.length, 1);
  assert.strictEqual(s.mysteries.M02.repeat_of, "M01");
});
