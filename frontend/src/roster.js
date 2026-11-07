// Roster editor logic: which hypotheses enter the arena. No DOM here, so it runs in Node tests.

function initRoster(body, max = body.max_in) {
  return {
    max,
    features: body.features.map((f) => f.name),
    rows: body.hypotheses.map((h, i) => ({
      claim: h.claim, f1: h.add_features[0], f2: h.add_features[1] || "", on: i < max,
    })),
  };
}

function ticked(r) { return r.rows.filter((x) => x.on).length; }

function canTick(r) { return ticked(r) < r.max; }

function setMax(r, max) {
  r.max = max;
  let n = 0;
  for (const row of r.rows) if (row.on && ++n > max) row.on = false;
  return r;
}

function toPayload(r) {
  return {
    max_in: r.max,
    hypotheses: r.rows
      .filter((x) => x.on && x.claim.trim() && x.f1)
      .map((x) => ({ claim: x.claim.trim(), add_features: [...new Set([x.f1, x.f2].filter(Boolean))] })),
  };
}

if (typeof module !== "undefined") module.exports = { initRoster, ticked, canTick, setMax, toPayload };
