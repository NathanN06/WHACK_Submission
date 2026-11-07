"""Level summaries, the Rule 5 composite score and the Operational Public Health Decision Brief.

Nothing here measures anything new: every number is copied from a measurement the Judge already
made and wrote to the ledger, with the encounter id that holds it.
"""

from __future__ import annotations

from collections import defaultdict

from . import judge as J
from . import rules


def biostat(a, c) -> dict:
    """The biostatMetrics block of the telemetry record: everything measured for this agent so far."""
    m1, m2, m3, m4 = (a.m.get(k, {}) for k in (1, 2, 3, 4))
    return {
        "sampleSizeN": _r(m1.get("n")), "minRequiredN": _r(m1.get("n_min")),
        "unadjustedEffect": _r(m2.get("r_xy")), "adjustedEffect": _r(m2.get("r_partial")),
        "confounderName": c.z_name, "candidateLagsSearchedK": a.K,
        "rawPValue": _r(m3.get("p_raw")), "sidakCorrectedPValue": _r(m3.get("p_corr")),
        "hindsightRmse": _r(m4.get("rmse_hindsight")), "vintageRealTimeRmse": _r(m4.get("rmse_vintage")),
        "arBaselineRmse": _r(m4.get("rmse_baseline_surge")), "outOfSampleSurgeSkill": _r(m4.get("ss_surge")),
    }


def level_row(a, level: int) -> dict:
    lost = sum(v for k, v in a.damage.items() if rules.RULE_LEVEL[rules.RULE_OF[k]] == level)
    terms = [t for t, r in rules.RULE_OF.items() if rules.RULE_LEVEL[r] == level and t in a.traps]
    return {"id": a.id, "name": a.name, "archetype": a.archetype, "hp": a.hp, "credits": a.credits,
            "hp_lost": lost, "status": a.status, "verdict": a.verdict, "abilities": a.cast.get(level, []),
            "buffs": list(a.buffs), "falsified": [rules.TRAP_LABELS[t] for t in terms if a.traps[t]],
            "sprung": [rules.TRAP_LABELS[t] for t in terms if not a.traps[t]]}


def most_damaging(agents, level: int) -> dict | None:
    by = defaultdict(int)
    for a in agents:
        for t, v in a.damage.items():
            if rules.RULE_LEVEL[rules.RULE_OF[t]] == level:
                by[t] += v
    if not by or max(by.values()) == 0:
        return None
    t = max(by, key=by.get)
    enemy = next(e for e in rules.ENEMIES[level] if e["term"] == t)
    return {"enemy": enemy["key"], "name": enemy["name"], "hp_dealt": by[t], "trap": rules.TRAP_LABELS[t]}


def damage_breakdown(agents) -> list[dict]:
    by = defaultdict(int)
    for a in agents:
        for t, v in a.damage.items():
            by[t] += v
    total = sum(by.values())
    return [{"term": t, "trap": rules.TRAP_LABELS[t], "hp_lost": v, "share": round(v / total, 3) if total else 0.0}
            for t, v in sorted(by.items(), key=lambda kv: -kv[1]) if v]


def finale(q) -> dict:
    c = q.c
    rows = []
    for a in q.agents.values():
        m4 = a.m.get(4, {})
        ss = m4.get("ss_surge") if a.archetype != "SKEPTIC" else 0.0
        faced, falsified = len(a.traps), sum(a.traps.values())
        lift = m4.get("ablation_lift_pct", 0.0) if a.archetype != "SKEPTIC" else 0.0
        score = J.composite_score(ss if a.active else None, a.hp, falsified, faced, lift, a.spent)
        if not a.active:
            verdict = "FALLEN"
        elif a.archetype == "SKEPTIC":
            verdict = "BASELINE"
        elif ss is not None and ss > 0 and m4.get("p_dm", 1.0) < rules.ALPHA:
            verdict = "VALIDATED"
        else:
            verdict = "NOT BETTER"
        a.verdict = verdict
        rows.append({
            "id": a.id, "name": a.name, "archetype": a.archetype, "claim": a.binding.claim, "status": a.status,
            "verdict": verdict, "hp": a.hp, "credits": a.credits, "spent": a.spent, "hp_by_level": a.hp_by_level,
            "traps_faced": faced, "traps_falsified": falsified, "damage": dict(a.damage), "score": score,
            "buffs": list(a.buffs), "loot": list(a.loot), "abilities": a.cast, "encounters": a.encounters,
            "streams": [{"label": c.streams[s].label, "lag": lag} for s, lag in a.spec.feats],
            "skill": {"ss_surge": _r(m4.get("ss_surge")), "p_dm": _r(m4.get("p_dm")), "lift_pct": _r(lift),
                      "surge_days": m4.get("surge_days")} if m4 else None,
            "metrics": {"faar": _r(a.m.get(1, {}).get("faar")), "rho_n": _r(a.m.get(1, {}).get("rho_n")),
                        "omega": _r(a.m.get(2, {}).get("omega")), "p_adj": _r(a.m.get(2, {}).get("p_adj")),
                        "K": a.K, "p_raw": _r(a.m.get(3, {}).get("p_raw")), "p_corr": _r(a.m.get(3, {}).get("p_corr")),
                        "g_spatial": _r(a.m.get(3, {}).get("g_spatial")), "delta_vintage": _r(m4.get("delta_vintage")),
                        "used_unreleased": m4.get("used_unreleased")},
        })
    rank = sorted(rows, key=lambda r: (r["status"] != "active", r["verdict"] != "VALIDATED", -r["score"]["total"]))
    validated = [r for r in rank if r["verdict"] == "VALIDATED"]
    champ = validated[0] if validated else None
    champion = q.agents[champ["id"]] if champ else None
    brief = decision_brief(q, champion, rows)
    headline = (f"{champion.name} emerges from the Citadel: \"{champion.binding.claim}\"" if champion else
                "Baseline Holds. No outside signal beat the AR(4) benchmark on real-time data: inconclusive.")
    return {
        "headline": headline, "campaign": {"id": c.id, "letter": c.letter, "title": c.title, "question": c.question,
                                           "target": c.target},
        "champion": champ, "baseline_holds": champ is None,
        "standing_benchmark": next((r for r in rows if r["archetype"] == "SKEPTIC" and r["status"] == "active"), None),
        "ranking": rank, "damage": damage_breakdown(q.agents.values()), "brief": brief,
        "score_rules": rules.SCORE_RULES, "score_weights": rules.SCORE_WEIGHTS, "simulated": True,
        "truth": c.truth,
        "totals": {"encounters": q._enc, "credits_spent": sum(r["spent"] for r in rows),
                   "traps_sprung": sum(r["traps_faced"] - r["traps_falsified"] for r in rows),
                   "fallen": sum(r["status"] != "active" for r in rows)},
    }


