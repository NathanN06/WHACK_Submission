// Pure state reducer for the Hypothesis Gauntlet: ledger events in, game state out.
// No DOM here, so it runs in Node tests. The screen (gauntlet.js) animates each event
// and reads this state; every number shown comes from an event the backend wrote.

const ENEMIES = {
  slime: { name: "Slime of Misinformation", level: 1 },
  goblin: { name: "Rumour Goblin", level: 1 },
  bat: { name: "Anecdote Bat", level: 1 },
  wisp: { name: "Echo Chamber Wisp", level: 1 },
  mimic: { name: "Preprint Mimic", level: 2 },
  skeleton: { name: "Small Sample Skeleton", level: 2 },
  phantom: { name: "Confounding Phantom", level: 2 },
  spider: { name: "Citation Spider", level: 2 },
  sentinel: { name: "Replication Sentinel", level: 3 },
  wraith: { name: "Contradiction Wraith", level: 3 },
  chimera_overfit: { name: "The Data Chimera", head: "Overfitting", level: 3, boss: true },
  chimera_selection: { name: "The Data Chimera", head: "Selection Bias", level: 3, boss: true },
  knight: { name: "Publication Bias Knight", level: 3 },
  chronolock: { name: "Chronolock Guardian", level: 4, boss: true },
  reaper: { name: "The Leakage Reaper", level: 4, boss: true },
  titan: { name: "The Bureaucratic Titan", level: 4, boss: true },
  guardian: { name: "Guardian of False Discoveries", level: 4, boss: true, final: true },
};

const ABILITIES = {
  fact_check: "Fact Check", bias_detection: "Bias Detection", replication_shield: "Replication Shield",
  ablation_strike: "Ablation Strike", temporal_guard: "Temporal Guard", preregister: "Preregister",
};

// What each test is, in words anyone can follow.
const TESTS = {
  coverage: "Count the people whose data can judge the claim",
  raw_direction: "Correlation in the raw data, bootstrapped over people",
  within_person: "Does the pattern hold inside each person's own meals?",
  echo: "Correlation of the evidence with carbs (the baseline)",
  added_value: "Cross-validated error with vs without the evidence (folds split by person)",
  majority_benefit: "Share of people predicted better",
  confounding: "Raw direction vs direction after adjusting for carbs",
  too_good: "Size of the gain vs the baseline error",
  fold_replication: "Replicate in 5 independent groups of people",
  sensor_check: "Repeat with each glucose sensor separately",
  shuffle_test: "Permutation test: real evidence vs scrambled copies",
  trimmed_gain: "Recompute the gain without the top 10% of contributors",
  penalty: "Benjamini-Hochberg correction across every claim tried",
  temporal: "Was every piece of evidence known at mealtime?",
  leak_audit: "Is any evidence built from the outcome itself?",
  provenance: "Is the evidence recorded in the independent dataset?",
  final_boss: "Train on discovery people, score on never-seen people vs baseline",
};

const GOOD = new Set(["VALIDATED"]);

function initialState() {
  return { level: 0, levelName: "", levels: {}, heroes: {}, order: [], feed: [], encounter: null,
           skepticLine: "", levelSummaries: {}, finale: null, error: null, startingCredits: 18,
           rules: null, question: "", sources: null, records: [] };
}

function hero(s, id) {
  let h = s.heroes[id];
  if (!h) {
    h = s.heroes[id] = { id, name: id, cls: "Wanderer", claim: "", features: [], direction: "either",
                         hp: 100, credits: 18, status: "questing", verdict: null, spent: 0,
                         passed: 0, failed: 0, conceded: 0, revised: false, prereg: null, lastDelta: 0,
                         byLevel: {} };
    s.order.push(id);
  }
  return h;
}

