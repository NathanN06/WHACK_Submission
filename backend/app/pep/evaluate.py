"""Truth versus luck: a seeded benchmark of the WHOLE production pipeline across many independent simulated worlds.

Each world is a campaign, or a variant of one with a different planted truth, drawn with its own seed: new patients,
a new holdout and a new sealed vault. Every world runs the production path end to end: the Scribe forms the scrolls,
the hero decides from blinded telemetry, the Judge measures and applies the damage rules, the Skeptic challenges, the
Bridge locks one claim for the sealed vault, and science.py assigns every claim a status. The planted truth is read
ONLY here, after a world has finished, to score what the pipeline concluded. Nothing in a run can see it.

Metrics, each with its denominator and a Wilson 95% interval:
  familywise error in null worlds (any claim supported), false support among claims that are false, the false
  discovery proportion among supported claims, power for true claims, sign errors, coverage of the reference 95%
  interval, true claims wrongly contradicted, status rates, vault reuse blocked, and the compute spent.
`summarize()` recomputes every metric from the saved per-claim log, so the exported numbers can be checked.
"""

from __future__ import annotations

import dataclasses
import json
import math
import tempfile
import time
from pathlib import Path

from . import rules
from .campaigns import CAMPAIGNS
from .world import Outcome

SUPPORTED = ("SUPPORTED_ON_SYNTHETIC_VALIDATION", "PROVISIONALLY_SUPPORTED")
SITE_SPREAD = (-0.35, -0.15, 0.0, 0.15, 0.35)

SCENARIOS = {
    "A": {"base": "GLP1_ADDICTION", "kind": "mixed",
          "what": "a strong benefit (alcohol), a weak one (opioid) and none (smoking); confounding and immortal time"},
    "B": {"base": "BPC157_TENDON", "kind": "null", "what": "no effect anywhere; strong healthy-user confounding"},
    "C": {"base": "LONGEVITY_STACK", "kind": "null", "what": "no effect anywhere; testosterone and training confound"},
    "D": {"base": "GLP1_NAION", "kind": "mixed",
          "what": "a rare harm (NAION, 0.4% a year), a weak harm (retinopathy) and a trivial one (vision)"},
    "A_NULL": {"base": "GLP1_ADDICTION", "kind": "null", "null": True,
               "what": "campaign A with every effect removed: the same confounding and immortal time, no truth to find"},
    "A_SITES": {"base": "GLP1_ADDICTION", "kind": "mixed", "site_beta": SITE_SPREAD,
                "what": "campaign A with site heterogeneity: the drug's effect differs across the five EHR sites"},
}


def campaign_for(name: str):
    """The scenario's campaign: a pre-loaded one, or a variant with a different planted truth."""
    sc = SCENARIOS[name]
    base = CAMPAIGNS[sc["base"]]
    if not sc.get("null") and not sc.get("site_beta"):
        return base
    outcomes = [Outcome(o.key, o.label, o.base_rate, 0.0 if sc.get("null") else o.beta) for o in base.outcomes]
    return dataclasses.replace(base, id=f"{base.id}__{name}", outcomes=outcomes,
                               site_beta=tuple(sc.get("site_beta") or base.site_beta),
                               truth=f"Benchmark variant {name}: {sc['what']}.")


def planted(c, outcome: str) -> float:
    """The true log hazard ratio of an outcome, averaged over the (equally sized) sites. Read only after a run."""
    o = next(x for x in c.outcomes if x.key == outcome)
    return o.beta + sum(c.site_beta) / len(c.site_beta)


def truth_class(beta: float, direction: int) -> str:
    t = beta * direction
    if beta == 0:
        return "NULL"
    if t < 0:
        return "OPPOSITE"
    return "TRUE_IMPORTANT" if t >= -math.log(rules.MIE_RR) - 1e-12 else "TRUE_TRIVIAL"


