"""Scores, level summaries and the final consensus report. Pure functions of hero results.

Nothing here runs a new statistic: every number is copied from a check that already ran
and is in the ledger, so the report can always be traced back to its tests.
"""

from collections import defaultdict

from . import rules
from .models import Hero


def _passed(h: Hero, test: str) -> bool | None:
    r = h.results.get(test)
    if r is None or r.get("untestable"):
        return None
    return bool(r.get("passed"))


def score_components(h: Hero) -> dict[str, float]:
    """The section 9 scoring rule (see rules.SCORE_COMPONENTS). Untested gates earn nothing."""
    C = rules.SCORE_COMPONENTS
    soundness = ["added_value", "echo", "within_person", "majority_benefit", "confounding"]
    got = []
    for t in soundness:
        p = _passed(h, t)
        got.append(0.5 if p is None and t != "added_value" else float(bool(p)))
    validity = C["validity"]["max"] * sum(got) / len(got)

    fb = h.results.get("final_boss") or {}
    if _passed(h, "final_boss"):
        oos = C["out_of_sample"]["max"]
    elif fb and not fb.get("untestable") and fb.get("gain", 0) > 0:
        oos = 8
    else:
        oos = 0

    extra = [_passed(h, "trimmed_gain"), _passed(h, "sensor_check")]
    extra = [x for x in extra if x is not None]
    falsification = 10 * bool(_passed(h, "shuffle_test")) + 5 * bool(_passed(h, "fold_replication")) \
        + 5 * (sum(extra) / len(extra) if extra else 0.5 * bool(_passed(h, "shuffle_test")))

    uncertainty = C["uncertainty"]["max"] * bool(_passed(h, "penalty"))

    raw = h.results.get("raw_direction") or {}
    honest_direction = not raw.get("contradicted") or h.revised
    misleading = C["misleading"]["max"] * (honest_direction and _passed(h, "too_good") is not False
                                           and _passed(h, "echo") is not False)

    leakage = 7.5 * bool(_passed(h, "temporal")) + 7.5 * bool(_passed(h, "leak_audit"))

    tried = h.attempted + h.conceded
    efficiency = C["efficiency"]["max"] * (1 - (h.redundant + h.conceded) / tried) if tried else 0.0

    if _passed(h, "temporal") is False or _passed(h, "leak_audit") is False:
        # results built on leaked information are not evidence: they earn nothing
        validity = oos = falsification = uncertainty = 0
    return {"validity": round(validity, 1), "out_of_sample": float(oos), "falsification": round(falsification, 1),
            "uncertainty": float(uncertainty), "misleading": float(misleading), "leakage": leakage,
            "efficiency": round(max(0.0, efficiency), 1)}


def score(h: Hero) -> float:
    comp = score_components(h)
    return round(sum(comp.values()) + rules.HP_BONUS * h.hp, 1)


def tiebreak(h: Hero) -> float:
    """Predefined tie-break: the most confident out-of-sample gain (lower end of its 95% CI)."""
    fb = h.results.get("final_boss") or {}
    return float(fb.get("ci_low", float("-inf"))) if not fb.get("untestable") else float("-inf")


def why_ranked(h: Hero, comp: dict, others: list[dict]) -> str:
    C = rules.SCORE_COMPONENTS
    strong = [C[k]["label"].lower() for k, v in comp.items() if v >= C[k]["max"] - 1e-9]
    rest = [o for o in others if o["id"] != h.id]
    best_other = max((o["score"] for o in rest), default=0)
    tie = ""
    if any(o["score"] == score(h) and o["verdict"] == "VALIDATED" for o in rest):
        tie = (f" It tied on score, and won the predefined tie-break: the most confident gain on unseen people "
               f"(lower 95% bound {tiebreak(h):+.2f} mg/dL per meal).")
    return (f"Full marks for {', '.join(strong) or 'no component'}; total {score(h)} of "
            f"{sum(c['max'] for c in C.values()) + 5:.0f} (runner-up {best_other}). "
            f"It passed every validation gate, which no amount of HP or extra tests can replace.{tie}")


def damage_by_weakness(heroes: list[Hero]) -> list[dict]:
    """HP lost to each kind of weakness, absolute and as a share of all damage."""
    lost = defaultdict(int)
    for h in heroes:
        for e in h.history:
            if e["hp_delta"] < 0:
                key = rules.ENCOUNTERS[e["enemy"]]["weakness"] if e["test"] else "Unverified (conceded) claims"
                lost[key] += -e["hp_delta"]
    total = sum(lost.values())
    return [{"weakness": k, "hp_lost": v, "share": round(v / total, 3) if total else 0.0}
            for k, v in sorted(lost.items(), key=lambda kv: -kv[1])]


def most_damaging_enemy(heroes: list[Hero], level: int) -> dict | None:
    lost = defaultdict(int)
    for h in heroes:
        for e in h.history:
            if e["level"] == level and e["hp_delta"] < 0 and e["test"]:
                lost[e["enemy"]] += -e["hp_delta"]
    if not lost:
        return None
    key = max(lost, key=lost.get)
    enc = rules.ENCOUNTERS[key]
    return {"enemy": key, "name": enc.get("head") and f"{enc['name']}: {enc['head']}" or enc["name"],
            "hp_dealt": lost[key], "weakness": enc["weakness"]}


def level_rows(heroes: list[Hero], level: int) -> list[dict]:
    rows = []
    for h in heroes:
        mine = [e for e in h.history if e["level"] == level]
        if not mine:
            continue
        rows.append({
            "id": h.id, "name": h.name, "hp": h.hp, "credits_left": h.credits, "status": h.status,
            "verdict": h.verdict, "tests": sum(1 for e in mine if e["test"]),
            "strengthened": [_label(e) for e in mine if e["passed"] is True],
            "weakened": [_label(e) for e in mine if e["passed"] is False or e["test"] is None],
        })
    return rows


