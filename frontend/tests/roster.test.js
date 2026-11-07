// Run: node --test frontend/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert");
const { initRoster, canTick, setMax, toPayload } = require("../src/roster.js");

const BODY = {
  max_in: 2,
  features: [{ name: "carbs" }, { name: "fiber" }, { name: "fat" }],
  hypotheses: [{ claim: "Carbs spike it", add_features: ["carbs"] },
               { claim: "Fibre", add_features: ["fiber"] }, { claim: "Fat", add_features: ["fat"] }],
};

test("starts with the first max hypotheses ticked", () => {
  const r = initRoster(BODY);
  assert.deepStrictEqual(r.rows.map((x) => x.on), [true, true, false]);
  assert.strictEqual(canTick(r), false);
});

test("lowering the max unticks the extras", () => {
  const r = setMax(initRoster(BODY), 1);
  assert.deepStrictEqual(r.rows.map((x) => x.on), [true, false, false]);
  assert.strictEqual(canTick(setMax(r, 3)), true);
});

test("payload sends only ticked, non-empty rows, with up to two distinct features", () => {
  const r = setMax(initRoster(BODY), 3);
  r.rows[0].f2 = "carbs";
  r.rows[1].f2 = "fat";
  r.rows[2].claim = "   ";
  assert.deepStrictEqual(toPayload(r), {
    max_in: 3,
    hypotheses: [{ claim: "Carbs spike it", add_features: ["carbs"] },
                 { claim: "Fibre", add_features: ["fiber", "fat"] }],
  });
});