function reduce(s, e) {
  if (e.level != null) s.level = e.level;
  const id = e.agent_id;
  const h = id ? hero(s, id) : null;
  if (h && e.level >= 1 && e.level <= 4) {
    const L = h.byLevel[e.level] || (h.byLevel[e.level] = { hpStart: h.hp, spent: 0, passed: 0, failed: 0, conceded: 0 });
    if (e.credits != null && e.credits < h.credits) L.spent += h.credits - e.credits;
    if (e.action === "result" && e.passed === true) L.passed += 1;
    if (e.action === "result" && e.passed === false && !(e.result && e.result.untestable)) L.failed += 1;
    if (e.action === "concede") L.conceded += 1;
  }
  if (h) {
    if (e.agent) Object.assign(h, { name: e.agent.name, cls: e.agent.cls, claim: e.agent.claim,
                                    features: e.agent.features, direction: e.agent.direction });
    if (e.credits != null) { if (e.credits < h.credits) h.spent += h.credits - e.credits; h.credits = e.credits; }
    if (e.hp != null) h.hp = e.hp;
    if (e.status) h.status = e.status;
    if (e.verdict) h.verdict = e.verdict;
  }
  switch (e.action) {
    case "quest_start":
      s.rules = e.result || null;
      s.question = (e.result && e.result.question) || "";
      s.sources = (e.result && e.result.sources) || null;
      s.levels = (e.result && e.result.levels) || {};
      s.startingCredits = (e.result && e.result.starting_credits) || 18;
      break;
    case "level_start":
      s.levelName = (e.result && e.result.name) || e.line;
      s.encounter = null;
      break;
    case "plan":
      s.skepticLine = e.line || "";
      break;
    case "encounter":
      s.encounter = { hero: id, enemy: e.enemy, ability: e.ability, test: e.test, cost: e.cost,
                      attack: e.line, action: null, result: null, passed: null, delta: null, explain: null };
      break;
    case "defend":
      if (s.encounter) s.encounter.action = { kind: "defend", line: e.line };
      break;
    case "concede":
      h.conceded += 1;
      h.lastDelta = e.hp_delta;
      if (s.encounter) Object.assign(s.encounter, { action: { kind: "concede", line: e.line },
                                                    delta: e.hp_delta, explain: e.explain });
      break;
    case "prereg":
      h.prereg = e.line;
      break;
    case "result":
      if (e.passed === true) h.passed += 1;
      if (e.passed === false && !(e.result && e.result.untestable)) h.failed += 1;
      h.lastDelta = e.hp_delta;
      if (s.encounter && s.encounter.hero === id)
        Object.assign(s.encounter, { result: e.line, passed: e.passed, delta: e.hp_delta, explain: e.explain,
                                     numbers: e.result, untestable: !!(e.result && e.result.untestable) });
      break;
    case "revise":
      h.revised = true;
      break;
    case "level_complete":
      s.levelSummaries[e.result.level] = e.result;
      break;
    case "finale":
      s.finale = e.result;
      for (const r of e.result.ranking || []) {
        const fh = hero(s, r.id);
        fh.verdict = r.verdict;
        if (fh.status === "questing") fh.status = "finished";
      }
      break;
    case "error":
      s.error = e.line;
      break;
  }
  if (e.encounter) s.records.push({ ...e.encounter, hero: h ? h.name : null, enemy_name: (ENEMIES[e.encounter.enemy_type] || {}).name,
                                    line: e.line });
  if (e.line) s.feed.unshift({ seq: e.seq, level: e.level, actor: e.actor, action: e.action, line: e.line,
                               hero: h ? h.name : null, passed: e.passed == null ? null : e.passed,
                               delta: e.hp_delta == null ? null : e.hp_delta });
  if (s.feed.length > 600) s.feed.length = 600;
  return s;
}

function standing(s) { return s.order.map((id) => s.heroes[id]).filter((h) => h.status === "questing"); }

if (typeof module !== "undefined") module.exports = { initialState, reduce, standing, ENEMIES, ABILITIES, TESTS, GOOD };