def run_world(name: str, seed: int, n_scrolls: int = 6, hero=None, registry=None, quest_id: str | None = None) -> tuple:
    """Run one world end to end; return (claim records, world record, the quest)."""
    from ..arena.ledger import Ledger
    from .campaign import PepQuest
    from .models import QuestEvent
    from .registry import VaultRegistry
    c = campaign_for(name)
    qid = quest_id or f"eval-{name}-s{seed}"
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(qid, tmp, model=QuestEvent)
        q = PepQuest(qid, c.id, ledger, hero, seed=seed, n_scrolls=n_scrolls, campaign_obj=c,
                     registry=registry if registry is not None else VaultRegistry())
        result = q.run()
    secs = time.perf_counter() - t0
    if result is None or q.science is None:
        raise RuntimeError(f"world {name} seed {seed} did not finish")
    t = q.trial or {}
    claims = []
    for a in q.agents.values():
        s = q.science["scrolls"][a.id]
        beta = planted(c, a.st.outcome)
        ref = s["reference"]
        claims.append({"type": "claim", "world": f"{name}-s{seed}", "scenario": name, "kind": SCENARIOS[name]["kind"],
                       "seed": seed, "scroll": a.id, "archetype": a.archetype, "origin_mode": a.scroll.origin_mode,
                       "outcome": a.st.outcome, "subgroup": a.st.subgroup, "direction": a.st.direction,
                       "design": a.st.design, "planted_log_hr": round(beta, 6), "truth_class": truth_class(beta, a.st.direction),
                       "status": s["status"], "holm_p": s["holm_p"], "guardian_p": s["guardian_p"],
                       "ref_beta": ref["beta"], "ref_lo": ref["beta_lo"], "ref_hi": ref["beta_hi"], "ref_method": ref["method"],
                       "covered": bool(ref["beta_lo"] <= beta <= ref["beta_hi"]), "game_verdict": a.verdict,
                       "trial_outcome": s["trial_outcome"], "vault_kind": s["confirmation_kind"]})
    world = {"type": "world", "world": f"{name}-s{seed}", "scenario": name, "kind": SCENARIOS[name]["kind"], "seed": seed,
             "fingerprint": q.w.fingerprint(), "claims": len(claims), "encounters": q._enc,
             "credits_spent": sum(a.spent for a in q.agents.values()), "seconds": round(secs, 3),
             "api_calls": getattr(getattr(q.brain, "complete", None), "calls", 0),
             "trial_outcome": t.get("outcome"), "trial_scroll": t.get("scroll"), "vault_kind": t.get("vault_kind")}
    return claims, world, q


def reuse_check(name: str, seed: int, n_scrolls: int = 6) -> dict:
    """Run the same world twice on one vault registry: the second Trial must never count as a new confirmation."""
    from .registry import VaultRegistry
    reg = VaultRegistry()
    _, first, _ = run_world(name, seed, n_scrolls, registry=reg, quest_id=f"eval-{name}-s{seed}-1")
    _, second, _ = run_world(name, seed, n_scrolls, registry=reg, quest_id=f"eval-{name}-s{seed}-2")
    return {"type": "reuse", "world": f"{name}-s{seed}", "scenario": name, "first": first["trial_outcome"],
            "first_kind": first["vault_kind"], "second": second["trial_outcome"], "second_kind": second["vault_kind"],
            "blocked": second["trial_outcome"] != "VALIDATED DISCOVERY" and second["vault_kind"] in ("REPLAY", "REUSE", None)}


# ---------------------------------------------------------------- metrics

def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "lo": None, "hi": None}
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"k": k, "n": n, "rate": round(p, 4), "lo": round(max(0.0, mid - half), 4), "hi": round(min(1.0, mid + half), 4)}


