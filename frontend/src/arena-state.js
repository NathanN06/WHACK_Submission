// Pure state reducer: ledger events in, screen state out. No DOM here, so it runs in Node tests.

function initialState() {
  return { reputation: 100, denarii: 60, day: 0, dayName: "", gladiators: {}, order: [],
           feed: [], summary: null };
}

function reduce(s, e) {
  if (e.reputation != null) s.reputation = e.reputation;
  if (e.denarii != null) s.denarii = e.denarii;
  if (e.day != null) s.day = e.day;
  if (e.action === "day_start") s.dayName = e.line;

  const id = e.gladiator_id;
  if (id) {
    let g = s.gladiators[id];
    if (!g) {
      g = s.gladiators[id] = { id, claim: "", features: [], origin: "", hp: 100,
                                status: "tunnel", verdict: null, last: "", bornAt: e.seq, hitAt: 0 };
      s.order.push(id);
    }
    if (e.gladiator) {
      g.claim = e.gladiator.claim;
      g.features = e.gladiator.add_features;
      g.origin = e.gladiator.origin;
    }
    if (e.hp != null) {
      if (e.hp < g.hp) g.hitAt = e.seq;
      g.hp = e.hp;
    }
    if (e.status) g.status = e.status;
    if (e.verdict) g.verdict = e.verdict;
    if (e.action === "result" && e.line) g.last = e.line;
  }
  if (e.line) s.feed.unshift({ seq: e.seq, actor: e.actor, line: e.line, gid: id || null,
                               passed: e.passed == null ? null : e.passed });
  if (e.action === "summary") s.summary = e.result;
  return s;
}

const LANES = {
  tunnel: "tunnel", arena: "arena",
  survivor: "standing", champion: "standing", unproven: "standing", untestable: "standing",
  dead: "graveyard", dropped: "graveyard", fallen: "graveyard",
};

function laneOf(g) { return LANES[g.status] || "tunnel"; }

function counts(s) {
  const all = s.order.map((id) => s.gladiators[id]);
  return {
    fought: all.length,
    fallen: all.filter((g) => laneOf(g) === "graveyard").length,
    standing: all.filter((g) => laneOf(g) === "standing").length,
  };
}

if (typeof module !== "undefined") module.exports = { initialState, reduce, laneOf, counts };
