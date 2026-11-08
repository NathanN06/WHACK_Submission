"""Level summaries, the composite score and the Research Decision Brief of the Peptide & GLP-1 edition.

Nothing here measures anything new: every number is copied from a measurement the Judge already
made and wrote to the ledger, with the encounter id that holds it.
"""

from __future__ import annotations

import math
from collections import defaultdict

from . import judge as J
from . import rules
from .campaigns import ARCHETYPES

DISCLAIMER = ("SIMULATED CAMPAIGN: a synthetic world (EHR cohort, social posts, papers and trial registry) with planted, "
              "known effects, built to test the Judge. These are not real findings and not medical advice.")


def biostat(a) -> dict:
    """The biostatMetrics block of the telemetry record: everything measured for this scroll so far."""
    m1, m2, m3, m4 = (a.m.get(k, {}) for k in (1, 2, 3, 4))
    nv, ad = m2.get("naive") or {}, m2.get("adjusted") or {}
    return {
        "affiliateSkew": _r(m1.get("phi")), "effectiveSources": m1.get("n_eff"),
        "rodentShare": _r(m2.get("tau")), "naiveRateRatio": _r(nv.get("rr")), "adjustedRateRatio": _r(ad.get("rr")),
        "confoundingShift": _r(m2.get("shift")), "testsSearchedK": a.st.K, "rawPValue": _r(m3.get("p_raw")),
        "sidakCorrectedPValue": _r(m3.get("p_corr")), "labConcentration": _r(m3.get("h_lab")),
        "completedHumanRcts": m3.get("n_rct"), "immortalTimeShare": _r(m4.get("immortal_share")),
        "purgeShift": _r(m4.get("delta_purge")), "outOfSampleSkill": _r(m4.get("ss_oos")),
        "pairedLossPValue": _r(m4.get("p_dm")), "design": a.st.design,
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
        ss = m4.get("ss_oos")
        faced, falsified = len(a.traps), sum(a.traps.values())
        lift = m4.get("lift_pct", 0.0) or 0.0
        score = J.composite_score(ss if a.active else None, a.hp, falsified, faced, lift, a.spent)
        if not a.active:
            verdict = "SHATTERED"
        elif a.eureka:
            verdict = "VALIDATED"
        else:
            verdict = "NOT BETTER"
        a.verdict = verdict
        o = next(x for x in c.outcomes if x.key == a.st.outcome)
        m2, m3 = a.m.get(2, {}), a.m.get(3, {})
        rows.append({
            "id": a.id, "name": a.name, "archetype": a.archetype, "title": ARCHETYPES[a.archetype]["title"],
            "claim": a.claim, "outcome": o.label, "status": a.status, "verdict": verdict, "hp": a.hp,
            "credits": a.credits, "spent": a.spent, "hp_by_level": a.hp_by_level, "traps_faced": faced,
            "traps_falsified": falsified, "damage": dict(a.damage), "score": score, "buffs": list(a.buffs),
            "abilities": a.cast, "encounters": a.encounters, "design": a.st.design, "K": a.st.K,
            "skill": {"ss_oos": _r(ss), "p_dm": _r(m4.get("p_dm")), "lift_pct": _r(lift),
                      "matched_pairs": m4.get("matched_pairs"), "rr_used": _r(math.exp(m4["beta_used"]))} if m4 else None,
            "metrics": {"phi": _r(a.m.get(1, {}).get("phi")), "n_eff": a.m.get(1, {}).get("n_eff"),
                        "tau": _r(m2.get("tau")), "rr_naive": _r((m2.get("naive") or {}).get("rr")),
                        "rr_adjusted": _r((m2.get("adjusted") or {}).get("rr")), "shift": _r(m2.get("shift")),
                        "K": m3.get("K"), "p_raw": _r(m3.get("p_raw")), "p_corr": _r(m3.get("p_corr")),
                        "h_lab": _r(m3.get("h_lab")), "n_rct": m3.get("n_rct"),
                        "replicating": len(m3.get("replicating", [])),
                        "immortal_share": _r(m4.get("immortal_share")), "delta_purge": _r(m4.get("delta_purge")),
                        "rr_current": _r(m4.get("rr_current")), "rr_purged": _r(m4.get("rr_purged"))},
        })
    rank = sorted(rows, key=lambda r: (r["status"] != "active", r["verdict"] != "VALIDATED", -r["score"]["total"]))
    validated = [r for r in rank if r["verdict"] == "VALIDATED"]
    champ = validated[0] if validated else None
    champion = q.agents[champ["id"]] if champ else None
    gate = ARCHETYPES["SKEPTIC"]
    benchmark = {"id": "gatekeeper", "name": gate["nickname"], "archetype": "SKEPTIC", "title": gate["title"],
                 "claim": f"{c.comparator}: no drug effect at all.", "verdict": "BASELINE", "status": "active",
                 "skill": {"ss_oos": 0.0}, "score": None}
    brief = decision_brief(q, champion, rows)
    if champion:
        headline = f"The Alchemist emerges from the Citadel with {champion.name}: \"{champion.claim}\""
    else:
        headline = (f"Baseline Holds. No scroll predicted unseen patients better than {_comp(c)} "
                    "with no drug effect: inconclusive.")
    return {
        "headline": headline, "campaign": {"id": c.id, "letter": c.letter, "title": c.title, "question": c.question,
                                           "drug": c.drug, "comparator": c.comparator},
        "champion": champ, "baseline_holds": champ is None, "benchmark": benchmark,
        "ranking": rank, "damage": damage_breakdown(q.agents.values()), "brief": brief,
        "score_rules": rules.SCORE_RULES, "score_weights": rules.SCORE_WEIGHTS, "simulated": True,
        "truth": c.truth,
        "totals": {"encounters": q._enc, "credits_spent": sum(r["spent"] for r in rows),
                   "traps_sprung": sum(r["traps_faced"] - r["traps_falsified"] for r in rows),
                   "shattered": sum(r["status"] != "active" for r in rows)},
    }


def decision_brief(q, champion, rows) -> dict:
    c = q.c
    harm = c.effect_direction > 0
    if champion:
        m, st = champion.m, champion.st
        m2, m3, m4 = m[2], m[3], m[4]
        o = next(x for x in c.outcomes if x.key == st.outcome)
        rr = math.exp(m4["beta_used"])
        if harm:
            decision = "SAFETY SIGNAL CONFIRMED: WARN AND MONITOR"
            rec = (f"Treat the rise in {_lower(o.label)} with {_lower(c.drug)} as a real safety signal against "
                   f"{_comp(c)}: update prescriber guidance and monitor it prospectively.")
        else:
            decision = "PRIORITISE A CONFIRMATORY RANDOMISED TRIAL"
            rec = (f"Prioritise a randomised trial of {_lower(c.drug)} against {_comp(c)} for "
                   f"{_lower(o.label)}. The observational signal survived every trap, but it is still observational.")
        dmg = champion.damage

        def hit(key):
            n = dmg.get(key, 0)
            return f" It lost {n} HP here." if n else ""

        caveats = []
        if st.design == "new_user":
            design = f"New-user, time-zero design: rate ratio {m4['rr_current']:.2f} with no immortal time."
        else:
            caveats.append("immortal time")
            design = (f"Not time-zero aligned: exposure was counted for anyone who ever filled a prescription "
                      f"({m4['immortal_share']:.0%} immortal time). Rate ratio {m4['rr_current']:.2f} as carried, "
                      f"{m4['rr_purged']:.2f} with a new-user design.")
        if st.adjusted:
            confound = (f"Adjusted for measured confounders: rate ratio {m2['naive']['rr']:.2f} naive, "
                        f"{m2['adjusted']['rr']:.2f} adjusted.")
        else:
            caveats.append("confounding")
            confound = (f"Not adjusted for measured confounders: rate ratio {m2['naive']['rr']:.2f} as carried; "
                        f"adjusting would give {m2['adjusted']['rr']:.2f}.")
        if m3["p_corr"] < rules.ALPHA:
            search = f"Survives its search: K = {m3['K']}, p_raw = {m3['p_raw']:.2g}, Sidak p_corr = {m3['p_corr']:.2g}."
        else:
            caveats.append("multiple testing")
            search = (f"Does not survive its search: K = {m3['K']}, p_raw = {m3['p_raw']:.2g}, Sidak p_corr = "
                      f"{m3['p_corr']:.2g} (needs < {rules.ALPHA}).")
        if caveats:
            rec += (" Caveats: it did not guard against " + ", ".join(caveats)
                    + ", so confirm those before acting.")
            rec = rec.replace("The observational signal survived every trap, but it is still observational.",
                              "It won at the Guardian, but not every trap was cleared, and it is still observational.")
        evidence = [
            _ev(f"Predicted {m4['matched_pairs']} matched pairs of unseen holdout patients better than the comparator: "
                f"SS = {m4['ss_oos']:+.4f}, paired loss test p = {m4['p_dm']:.3g}.", champion.encounters.get("final")),
            _ev(design + hit("chrono"), champion.encounters.get("chrono")),
            _ev(confound + hit("confound"), champion.encounters.get("confound")),
            _ev(search + hit("sidak"), champion.encounters.get("sidak")),
            _ev(f"Replicated in {len(m3['replicating'])} of {len(m3['sites'])} EHR sites; lab concentration "
                f"H = {m3['h_lab']:.2f}." + hit("hlab"), champion.encounters.get("hlab")),
        ]
        uncertainty = (f"The rate ratio used was {rr:.2f}, from one simulated network. Unmeasured confounding cannot be "
                       f"ruled out, and {'no' if m3['n_rct'] == 0 else m3['n_rct']} completed human RCT"
                       f"{'' if m3['n_rct'] == 1 else 's'} back{'s' if m3['n_rct'] == 1 else ''} it. "
                       "A second vaulted partition is kept untouched for a later validation run.")
    else:
        best = max((r for r in rows if r["skill"] and r["status"] == "active"),
                   key=lambda r: r["skill"]["ss_oos"] if r["skill"]["ss_oos"] is not None else -9, default=None)
        decision = "BASELINE HOLDS: NOT SUPPORTED"
        rec = (f"Do not act on these claims. No scroll predicted unseen patients better than {_comp(c)} "
               f"with no drug effect, so the evidence for {_lower(c.drug)} is inconclusive.")
        evidence = []
        if best:
            evidence.append(_ev(f"Best surviving scroll: {best['name']} reached SS = {best['skill']['ss_oos']:+.4f} "
                                f"(paired loss test p = {best['skill']['p_dm']:.3g}), which is not a reliable gain.",
                                best["encounters"].get("final")))
        uncertainty = ("A real effect too small for this cohort cannot be ruled out; a larger cohort or a randomised trial "
                       "could still find one.")
    failed = []
    for r in rows:
        if champion and r["id"] == champion.id:
            continue
        worst = max(r["damage"].items(), key=lambda kv: kv[1], default=None)
        if worst and worst[1] > 0:
            failed.append(_ev(f"{r['name']} (\"{r['claim']}\"): hardest hit by {_lower(rules.TRAP_LABELS[worst[0]])} "
                              f"({worst[1]} HP){', and shattered' if r['status'] != 'active' else ''}.",
                              r["encounters"].get(worst[0])))
    return {"decision": decision, "recommendation": rec, "evidence": evidence, "misleading": failed,
            "uncertainty": uncertainty, "truth": c.truth, "disclaimer": DISCLAIMER}


def _comp(c) -> str:
    """The comparator in running text, without its "(active comparator)" tag."""
    return _lower(c.comparator.split(" (")[0])


def _lower(s: str) -> str:
    """Lower-case the first letter unless the word looks like an acronym or a drug code (GLP-1, BPC-157)."""
    head = s.split(" ")[0]
    return s if head[:2].isupper() or any(ch.isdigit() for ch in head) else s[0].lower() + s[1:]


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
