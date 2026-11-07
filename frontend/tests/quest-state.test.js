// Run: node --test frontend/tests/
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { initialState, reduce, standing, ENEMIES, TESTS } = require("../src/quest-state.js");

const ledger = path.join(__dirname, "..", "src", "demo-quest.jsonl");
const events = fs.readFileSync(ledger, "utf8").trim().split("\n").map(JSON.parse);

test("the recorded quest folds into a finale with every hero accounted for", () => {
  const s = events.reduce(reduce, initialState());
  assert.ok(s.finale);
  assert.strictEqual(s.order.length, s.finale.ranking.length);
  assert.deepStrictEqual(Object.keys(s.levelSummaries).map(Number), [1, 2, 3, 4]);
  assert.strictEqual(standing(s).length, 0);
  for (const r of s.finale.ranking) assert.strictEqual(s.heroes[r.id].verdict, r.verdict);
});

test("hero HP and credits match the last event the backend wrote for them", () => {
  const s = events.reduce(reduce, initialState());
  for (const id of s.order) {
    const last = events.filter((e) => e.agent_id === id && e.hp != null).pop();
    assert.strictEqual(s.heroes[id].hp, last.hp);
    assert.strictEqual(s.heroes[id].credits, last.credits);
  }
});

test("an encounter collects all seven pieces of combat feedback", () => {
  const s = initialState();
  const i = events.findIndex((e) => e.action === "result" && e.passed === false && e.hp_delta < 0);
  const start = events.slice(0, i).map((e, k) => [e, k]).filter(([e]) => e.action === "encounter").pop()[1];
  events.slice(0, i + 1).forEach((e) => reduce(s, e));
  const enc = s.encounter;
  assert.ok(ENEMIES[enc.enemy] && enc.attack && enc.ability && TESTS[enc.test]);
  assert.ok(enc.result && enc.explain && enc.delta < 0 && enc.passed === false);
  assert.strictEqual(enc.hero, events[start].agent_id);
});

test("every enemy and test in the ledger has a name the screen can show", () => {
  for (const e of events) {
    if (e.enemy) assert.ok(ENEMIES[e.enemy], e.enemy);
    if (e.test) assert.ok(TESTS[e.test], e.test);
  }
});