def decision_brief(q, champion, rows) -> dict:
    c = q.c
    if champion:
        m = champion.m
        streams = ", ".join(f"{c.streams[s].label} ({lag}-day lead)" for s, lag in champion.spec.feats)
        how = []
        if champion.spec.realtime:
            how.append("read it as it stands on the day (point-in-time, with the reporting delay modelled)")
        if champion.spec.include_z:
            how.append(f"keep {c.z_name.lower()} in the model")
        if champion.spec.denoise:
            how.append("subtract news-driven volume first")
        if champion.spec.ridge:
            how.append("use the shrunk (ridge) weights")
        rec = (f"Add {streams} to the {c.target.lower()} forecast, on top of the hospital-only AR(4) model"
               + (": " + "; ".join(how) if how else "") + ".")
        m4 = m[4]
        evidence = [
            _ev(f"Beat the AR(4) baseline at surge onset on {m4['surge_days']} unseen real-time days: "
                f"SS = {m4['ss_surge']:+.2f}, Diebold-Mariano p = {m4['p_dm']:.3g}.", champion.encounters.get("final")),
            _ev(f"Overall real-time error {m4['ablation_lift_pct']:.0f}% lower than the baseline (ablation lift).",
                champion.encounters.get("final")),
            _ev(f"No leakage: real-time error within {max(0.0, m4['delta_vintage']) * 100:.0f}% of hindsight.",
                champion.encounters.get("chrono")),
            _ev(f"Replicated across {len(c.regions) - 1} held-out regions: worst-case error growth G = {m[3]['g_spatial']:.2f}.",
                champion.encounters.get("g_spatial")),
            _ev(f"Survives its search: K = {champion.K}, p_raw = {m[3]['p_raw']:.2g}, Sidak p_corr = {m[3]['p_corr']:.2g}.",
                champion.encounters.get("sidak")),
        ]
        if m[2].get("applicable"):
            evidence.append(_ev(f"Not a seasonal artefact: partial r = {m[2]['r_partial']:+.2f} after adjusting for "
                                f"{c.z_name.lower()} (omega = {m[2]['omega']:.2f}).", champion.encounters.get("omega")))
        uncertainty = (f"Skill is measured on {m4['surge_days']} surge-onset days in one region's holdout; "
                       f"rural transfer is weaker (G = {m[3]['g_spatial']:.2f}). Re-check each season with fresh vintages.")
        decision = "DEPLOY AS AN EARLY-WARNING INPUT"
    else:
        best = max((r for r in rows if r["archetype"] != "SKEPTIC" and r["skill"]),
                   key=lambda r: r["skill"]["ss_surge"] or -9, default=None)
        rec = (f"Keep the hospital-only AR(4) forecast for {c.target.lower()}. No outside signal beat it on real-time "
               f"data when surges began, so the evidence for them is inconclusive.")
        evidence = []
        if best:
            evidence.append(_ev(f"Best outside signal: {best['name']} reached SS = {best['skill']['ss_surge']:+.2f} "
                                f"(Diebold-Mariano p = {best['skill']['p_dm']:.3g}), which is not a reliable gain.",
                                best["encounters"].get("final")))
        uncertainty = "A real effect too small for these data cannot be ruled out; a larger or better-measured study could still find one."
        decision = "BASELINE HOLDS: DO NOT DEPLOY"
    failed = []
    for r in rows:
        if champion and r["id"] == champion.id or r["archetype"] == "SKEPTIC":
            continue
        worst = max(r["damage"].items(), key=lambda kv: kv[1], default=None)
        if worst and worst[1] > 0:
            failed.append(_ev(f"{r['name']} ({r['claim']}): hardest hit by {rules.TRAP_LABELS[worst[0]].lower()} "
                              f"({worst[1]} HP){', and fell' if r['status'] != 'active' else ''}.",
                              r["encounters"].get(worst[0])))
    return {"decision": decision, "recommendation": rec, "evidence": evidence, "misleading": failed,
            "uncertainty": uncertainty, "truth": c.truth,
            "disclaimer": "SIMULATED CAMPAIGN: a synthetic surveillance world with planted, known effects, built to test "
                          "the Judge. These are not real public health findings."}


def _ev(text: str, cite: str | None) -> dict:
    return {"text": text, "cite": cite}


def _r(x):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return x
    return float(f"{v:.4g}") if v == v and abs(v) != float("inf") else None
