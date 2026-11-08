"""The endgame: the Bridge of Judgment, the Researcher's Dilemma, the Evolution Trial and the Trial of Truth.

After the fourth dungeon the hero does not walk straight out. It stands before the Bridge of Judgment and
reviews its whole research history (ResearcherSelfAssessment). A fixed policy (EvolutionDecisionEngine) turns
that review into one recommendation: CROSS, EVOLVE or INCONCLUSIVE. The Research Director chooses; the hero
designs the experiments; nobody overrides the Judge.

The Trial of Truth locks the claim (a hashed specification), then opens the second vault (index days >= 1450)
for the first and only time. No level, Mystery Boss or Evolution step ever reads it. The outcome depends on
methodological validity and on whether the confidence the hero asserted was justified, not on HP.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

from . import challenges as C
from . import judge as J
from . import rules
from .registry import confirmation_label
from .world import HOLDOUT_END

CHOICES = ("cross", "evolve", "inconclusive")
# What Researcher V2 may still fix after seeing results. Preregistration is not among them: once Level III's search has
# run on this cohort, locking one outcome would be retroactive, so a search weakness has no fix here.
FIX_FOR_FALLEN = {"confounder": "BIAS_DETECTION", "chronolock": "TEMPORAL_GUARD"}


# ---------- the whole endgame ----------

def endgame(q) -> dict:
    d = q.director
    q.level = 5
    q.vault2_n = int((q.w.split == "vault2").sum())   # a count of patients, not a look at their outcomes
    q._emit(actor="system", action="bridge_enter", line="The Bridge of Judgment: a narrow span over the abyss, a golden portal beyond.",
            explain="Before crossing, the hero reviews everything it found, everything that failed and every challenge still open.",
            result={"vault2_patients": q.vault2_n, "vault2_from_day": HOLDOUT_END})
    while True:
        with q.lock:
            A = assess(q)
            q._emit(actor="system", action="self_assessment", line=f"The hero speaks: \"{A['speech']}\"",
                    explain=A["recommendation"]["why"], result={"assessment": A})
        pick = d.wait_choice(A) if d is not None else {"choice": A["recommendation"]["choice"], "by": "autopilot"}
        choice = pick["choice"]
        with q.lock:
            q._emit(actor="director" if pick["by"] == "director" else "system", action="bridge_choice",
                    line=f"{'The Research Director' if pick['by'] == 'director' else 'Autopilot (following the hero)'} chooses: "
                         f"{A['options'][choice]['label']}.",
                    result={"choice": choice, "by": pick["by"], "recommended": A["recommendation"]["choice"],
                            "followed_hero": choice == A["recommendation"]["choice"]})
            q.bridge_log.append({"assessment": A, "choice": choice, "by": pick["by"]})
            if choice == "evolve":
                evolve(q, A)
                continue
            trial(q, A, choice)
        break
    with q.lock:
        return q.finale()


# ---------- ResearcherSelfAssessment + EvolutionDecisionEngine ----------

def weaknesses(q, a) -> list[dict]:
    """Every weakness in a scroll the hero can name from the ledger, with its severity and fix."""
    d = q.director
    m3 = a.m.get(3, {})
    cast = {k for lv in a.cast.values() for k in lv} | set(getattr(a, "v2_fixes", []))
    out = []

    def add(key, fix=None, label=None, severity=None, **extra):
        W = rules.WEAKNESSES.get(key, {})
        out.append({"key": key, "label": label or W["label"], "severity": severity if severity is not None else W["severity"],
                    "fix": fix, "source": extra.pop("source", "judge"), **extra})

    if a.st.design == "ever":
        add("leakage", "TEMPORAL_GUARD" if "TEMPORAL_GUARD" not in cast else None, encounter=a.encounters.get("chrono"))
    if not a.st.adjusted:
        add("confounding", "BIAS_DETECTION", encounter=a.encounters.get("confound"))
    if m3 and m3.get("p_corr", 0) > rules.ALPHA and a.st.K > 1:
        add("search", None, encounter=a.encounters.get("sidak"),
            label=rules.WEAKNESSES["search"]["label"] + " (the search already ran on this cohort: preregistering now "
                                                        "would be retroactive)")
    if m3 and len(m3.get("replicating", [])) < 3:
        add("generalisation", "REPLICATION_SHIELD" if not a.st.replicated else None, encounter=a.encounters.get("hlab"))
    if m3 and m3.get("n_rct") == 0:
        add("no_rct", None, encounter=a.encounters.get("rct"))
    if not a.eureka:
        add("holdout", None, encounter=a.encounters.get("final"))
    if d is not None:
        for m in d.mysteries.values():
            if m["target"] != a.id:
                continue
            if m["status"] in ("offered", "saved", "unresolved"):
                testable = m["archetype"] in C.TESTS and not m.get("unmeasured")
                add(f"mystery:{m['id']}", "RETEST" if testable else None, source="director", mystery=m["id"],
                    label=f"Unresolved challenge {m['id']}: {m['question'] or m['text']}",
                    severity=(2 if testable else 1) + rules.USER_RAISED_BONUS, raised_level=m["raised_level"])
            elif m["status"] == "fallen":
                fix = FIX_FOR_FALLEN.get(m["archetype"])
                if fix == "BIAS_DETECTION" and a.st.adjusted:
                    fix = None
                if fix == "TEMPORAL_GUARD" and a.st.design != "ever":
                    fix = None
                add(f"mystery:{m['id']}", fix, source="director", mystery=m["id"],
                    label=f"{m['boss']} exposed a weakness ({m['id']}): {m['result']['line'] if m['result'] else ''}",
                    severity=2 + rules.USER_RAISED_BONUS, raised_level=m["raised_level"])
    sk = getattr(a, "skeptic", None)
    if sk and sk["outcome"] == "FALLEN":   # disclosed, never fixed here: the Skeptic's test is a robustness check
        add(f"skeptic:{sk['challenge']}", None, source="skeptic", severity=1,
            label=f"The Skeptic's {sk['challenge']} test exposed a weakness: {sk['line']}"[:300])
    for w in out:
        w["cost"] = _cost(w)
    return out


def _cost(w: dict) -> int:
    if not w["fix"]:
        return 0
    c = rules.MYSTERY_TEST_COST if w["fix"] == "RETEST" else rules.ABILITIES[w["fix"]]["cost"]
    if w.get("mystery") and w["fix"] != "RETEST":
        c += rules.MYSTERY_TEST_COST  # fix it, then fight the boss again
    return c


def plan_for(a, ws: list[dict]) -> dict:
    """The focused expedition the credits can pay for: most severe fixes first, each ability paid once."""
    budget = a.credits - rules.EVOLUTION_BASE_COST
    chosen, abilities, spent = [], set(), 0
    for w in sorted([w for w in ws if w["fix"]], key=lambda w: -w["severity"]):
        extra = (0 if w["fix"] in abilities or w["fix"] == "RETEST" else
                 rules.ABILITIES[w["fix"]]["cost"]) + (rules.MYSTERY_TEST_COST if w.get("mystery") else 0)
        if spent + extra <= budget:
            chosen.append(w)
            spent += extra
            if w["fix"] != "RETEST":
                abilities.add(w["fix"])
    return {"items": chosen, "abilities": sorted(abilities), "cost": spent + rules.EVOLUTION_BASE_COST if chosen else 0,
            "value": sum(w["severity"] for w in chosen), "budget": max(0, budget)}


def candidate(q):
    """The claim CROSS would commit: the best validated scroll, else the most promising survivor."""
    active = q._active()
    if not active:
        return None
    ss = lambda a: (a.m.get(4, {}).get("ss_oos") if a.m.get(4, {}).get("ss_oos") is not None else -9)
    good = [a for a in active if a.eureka]
    return max(good or active, key=lambda a: (ss(a), a.hp))


def review(q, a) -> dict:
    m2, m3, m4 = (a.m.get(k, {}) for k in (2, 3, 4))
    return {"id": a.id, "name": a.name, "archetype": a.archetype, "claim": a.claim, "status": a.status, "hp": a.hp,
            "credits": a.credits, "eureka": a.eureka, "design": a.st.design, "adjusted": a.st.adjusted, "K": a.st.K,
            "subgroup": a.st.subgroup, "direction": a.st.direction, "hypothesis_id": a.scroll.hypothesis_id,
            "ss_oos": m4.get("ss_oos"), "p_dm": m4.get("p_dm"), "rr_used": math.exp(m4["beta_used"]) if m4 else None,
            "rr_adjusted": (m2.get("adjusted") or {}).get("rr"), "p_corr": m3.get("p_corr"),
            "replicating": len(m3.get("replicating", [])), "sites": len(m3.get("sites", [])) or 5,
            "n_rct": m3.get("n_rct"), "failed_tests": [rules.TRAP_LABELS[t] for t, ok in a.traps.items() if not ok],
            "hp_by_level": dict(a.hp_by_level), "version": "V2" if getattr(a, "v2_fixes", None) is not None else "V1"}


def assess(q) -> dict:
    d = q.director
    cand = candidate(q)
    ws = weaknesses(q, cand) if cand else []
    plan = plan_for(cand, ws) if cand else {"items": [], "abilities": [], "cost": 0, "value": 0, "budget": 0}
    vault_ok = q.vault_opened is None
    fixable = [w for w in ws if w["fix"]]
    if q.evolved:
        evo = (False, "Evolution may happen only once per expedition, and Researcher V2 has already run.")
    elif not vault_ok:
        evo = (False, "The independent vault has already been opened, so no new valid evidence remains to evolve against.")
    elif cand is None:
        evo = (False, "No scroll survives to evolve.")
    elif not fixable:
        evo = (False, "No meaningful, testable weakness is left to investigate, so evolution cannot be scientifically justified.")
    elif not plan["items"]:
        cheapest = min(w["cost"] for w in fixable) + rules.EVOLUTION_BASE_COST
        evo = (False, f"{cand.name} has {cand.credits} credits left; the cheapest focused expedition costs {cheapest}.")
    else:
        evo = (True, f"A focused expedition can address {len(plan['items'])} weakness(es) for {plan['cost']} credits.")
    severe_left = [w for w in ws if not w["fix"] and w["severity"] >= 3]
    fallen = [w for w in ws if w["source"] == "director" and w["key"].startswith("mystery:") and "exposed" in w["label"]]
    if evo[0] and plan["value"] >= rules.EVOLVE_THRESHOLD:
        rec, why = "evolve", (f"The weaknesses a focused expedition can fix weigh {plan['value']} (threshold "
                              f"{rules.EVOLVE_THRESHOLD}), and {plan['cost']} credits pay for it.")
    elif cand is not None and cand.eureka and not severe_left and not fallen:
        rec, why = "cross", ("The claim beat the comparator on the vaulted holdout on a valid design, and no severe weakness "
                             "remains open.")
    elif cand is not None and cand.eureka and fallen:
        rec, why = "inconclusive", (f"The claim beat the comparator on the holdout, but a challenge you raised exposed a weakness "
                                    f"that {'Researcher V2 can no longer revisit' if q.evolved else 'no affordable test can fix'}: "
                                    f"{fallen[0]['label']}")
    elif cand is not None and cand.eureka:
        rec, why = "inconclusive", f"The claim beat the comparator on the holdout, but a severe weakness remains: {severe_left[0]['label']}"
    else:
        rec, why = "inconclusive", ("No claim beat the comparator on unseen patients, and no worthwhile test is left that could "
                                    "change that.")
    unresolved = [dict(m) for m in (d.unresolved() if d else [])]
    links = [{"mystery": m["id"], "raised_level": m["raised_level"], "text": m["text"],
              "effect": "in the evolution plan" if any(w.get("mystery") == m["id"] for w in plan["items"]) else
                        "weighed in the recommendation" if cand and m["target"] == cand.id else "noted (another scroll)"}
             for m in unresolved]
    speech = _speech(q, cand, ws, plan, rec)
    labels = {"cross": "CROSS THE BRIDGE", "evolve": "EVOLVE", "inconclusive": "PRESENT INCONCLUSIVE FINDINGS"}
    options = {
        "cross": {"label": labels["cross"], "enabled": cand is not None,
                  "reason": "Commit the current research specification to the final test." if cand else "No surviving claim to commit.",
                  "risk": "The claim may fail on evidence nobody has seen yet."},
        "evolve": {"label": labels["evolve"], "enabled": evo[0], "reason": evo[1], "cost": plan["cost"],
                   "plan": [{"label": w["label"], "fix": w["fix"], "severity": w["severity"], "mystery": w.get("mystery")}
                            for w in plan["items"]],
                   "risk": "Consumes credits; may expose evidence that weakens the claim; no guaranteed improvement."},
        "inconclusive": {"label": labels["inconclusive"], "enabled": True,
                         "reason": "Deliver a qualified report without asserting an unsupported discovery.", "risk": None},
    }
    return {
        "candidate": review(q, cand) if cand else None, "scrolls": [review(q, a) for a in q.agents.values()],
        "weaknesses": ws, "unresolved": unresolved, "causal_links": links,
        "leakage": [a.name for a in q._active() if a.st.design == "ever"],
        "credits": {a.id: a.credits for a in q.agents.values()},
        "independent_evidence": {"vault2_patients": q.vault2_n, "untouched": vault_ok},
        "plan": {"abilities": plan["abilities"], "cost": plan["cost"], "value": plan["value"],
                 "items": [w["key"] for w in plan["items"]]},
        "recommendation": {"choice": rec, "label": labels[rec], "why": why}, "options": options, "speech": speech,
        "evolved": q.evolved, "version": "V2" if q.evolved else "V1",
        "policy": {"evolve_threshold": rules.EVOLVE_THRESHOLD, "base_cost": rules.EVOLUTION_BASE_COST,
                   "user_raised_bonus": rules.USER_RAISED_BONUS},
    }


def _speech(q, cand, ws, plan, rec) -> str:
    if cand is None:
        return "Every scroll I carried has shattered. I have nothing I can defend, only what the failures taught me."
    m4 = cand.m.get(4, {})
    if cand.eureka:
        s = (f"My research suggests that {cand.claim[0].lower() + cand.claim[1:].rstrip('.')}: it predicted unseen holdout "
             f"patients better than the comparator (SS {m4.get('ss_oos', 0):+.4f}, paired p {m4.get('p_dm', 1):.2g}).")
    else:
        s = (f"My strongest scroll is {cand.name}, but it did not beat the comparator on the holdout "
             f"(SS {m4.get('ss_oos', 0) or 0:+.4f}).")
    top = sorted(ws, key=lambda w: -w["severity"])[:2]
    if top:
        s += " However: " + "; ".join(w["label"][0].lower() + w["label"][1:].rstrip(".") for w in top) + "."
    s += {"evolve": " I recommend Evolution before crossing.", "cross": " I recommend crossing the bridge.",
          "inconclusive": " I recommend presenting inconclusive findings."}[rec]
    return s


# ---------- ResearcherVersionManager + the Evolution Trial ----------

def snapshot(q) -> dict:
    return {"scrolls": [review(q, a) for a in q.agents.values()],
            "mysteries": [dict(m) for m in (q.director.mysteries.values() if q.director else [])],
            "measurements": {a.id: copy.deepcopy({k: _plain(v) for k, v in a.m.items()}) for a in q.agents.values()}}


def evolve(q, A: dict) -> None:
    d = q.director
    a = candidate(q)
    ws = weaknesses(q, a)
    plan = plan_for(a, ws)
    q.evolved = True
    q.versions["V1"] = snapshot(q)
    motivated = [w for w in plan["items"]]
    q._emit(actor="system", action="evolution_start", agent=a,
            line=f"Evolution approved. Researcher V1 is preserved; V2 will investigate {len(motivated)} weakness(es) in {a.name}.",
            explain="; ".join(w["label"] for w in motivated)[:400],
            result={"v1": q.versions["V1"], "plan": [{k: w.get(k) for k in ("key", "label", "fix", "severity", "mystery", "source")}
                                                      for w in motivated], "cost": plan["cost"],
                    "causal_links": [{"mystery": w["mystery"], "influenced": "the evolution plan"} for w in motivated if w.get("mystery")]})
    a.credits -= plan["cost"]
    a.spent += plan["cost"]
    q._emit(actor="system", action="evolution_transform", agent=a, cost=plan["cost"],
            line="Light floods the bridge. The Alchemist becomes Researcher V2.",
            result={"version": "V2", "abilities": plan["abilities"], "cost": plan["cost"]})
    a.v2_fixes = []
    v1 = {k: _plain(v) for k, v in a.m.items()}
    for k in plan["abilities"]:
        note = q.apply_ability(a, k)
        if k == "BIAS_DETECTION":
            a.st.adjusted = True
        a.v2_fixes.append(k)
        before = a.hp
        a.hp = min(rules.STARTING_HP, a.hp + rules.EVOLUTION_FIX_HEAL)
        q._emit(actor="system", action="evolution_step", agent=a, hp_delta=a.hp - before,
                line=f"V2 fixes a weakness: {note}", result={"v2_level": rules.ABILITIES[k]["level"], "ability": k,
                                                              "heal": a.hp - before, "rule": "EVOLUTION_FIX_HEAL"})
    w = q.w
    # The focused second expedition: one measurement per dungeon, each compared with V1's.
    q._emit(actor="judge", action="evolution_step", agent=a, line="V2, Level I: no new social evidence; the Rumour Dungeon is unchanged.",
            result={"v2_level": 1, "numbers": {"phi": v1.get(1, {}).get("phi"), "n_eff": v1.get(1, {}).get("n_eff")}})
    a.m[2] = J.level2(w, a.scroll, a.st)
    _step(q, a, 2, f"V2, Level II: rate ratio {a.m[2]['adjusted' if a.st.adjusted else 'naive']['rr']:.2f} in V2's design "
                   f"(V1 carried {(v1.get(2, {}).get('adjusted' if a.st.adjusted else 'naive') or {}).get('rr', float('nan')):.2f}).",
          {"rr_v2": a.m[2]["adjusted" if a.st.adjusted else "naive"]["rr"], "p_v2": a.m[2]["adjusted" if a.st.adjusted else "naive"]["p"]})
    a.m[3] = J.level3(w, a.scroll, a.st)
    _step(q, a, 3, f"V2, Level III: Sidak p_corr {a.m[3]['p_corr']:.2g} over K = {a.m[3]['K']}; replicated in "
                   f"{len(a.m[3]['replicating'])} of {len(a.m[3]['sites'])} sites.",
          {"p_corr_v2": a.m[3]["p_corr"], "K": a.m[3]["K"], "replicating_v2": len(a.m[3]["replicating"]),
           "p_corr_v1": v1.get(3, {}).get("p_corr"), "replicating_v1": len(v1.get(3, {}).get("replicating", []))})
    for item in plan["items"]:
        if not item.get("mystery"):
            continue
        orig = d.mysteries[item["mystery"]]
        m = d._new_mystery(a, 5, f"V2 re-test of {orig['id']}: {orig['text']}", orig["archetype"], "evolution",
                           covariate=orig.get("covariate"), outcome=orig.get("outcome"))
        m["parent"] = orig["id"]
        d.fight(m, 5, version="V2")
        orig.update(status="retested", retest=m["id"], resolved_by="V2", result=m["result"])
    eureka_v1 = a.eureka
    a.m[4] = J.level4(w, a.scroll, a.st)
    raw, a.eureka = J.d_final(a.m[4], a.st.design == "new_user", a.m[4]["direction_ok"])
    _step(q, a, 4, f"V2, Level IV (exploratory): SS {a.m[4]['ss_oos']:+.4f} on the holdout V1 already saw (p {a.m[4]['p_dm']:.2g}). "
                   "Not independent: only the sealed vault can validate V2.",
          {"ss_v2": a.m[4]["ss_oos"], "p_v2": a.m[4]["p_dm"], "ss_v1": v1.get(4, {}).get("ss_oos"), "exploratory": True})
    q.versions["V2"] = snapshot(q)
    change = ("strengthened" if a.eureka and not eureka_v1 else "weakened" if eureka_v1 and not a.eureka else
              "refined" if plan["abilities"] else "re-examined")
    q._emit(actor="system", action="evolution_complete", agent=a,
            line=f"Researcher V2 returns to the bridge. The conclusion was {change}.",
            result={"change": change, "v1": _row(q.versions["V1"], a.id), "v2": _row(q.versions["V2"], a.id),
                    "fixed": a.v2_fixes, "retests": [i["mystery"] for i in plan["items"] if i.get("mystery")]})


def _step(q, a, lv, line, numbers) -> None:
    q._emit(actor="judge", action="evolution_step", agent=a, line=line, result={"v2_level": lv, "numbers": numbers})


def _row(snap: dict, aid: str) -> dict:
    return next((s for s in snap["scrolls"] if s["id"] == aid), {})


# ---------- TrialOfTruthEvaluator ----------

def trial(q, A: dict, choice: str) -> None:
    a = candidate(q)
    stance = "assert" if choice == "cross" else "qualified"
    if a is None:
        q.trial = {"outcome": "JUSTIFIED UNCERTAINTY", "stance": stance, "spec": None, "crossed": True,
                   "line": "No claim survived, and the hero asserted none.", "evaluated": False}
        q._emit(actor="judge", action="trial_result", line="Trial of Truth: no claim to test. The hero crosses with a qualified report.",
                result={"trial": q.trial})
        return
    from .campaign import plan_hash
    from .hypotheses import ESTIMAND
    m4 = a.m.get(4, {})
    beta = float(m4.get("beta_used", 0.0))
    c, w = q.c, q.w
    # the claim, not this quest's slot for it: the same claim locked again on the same vault is a REPLAY
    spec = {"version": "V2" if q.evolved else "V1", "hypothesis_id": a.scroll.hypothesis_id,
            "hypothesis_version": a.scroll.version, "question_key": a.scroll.question_key, "claim": a.claim,
            "population": c.population, "subgroup": a.st.subgroup, "outcome": a.st.outcome,
            "direction": "lowers" if a.st.direction < 0 else "raises", "comparator": c.comparator, "estimand": ESTIMAND,
            "window_days": rules.FOLLOW_UP, "design": a.st.design, "adjusted": a.st.adjusted, "K": a.st.K,
            "ablated": a.st.ablated, "beta": round(beta, 6), "rate_ratio": round(math.exp(beta), 4), "stance": stance,
            "claim_lock_sha256": a.plan_sha, "analysis_version": rules.ANALYSIS_VERSION,
            "multiplicity_family": rules.MULTIPLICITY_FAMILIES["sealed_vault"],
            "partition": f"sealed vault: index day >= {HOLDOUT_END}", "cohort": w.fingerprint(), "seed": q.seed,
            "evaluation": "1:1 propensity-matched new users in the second vault (index day >= %d), the claim's subgroup; "
                          "SS_oos > %.3f, paired loss p < %.2f, effect in the claimed direction"
                          % (HOLDOUT_END, rules.SS_MARGIN, rules.ALPHA)}
    digest = _hash(spec)
    if q.vault_opened is not None:
        raise RuntimeError("the second vault was already opened")
    # the registry logs the opening BEFORE any vault patient is read
    reg = q.registry.open_vault(w.fingerprint(), c.id, q.seed, digest, a.scroll.question_key, q.run_id)
    q._emit(actor="system", action="spec_locked", agent=a,
            line=f"The research specification is locked ({digest[:12]}). "
                 + ("The sealed vault opens for the first time." if reg["independent"] else
                    f"This cohort's vault was opened {reg['prior_evaluations']} time(s) before: whatever happens, this "
                    "cannot count as a new independent confirmation."),
            result={"spec": spec, "sha256": digest, "vault": reg})
    q.vault_opened = {"by": "trial", "spec": digest, "kind": reg["kind"]}
    g = J.guardian(w, a.st.outcome, beta, "train", "vault2", subgroup=a.st.subgroup)
    failures = []
    if spec["design"] == "ever":
        failures.append("Immortal time: exposure was credited before the first fill, so the claim used information from the future.")
    if plan_hash(c, a.scroll, a.st) != a.plan_sha:
        failures.append("The claim changed after it was locked at recruitment.")
    if _hash(spec) != digest:
        failures.append("The specification changed after it was locked.")
    dir_ok = J.direction_ok(beta, a.st.direction)
    gain = (not g.get("no_overlap")) and g["ss_oos"] > rules.SS_MARGIN and g["p_dm"] < rules.ALPHA and dir_ok
    independent = reg["independent"]
    if stance == "assert" and failures:
        outcome = "INVALID METHODOLOGY"
    elif stance == "assert":
        outcome = ("VALIDATED DISCOVERY" if gain and independent else
                   "NO NEW INDEPENDENT CONFIRMATION" if gain else "UNJUSTIFIED CONFIDENCE")
    else:
        outcome = "JUSTIFIED UNCERTAINTY"
    q.registry.record_result(w.fingerprint(), reg["eval_id"], outcome, gain)
    label = confirmation_label(reg["kind"], gain)
    before = a.hp
    a.hp = max(0, min(rules.STARTING_HP, a.hp + rules.TRIAL_HP[outcome]))
    crossed = (outcome in ("VALIDATED DISCOVERY", "JUSTIFIED UNCERTAINTY", "NO NEW INDEPENDENT CONFIRMATION")
               or a.hp > 0 and outcome == "UNJUSTIFIED CONFIDENCE")
    note = ""
    if stance == "qualified":
        note = (" The vault would have supported the claim: the hero was more cautious than it needed to be, which is not punished."
                if gain and not failures else " The vault does not support a firm claim either: the caution was warranted."
                if not failures else " The design still had a validity flaw, which the qualified report must disclose.")
    if not dir_ok and beta != 0.0 and not g.get("no_overlap"):
        note += " The effect the claim carried points the opposite way to the claim itself."
    q.trial = {"outcome": outcome, "stance": stance, "spec": spec, "sha256": digest, "gain": gain, "failures": failures,
               "skill": {k: g.get(k) for k in ("ss_oos", "p_dm", "matched_pairs", "loss_scroll", "loss_comparator", "lift_pct")},
               "observed": g.get("observed"), "predicted": g.get("predicted"), "hp_delta": a.hp - before, "crossed": crossed,
               "scroll": a.id, "name": a.name, "line": rules.TRIAL_OUTCOMES[outcome] + note, "evaluated": True,
               "independent": independent, "vault_kind": reg["kind"], "vault_eval": reg["eval_id"],
               "confirmation_label": label, "direction_ok": dir_ok}
    ob, pr = g.get("observed") or {}, g.get("predicted") or {}
    chart = None if g.get("no_overlap") else {
        "kind": "grouped", "title": "Second vault, matched: one-year risk observed vs predicted",
        "groups": [{"label": "Users", "values": {"observed": ob.get("treated"), "scroll": pr.get("scroll_treated"),
                                                  "baseline": pr.get("baseline_treated")}},
                   {"label": "Comparators", "values": {"observed": ob.get("comparator"), "scroll": pr.get("scroll_comparator"),
                                                        "baseline": pr.get("baseline_comparator")}}]}
    skill = "no matched pairs" if g.get("no_overlap") else f"SS_oos {g['ss_oos']:+.4f} on {g['matched_pairs']} matched pairs, paired p {g['p_dm']:.3g}"
    q._emit(actor="judge", action="trial_result", agent=a, hp_delta=a.hp - before,
            passed=outcome in ("VALIDATED DISCOVERY", "JUSTIFIED UNCERTAINTY", "NO NEW INDEPENDENT CONFIRMATION"),
            line=f"Trial of Truth: {outcome}. {skill}. {label}.", explain=q.trial["line"],
            result={"trial": q.trial, "chart": chart, "numbers": q.trial["skill"],
                    "formula": "SS_oos = 1 - Loss_claim / Loss_comparator on the second vault; validated if SS > 0.002, "
                               "p < 0.05, the effect points the claimed way and the vault was never opened before"})
    if a.hp <= 0 and a.active:
        a.status, a.verdict = "shattered", "SHATTERED"
        q._emit(actor="judge", action="shatter", agent=a, line=f"The bridge gives way beneath {a.name}. The claim falls into the abyss.",
                explain=rules.TRIAL_OUTCOMES[outcome])


def _hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


# ---------- OverworldConsensusReport ----------

def overworld(q) -> dict:
    d = q.director
    t = q.trial or {}
    mysteries = list(d.mysteries.values()) if d else []
    summoned = [m for m in mysteries if m["status"] in ("survived", "fallen", "unresolved", "retested") and m.get("encounter")]
    a = q.agents.get(t.get("scroll") or "")
    if t.get("outcome") == "VALIDATED DISCOVERY":
        conclusion = f"{a.name}: \"{a.claim}\" survived the predeclared independent evaluation."
    elif t.get("outcome") == "JUSTIFIED UNCERTAINTY":
        conclusion = ("The hero presented qualified findings: the evidence does not justify a firm claim." if not t.get("gain") else
                      "The hero presented qualified findings; the sealed vault later showed the claim held, so a firmer claim was possible.")
    elif t.get("outcome") == "NO NEW INDEPENDENT CONFIRMATION":
        conclusion = (f"\"{a.claim}\" held on this cohort's vault, but the vault had been opened before, so it is "
                      f"{t.get('confirmation_label', 'not a new independent confirmation').lower()}.")
    elif t.get("outcome") == "UNJUSTIFIED CONFIDENCE":
        conclusion = f"The hero asserted \"{a.claim}\", but the sealed vault does not support it."
    elif t.get("outcome") == "INVALID METHODOLOGY":
        conclusion = f"The claim \"{a.claim}\" was rejected: " + "; ".join(t.get("failures", []))
    else:
        conclusion = "No final evaluation was run."
    changed = [m for m in mysteries if m["status"] in ("fallen", "retested") or any(
        any(w.get("mystery") == m["id"] for w in b["assessment"]["weaknesses"]) and b["choice"] == "evolve" for b in q.bridge_log)]
    return {
        "crossed": bool(t.get("crossed")), "trial": t,
        "conclusion": {"text": conclusion, "strongest": {"scroll": a.name, "claim": a.claim} if a else None,
                       "evidence": t.get("skill"), "uncertainty": _uncertainty(q, a), "validated": t.get("outcome") == "VALIDATED DISCOVERY",
                       "confirmation": t.get("confirmation_label"), "independent": t.get("independent")},
        "journey": {"hp_by_level": {x.id: dict(x.hp_by_level) for x in q.agents.values()},
                    "final_hp": {x.id: x.hp for x in q.agents.values()},
                    "credits_used": sum(x.spent for x in q.agents.values()),
                    "bosses": [e["name"] for lv in (3, 4) for e in rules.ENEMIES[lv] if e.get("boss")] + [m["boss"] for m in summoned],
                    "weaknesses": [w["label"] for w in (q.bridge_log[-1]["assessment"]["weaknesses"] if q.bridge_log else [])],
                    "tests_executed": q._enc},
        "contributions": {"evidence": [{k: r.get(k) for k in ("id", "classification", "kind", "url", "filename", "claim", "missing")}
                                       for r in (d.intakes if d else [])],
                          "summoned": [{k: m.get(k) for k in ("id", "boss", "status", "text", "hp_delta", "resolved_by")} for m in summoned],
                          "secret_levels": list(d.secret_levels) if d else [],
                          "unresolved": [{k: m.get(k) for k in ("id", "boss", "text", "reason", "raised_level")} for m in mysteries
                                         if m["status"] in ("offered", "saved", "unresolved")],
                          "changed_research": [{"id": m["id"], "text": m["text"], "how": "exposed a weakness" if m["status"] == "fallen"
                                                else "drove Researcher V2 to re-test it"} for m in changed]},
        "evolution": {"occurred": q.evolved,
                      "why": [w["label"] for b in q.bridge_log if b["choice"] == "evolve" for w in b["assessment"]["weaknesses"]
                              if w["key"] in b["assessment"]["plan"]["items"]],
                      "v1": _row(q.versions.get("V1", {"scrolls": []}), t.get("scroll")) if q.evolved else None,
                      "v2": _row(q.versions.get("V2", {"scrolls": []}), t.get("scroll")) if q.evolved else None},
        "ledger": {"hypotheses": [{"id": x.id, "claim": x.claim, "origin": x.scroll.origin} for x in q.agents.values()],
                   "data_version": f"simulated world {q.c.id}, seed {q.seed}; train index days < 1100, holdout 1100-1449, "
                                   f"sealed vault >= {HOLDOUT_END}",
                   "spec": t.get("spec"), "spec_sha256": t.get("sha256"),
                   "decisions": [{"choice": b["choice"], "by": b["by"], "recommended": b["assessment"]["recommendation"]["choice"]}
                                 for b in q.bridge_log]},
    }


def _uncertainty(q, a) -> str:
    if a is None:
        return "No claim survived."
    m3 = a.m.get(3, {})
    return (f"Observational, simulated data; {m3.get('n_rct', 0)} completed randomized trials registered on the topic "
            f"(results not assessed); replicated in {len(m3.get('replicating', []))} of {len(m3.get('sites', [])) or 5} "
            "sites. Unmeasured confounding cannot be ruled out.")


def _plain(x):
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    try:
        import numpy as np
        if isinstance(x, np.generic):
            return x.item()
    except ImportError:
        pass
    return x