def summarize(records: list[dict]) -> dict:
    """Every exported metric, recomputed from the saved records alone (the scripted runs; live runs are compared apart)."""
    records = [r for r in records if r.get("mode", "scripted") == "scripted"]
    claims = [r for r in records if r["type"] == "claim"]
    worlds = [r for r in records if r["type"] == "world"]
    reuse = [r for r in records if r["type"] == "reuse"]
    by_world: dict[str, list] = {}
    for r in claims:
        by_world.setdefault(r["world"], []).append(r)
    sup = lambda r: r["status"] in SUPPORTED   # noqa: E731
    false_claim = lambda r: r["truth_class"] in ("NULL", "OPPOSITE")   # noqa: E731
    null_worlds = [w for w in worlds if w["kind"] == "null"]
    true_imp = [r for r in claims if r["truth_class"] == "TRUE_IMPORTANT"]
    valid = [r for r in true_imp if r["design"] == "new_user"]
    statuses = {}
    for cls in ("TRUE_IMPORTANT", "TRUE_TRIVIAL", "NULL", "OPPOSITE"):
        rows = [r for r in claims if r["truth_class"] == cls]
        statuses[cls] = {s: wilson(sum(r["status"] == s for r in rows), len(rows)) for s in rules.STATUS_ORDER}
    power_by = {}
    for r in true_imp:
        power_by.setdefault(f"{r['scenario']}:{r['outcome']}", []).append(r)
    supported = [r for r in claims if sup(r)]
    # claims that share an estimand in one world share one interval: coverage is counted once per (world, estimand)
    units: dict = {}
    for r in claims:
        units.setdefault((r["world"], r["scenario"], r["outcome"], r["subgroup"]), r["covered"])
    cover_by: dict = {}
    for (_, sc, _, _), ok in units.items():
        cover_by.setdefault(sc, []).append(ok)
    return {
        "worlds": {"total": len(worlds), "null": len(null_worlds), "with_true_effects": len(worlds) - len(null_worlds)},
        "claims": len(claims),
        "familywise_error_null_worlds": wilson(sum(any(sup(r) for r in by_world[w["world"]]) for w in null_worlds),
                                               len(null_worlds)),
        "false_confirmation_null_worlds": wilson(sum(w["trial_outcome"] == "VALIDATED DISCOVERY" for w in null_worlds),
                                                 len(null_worlds)),
        "false_support_rate": wilson(sum(sup(r) for r in claims if false_claim(r)), sum(false_claim(r) for r in claims)),
        "false_discovery_proportion": wilson(sum(false_claim(r) for r in supported), len(supported)),
        "trivial_among_supported": wilson(sum(r["truth_class"] == "TRUE_TRIVIAL" for r in supported), len(supported)),
        "sign_errors": sum(sup(r) and r["truth_class"] == "OPPOSITE" for r in claims),
        "power_true_claims_valid_design": wilson(sum(sup(r) for r in valid), len(valid)),
        "power_true_claims_any_design": wilson(sum(sup(r) for r in true_imp), len(true_imp)),
        "power_by_estimand_valid_design": {k: wilson(sum(sup(r) for r in v if r["design"] == "new_user"),
                                                     sum(r["design"] == "new_user" for r in v))
                                           for k, v in sorted(power_by.items())},
        "true_claims_wrongly_contradicted": wilson(sum(r["status"] == "CONTRADICTED" for r in true_imp), len(true_imp)),
        "reference_ci_coverage": wilson(sum(units.values()), len(units)),
        "reference_ci_coverage_by_scenario": {k: wilson(sum(v), len(v)) for k, v in sorted(cover_by.items())},
        "status_by_truth": statuses,
        "status_rates": {s: wilson(sum(r["status"] == s for r in claims), len(claims)) for s in rules.STATUS_ORDER},
        "vault_reuse_blocked": wilson(sum(r["blocked"] for r in reuse), len(reuse)),
        "compute": {"encounters_mean": round(sum(w["encounters"] for w in worlds) / max(1, len(worlds)), 2),
                    "credits_spent_mean": round(sum(w["credits_spent"] for w in worlds) / max(1, len(worlds)), 2),
                    "seconds_mean": round(sum(w["seconds"] for w in worlds) / max(1, len(worlds)), 3),
                    "api_calls": sum(w.get("api_calls", 0) for w in worlds)},
    }


def examples(records: list[dict]) -> dict:
    """A false discovery defeated beside a true discovery that survived, with the planted truth revealed (post-run)."""
    claims = [r for r in records if r["type"] == "claim"]
    false_def = next((r for r in claims if r["truth_class"] in ("NULL", "OPPOSITE") and r["status"] != "PROVISIONALLY_SUPPORTED"
                      and r["status"] != "SUPPORTED_ON_SYNTHETIC_VALIDATION" and r["archetype"] == "HYPE"), None)
    true_surv = next((r for r in claims if r["truth_class"] == "TRUE_IMPORTANT"
                      and r["status"] == "SUPPORTED_ON_SYNTHETIC_VALIDATION"), None)
    keep = ("world", "scroll", "archetype", "outcome", "subgroup", "direction", "planted_log_hr", "status", "game_verdict")
    return {"false_discovery_defeated": {k: false_def[k] for k in keep} if false_def else None,
            "true_discovery_survived": {k: true_surv[k] for k in keep} if true_surv else None}


def paired_live(scripted_records: list[dict], live_records: list[dict]) -> dict:
    """Matched-seed comparison of the live hero against the scripted one: per world, true supports minus false ones."""
    def score(recs):
        out = {}
        for r in recs:
            if r["type"] == "claim":
                d = out.setdefault(r["world"], 0)
                if r["status"] in SUPPORTED:
                    out[r["world"]] = d + (1 if r["truth_class"] == "TRUE_IMPORTANT" else -1 if r["truth_class"] in ("NULL", "OPPOSITE") else 0)
        return out
    a, b = score(scripted_records), score(live_records)
    diffs = [b[k] - a[k] for k in a if k in b]
    if len(diffs) < 2:
        return {"status": "INSUFFICIENT", "pairs": len(diffs)}
    mean = sum(diffs) / len(diffs)
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1))
    half = 1.96 * sd / math.sqrt(len(diffs))
    return {"status": "RUN", "pairs": len(diffs), "mean_difference_live_minus_scripted": round(mean, 4),
            "ci95": [round(mean - half, 4), round(mean + half, 4)],
            "score": "per world: true important claims supported minus false claims supported"}


