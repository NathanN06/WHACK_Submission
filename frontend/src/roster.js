// Roster editor logic: which hypotheses enter the arena each day. No DOM here, so it runs in Node tests.

function initRoster(days, max) {
  return {
    max,
    days: days.map((d) => ({
      day: d.day, name: d.name, features: d.features, catalog: d.catalog,
      rows: d.hypotheses.map((h, i) => ({
        claim: h.claim, f1: h.add_features[0], f2: h.add_features[1] || "", on: i < max,
      })),
    })),
  };
}

function ticked(r, i) { return r.days[i].rows.filter((x) => x.on).length; }

function canTick(r, i) { return ticked(r, i) < r.max; }

function setMax(r, max) {
  r.max = max;
  for (const d of r.days) {
    let n = 0;
    for (const row of d.rows) if (row.on && ++n > max) row.on = false;
  }
  return r;
}

function toPayload(r) {
  const roster = {};
  for (const d of r.days) {
    roster[d.day] = d.rows
      .filter((x) => x.on && x.claim.trim() && x.f1)
      .map((x) => ({ claim: x.claim.trim(), add_features: [...new Set([x.f1, x.f2].filter(Boolean))] }));
  }
  return { max_per_day: r.max, roster };
}

if (typeof module !== "undefined") module.exports = { initRoster, ticked, canTick, setMax, toPayload };
