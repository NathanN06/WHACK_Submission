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