def run(seeds: list[int], scenarios: list[str] | None = None, n_scrolls: int = 6, reuse_seeds: int = 2,
        live_hero=None, out_dir: Path | None = None, log=print) -> dict:
    """The benchmark. Writes runs.jsonl (every claim, world and reuse record) and evaluation_summary.json."""
    scenarios = scenarios or list(SCENARIOS)
    records, live_records = [], []
    for name in scenarios:
        for seed in seeds:
            claims, world, _ = run_world(name, seed, n_scrolls)
            records += [{**r, "mode": "scripted"} for r in claims + [world]]
            if live_hero is not None:
                lc, lw, _ = run_world(name, seed, n_scrolls, hero=live_hero, quest_id=f"eval-{name}-s{seed}-live")
                live_records += [{**r, "mode": "live"} for r in lc + [lw]]
            if log:
                sup = [f"{c['scroll']}:{c['status'][:4]}/{c['truth_class'][:4]}" for c in claims if c["status"] in SUPPORTED]
                log(f"  {name:8} seed {seed:4}: {world['seconds']:.1f}s, trial {world['trial_outcome']}, supported {sup or 'none'}")
        for seed in seeds[:reuse_seeds]:
            records.append({**reuse_check(name, seed, n_scrolls), "mode": "scripted"})
    summary = {
        "title": "Hypothesis Gauntlet: truth-versus-luck benchmark",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "analysis_version": rules.ANALYSIS_VERSION,
        "methodology": [
            "Every world is an independent synthetic cohort (its own seed): new patients, holdout and sealed vault.",
            "Each world runs the production pipeline end to end: scripted Scribe (deterministic) forming "
            f"{n_scrolls} claims, the hero deciding from blinded telemetry, the Judge, the Skeptic, the Bridge's autopilot "
            "choice and the Trial of Truth, then science.py's statuses.",
            "The planted truth is read only after a world has finished, to score it.",
            "A claim is TRUE_IMPORTANT when its planted effect points the claimed way by at least the minimal important "
            f"effect (rate ratio {rules.MIE_RR}), TRUE_TRIVIAL when it points that way by less, NULL with no effect, "
            "OPPOSITE when it points the other way. Supported = PROVISIONALLY_SUPPORTED or SUPPORTED_ON_SYNTHETIC_VALIDATION.",
            "Rates carry Wilson 95% intervals over the stated denominators. Claims that share an estimand in one world "
            "share one reference interval, so coverage is counted once per world and estimand.",
            "The reference interval assumes one effect across sites unless Cochran's Q flags disagreement "
            f"(p < {rules.HETEROGENEITY_ALPHA}); then it pools the sites with DerSimonian-Laird random effects.",
        ],
        "seeds": seeds, "scenarios": {k: {**SCENARIOS[k], "site_beta": list(SCENARIOS[k].get("site_beta") or [])}
                                      for k in scenarios},
        "metrics": summarize(records), "examples": examples(records),
        "live_vs_scripted": (paired_live(records, live_records) if live_hero is not None else
                             {"status": "PENDING", "reason": "No live Claude run was made (no API key, or --live not "
                                                             "given). No gain from AI is claimed."}),
        "limitations": [
            "All cohorts are simulated from one family of data-generating models (exponential event times, log-linear "
            "confounding); real data can break assumptions this benchmark never tests.",
            "Missing data, informative censoring, unmeasured confounding and effect modification by subgroup are not "
            "simulated, so the benchmark says nothing about them.",
            "The hand-written HYPE and PREPRINT scrolls follow fixed sloppy plans by design, so they are INVALID by "
            "construction; power is reported separately for claims analysed on a valid (time-zero) design.",
            "Only the scripted hero is benchmarked unless a live run is recorded above.",
        ],
        "logs": "runs.jsonl",
    }
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "runs.jsonl", "w", encoding="utf-8") as f:
            for r in records + live_records:
                f.write(json.dumps(r) + "\n")
        (out_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
