// Run: node --test frontend/tests/
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { initialState, reduce, laneOf, counts } = require("../src/arena-state.js");

const fixture = path.join(__dirname, "sample-run.jsonl");
const events = fs.readFileSync(fixture, "utf8").trim().split("\n").map(JSON.parse);

test("a whole recorded game folds into a final screen", () => {
  const s = events.reduce(reduce, initialState());
  const c = counts(s);
  assert.strictEqual(c.fought, s.order.length);
  assert.strictEqual(c.fought, c.fallen + c.standing);
  assert.ok(s.summary && s.summary.total_decoys >= 4);
  assert.strictEqual(s.reputation, events[events.length - 1].reputation);
});

test("the leak ends in the graveyard as LEAKY with 0 hp", () => {
  const s = events.reduce(reduce, initialState());
  const leak = Object.values(s.gladiators).find((g) => g.features[0] === "meal_intensity_score");
  assert.strictEqual(leak.verdict, "LEAKY");
  assert.strictEqual(leak.hp, 0);
  assert.strictEqual(laneOf(leak), "graveyard");
  assert.ok(leak.hitAt > 0);
});

test("a gladiator moves tunnel -> arena -> standing", () => {
  const s = initialState();
  reduce(s, { seq: 1, actor: "lanista", action: "propose", gladiator_id: "G01", status: "tunnel", hp: 100,
              gladiator: { claim: "fibre", add_features: ["fiber"], origin: "researcher" }, line: "fibre" });
  assert.strictEqual(laneOf(s.gladiators.G01), "tunnel");
  reduce(s, { seq: 2, actor: "lanista", action: "back", gladiator_id: "G01", status: "arena", hp: 100 });
  assert.strictEqual(laneOf(s.gladiators.G01), "arena");
  reduce(s, { seq: 3, actor: "engine", action: "survivor", gladiator_id: "G01", status: "survivor",
              verdict: "SURVIVOR", hp: 100 });
  assert.strictEqual(laneOf(s.gladiators.G01), "standing");
  assert.strictEqual(s.feed[0].line, "fibre");
});
