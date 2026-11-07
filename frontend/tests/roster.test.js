// Run: node --test frontend/tests/
const test = require("node:test");
const assert = require("node:assert");
const { initRoster, canTick, setMax, toPayload } = require("../src/roster.js");

const DAYS = [
  { day: 1, name: "Day I", features: ["carbs"], catalog: [{ name: "carbs", day: 1 }],
    hypotheses: [{ claim: "Carbs spike it", add_features: ["carbs"] }] },
  { day: 2, name: "Day II", features: ["fiber", "fat", "protein"],
    catalog: [{ name: "carbs", day: 1 }, { name: "fiber", day: 2 }, { name: "fat", day: 2 }, { name: "protein", day: 2 }],
    hypotheses: [{ claim: "Fibre", add_features: ["fiber"] }, { claim: "Fat", add_features: ["fat"] },
                 { claim: "Protein", add_features: ["protein"] }] },
];

test("starts with the first max hypotheses of each day ticked", () => {
  const r = initRoster(DAYS, 2);
  assert.deepStrictEqual(r.days[1].rows.map((x) => x.on), [true, true, false]);
  assert.strictEqual(canTick(r, 1), false);
  assert.strictEqual(canTick(r, 0), true);
});

test("lowering the max unticks the extras", () => {
  const r = setMax(initRoster(DAYS, 3), 1);
  assert.deepStrictEqual(r.days[1].rows.map((x) => x.on), [true, false, false]);
});

test("payload sends only ticked, non-empty rows, with up to two distinct features", () => {
  const r = initRoster(DAYS, 3);
  r.days[1].rows[0].f2 = "fat";
  r.days[1].rows[1].claim = "   ";
  r.days[1].rows[2].f2 = "protein";
  assert.deepStrictEqual(toPayload(r), {
    max_per_day: 3,
    roster: {
      1: [{ claim: "Carbs spike it", add_features: ["carbs"] }],
      2: [{ claim: "Fibre", add_features: ["fiber", "fat"] }, { claim: "Protein", add_features: ["protein"] }],
    },
  });
});