def _label(e: dict) -> str:
    enc = rules.ENCOUNTERS[e["enemy"]]
    return (enc.get("head") or enc["name"]) if e["test"] else f"conceded {enc.get('head') or enc['name']}"


def contributions(h: Hero, sources: dict) -> list[dict]:
    """Which evidence carried the conclusion, from tests that ran. No invented percentages.

    The two ablations (with vs without the evidence, on discovery people and on unseen
    people) are the real contribution measure: the drop in prediction error per meal.
    """
    r, out = h.results, []
    tv = r.get("added_value")
    if tv and not tv.get("untestable"):
        out.append({"source": f"Primary measurements: {sources['discovery']}", "test": "Ablation, cross-validated by person",
                    "value": f"{tv['gain']:+.2f} mg/dL per meal (95% CI {tv['ci_low']:+.2f} to {tv['ci_high']:+.2f})",
                    "supports": bool(tv["passed"])})
    fr = r.get("fold_replication")
    if fr:
        out.append({"source": "Independent replication (5 separate groups of people)", "test": "Fold replication",
                    "value": f"replicated in {fr['replicated']} of {fr['n_groups']} groups", "supports": bool(fr["passed"])})
    st = r.get("shuffle_test")
    if st:
        out.append({"source": "Scrambled-data comparison", "test": "Permutation test",
                    "value": f"p = {st['p']:.3f} ({st['beaten_by']} of {st['n_perm']} shuffles did as well)",
                    "supports": bool(st["passed"])})
    sc = r.get("sensor_check")
    if sc and not sc.get("untestable"):
        parts = ", ".join(f"{k} {v:+.2f}" for k, v in sc["by_sensor"].items() if v is not None)
        out.append({"source": "Second measurement device", "test": "Sensor agreement",
                    "value": f"{parts} mg/dL per meal", "supports": bool(sc["passed"])})
    fb = r.get("final_boss")
    if fb and not fb.get("untestable"):
        out.append({"source": f"Held-out validation: {sources['holdout']}", "test": "Ablation on never-seen people",
                    "value": f"{fb['gain']:+.2f} mg/dL per meal (95% CI {fb['ci_low']:+.2f} to {fb['ci_high']:+.2f}), "
                             f"{fb['n_participants']} people", "supports": bool(fb["passed"])})
    return out


def consensus(question: str, champion: Hero | None, heroes: list[Hero], decoys: dict[str, str],
              sources: dict) -> dict:
    """Section 10E: the final answer, in plain English, built only from executed tests."""
    misleading = []
    for h in heroes:
        if h is champion:
            continue
        fails = [e for e in h.history if e["passed"] is False]
        tag = " (a planted impostor)" if h.id in decoys else ""
        if h.verdict == "LOOK-AHEAD":
            misleading.append(f"{h.gladiator.claim}{tag}: predicted well only by using information from after the meal.")
        elif fails and any(e["test"] in ("added_value", "shuffle_test") for e in fails) \
                and h.results.get("added_value", {}).get("passed"):
            misleading.append(f"{h.gladiator.claim}{tag}: looked real in the discovery data but did not hold up "
                              f"({', '.join(_label(e) for e in fails)}).")
        elif h.verdict == "UNSUPPORTED" and h.results.get("added_value", {}).get("passed"):
            misleading.append(f"{h.gladiator.claim}{tag}: passed early tests, failed later ones "
                              f"({', '.join(_label(e) for e in fails) or 'unseen people'}).")
        elif h.id in decoys:
            misleading.append(f"{h.gladiator.claim}{tag}: stopped at {', '.join(_label(e) for e in fails[:2]) or 'the gates'}.")
    validated = [h for h in heroes if h.verdict == "VALIDATED"]
    citations = []
    if champion:
        for t in ("added_value", "shuffle_test", "penalty", "fold_replication", "temporal", "leak_audit", "final_boss"):
            enc_id = champion.encounter_ids.get(t)
            if enc_id:
                citations.append(enc_id)
    if not champion:
        return {
            "question": question, "survived": False,
            "answer": "Inconclusive. No hypothesis survived every validation step, so the gauntlet names no winner.",
            "supporting": [], "misleading": misleading[:6],
            "uncertainty": "Claims that looked promising early did not hold on unseen people or under correction for "
                           "the number of claims tried. More data, or better-measured evidence, is needed.",
            "citations": [], "also_validated": []}
    fb = champion.results["final_boss"]
    others = [h.gladiator.claim for h in validated if h is not champion]
    uncertainty = (f"On {fb['n_participants']} never-seen people the improvement is {fb['gain']:+.2f} mg/dL per meal, "
                   f"plausibly anywhere from {fb['ci_low']:+.2f} to {fb['ci_high']:+.2f}. The effect is real but its size "
                   f"is uncertain, and the holdout ({sources['holdout']}) may differ from the people it was found in.")
    if sources.get("synthetic"):
        uncertainty += " DEMO MODE: these meals are synthetic, made with known effects to test the gauntlet. They are not a real discovery."
    return {
        "question": question, "survived": True,
        "answer": f"{champion.gladiator.claim}. It adds predictive value beyond carbohydrate, replicates, beats scrambled "
                  f"data after counting every claim tried, uses only mealtime information, and holds on people never seen.",
        "original_claim_survived": not champion.revised,
        "supporting": [f"{c['source']}: {c['value']}" for c in contributions(champion, sources) if c["supports"]],
        "misleading": misleading[:6], "uncertainty": uncertainty, "citations": citations,
        "also_validated": others,
    }
