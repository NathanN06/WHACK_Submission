"""The Research Challenge Registry: every test a Mystery Boss may run, and nothing else.

A user's challenge is routed to one archetype here; the Skeptic picks that archetype's test; the test is
deterministic code on the training cohort only. Neither the vaulted holdout (Level IV) nor the second vault
(the Trial of Truth) is ever read here: `_train()` refuses any mask that reaches them.

Each test returns an outcome:
  SURVIVED     the claim held up under the challenge
  FALLEN       the challenge exposed a real weakness
  UNRESOLVED   no valid test could be run (the data cannot answer it); nothing is invented instead
"""

from __future__ import annotations

import math
import re

import numpy as np
from scipy import stats

from . import judge as J
from . import rules
from .world import COVARIATE_LABELS, COVARIATES, SITES, World

ARCHETYPES = {
    "seasonal": {"boss": "The Seasonal Wraith", "key": "m_seasonal",
                 "question": "Does the relationship disappear after accounting for seasonal patterns?",
                 "test": "Season-adjusted rate ratio (index-date quarter) and the effect in each quarter",
                 "ability": "Seasonal Ward", "attack": "Winter fills the clinics. Was it the drug, or the calendar?",
                 "rule": "survives if the season-adjusted effect keeps its direction with p < 0.05 and season moves it < 50%"},
    "chronolock": {"boss": "The Chronolock Assassin", "key": "m_chronolock",
                   "question": "Did the hero accidentally use information from the future?",
                   "test": "Leakage audit: immortal time in the exposure definition, and the effect with it purged",
                   "ability": "Time-Zero Audit", "attack": "You counted days your patients had not lived yet.",
                   "rule": "survives if exposure starts at the first fill and training precedes the holdout in calendar time"},
    "regional": {"boss": "The Regional Hydra", "key": "m_regional",
                 "question": "Does the finding generalise across locations?",
                 "test": "Per-site rate ratios, Cochran's Q heterogeneity test, and the rural sites pooled",
                 "ability": "Site-by-Site Survey", "attack": "Cut off one head and the rural ones still disagree.",
                 "rule": "survives if Cochran's Q p >= 0.05 and the pooled rural sites show the claimed direction with p < 0.05"},
    "chance": {"boss": "The Probability Phantom", "key": "m_chance",
               "question": "Could the apparent result arise by chance?",
               "test": f"Permutation test: {rules.PERMUTATIONS} label shuffles in the new-user cohort, Sidak-corrected for the scroll's search",
               "ability": "Shuffle Ritual", "attack": "Roll the dice enough times and anything glows.",
               "rule": "survives if the Sidak-corrected permutation p < 0.05 in the claimed direction"},
    "replication": {"boss": "The Replication Revenant", "key": "m_replication",
                    "question": "Does the result survive independent evaluation?",
                    "test": "Fit on the earlier training years, re-estimate on the last quarter of them, untouched by the fit",
                    "ability": "Second Sight", "attack": "Show me it again, on patients your model has not met.",
                    "rule": "survives if the later slice alone shows the claimed direction with p < 0.05 (the vaults stay closed)"},
    "redundancy": {"boss": "The Redundancy Golem", "key": "m_redundancy",
                   "question": "Does the new signal add predictive value beyond the established baseline?",
                   "test": "Ablation on a validation slice of the training years: skill score vs the no-drug-effect baseline",
                   "ability": "Ablation Strike", "attack": "The comparator already knew all that. What do you add?",
                   "rule": "survives if the drug term lowers loss on the validation slice (SS > 0), as the Ablation Strike rule"},
    "confounder": {"boss": "The Confounder Shapeshifter", "key": "m_confounder",
                   "question": "Could an alternative variable explain the finding?",
                   "test": "Rate ratio adjusted for the named (or every measured) confounder, and which one moves it most",
                   "ability": "Bias Detection", "attack": "I wear the drug's face. Look closer: it was always someone else.",
                   "rule": "survives if the adjusted effect keeps the claimed direction with p < 0.05"},
}

KEYWORDS = {
    "chronolock": ["future", "leak", "look-ahead", "lookahead", "immortal", "time zero", "time-zero", "hindsight",
                   "before the first", "before they started", "after the fact", "peek"],
    "seasonal": ["season", "winter", "summer", "autumn", "spring", "month", "holiday", "christmas", "january",
                 "calendar", "flu season"],
    "regional": ["region", "site", "rural", "urban", "city", "cities", "generalis", "generaliz", "location",
                 "hospital", "country", "countries", "geograph", "elsewhere", "other places", "transport"],
    "chance": ["chance", "luck", "lucky", "random", "fluke", "p-hack", "p hack", "phack", "false positive",
               "coincidence", "noise", "by accident", "significan"],
    "replication": ["replicat", "independent", "reproduc", "hold up", "holds up", "out of sample", "out-of-sample",
                    "different period", "new data", "another dataset", "later years", "unseen"],
    "redundancy": ["baseline", "add value", "adds value", "redundan", "beyond the", "predictive value",
                   "incremental", "better than the comparator", "on top of", "already known"],
    "confounder": ["confound", "alternative explanation", "explained by", "because of", "caused by", "instead",
                   "really the", "actually the", "healthy user", "healthier", "sicker", "selection"],
}

COVARIATE_WORDS = {
    "trt": ["testosterone", "trt", "steroid", "hormone"],
    "healthy": ["gym", "exercise", "diet", "healthy", "fitness", "training", "lifestyle", "screening"],
    "therapy": ["therapy", "coaching", "counsel", "rehab programme", "behavioural", "behavioral", "psycholog"],
    "age10": ["age", "older", "younger", "elderly"],
    "female": ["sex", "women", "men", "female", "male", "gender"],
    "severity": ["severity", "severe", "sicker", "sick", "worse disease", "comorbid"],
}
UNMEASURED_WORDS = ["income", "wealth", "education", "insurance", "genetic", "gene", "wastewater", "ethnicity",
                    "race", "postcode", "zip code", "smoking status", "bmi", "weight loss", "adherence", "dose"]


def route(text: str) -> dict:
    """QuestionRouter: which registered challenge (if any) a piece of text raises. Pure keyword rules."""
    t = " " + (text or "").lower() + " "
    covariate = next((k for k, words in COVARIATE_WORDS.items() if any(_word(t, w) for w in words)), None)
    unmeasured = next((w for w in UNMEASURED_WORDS if _word(t, w)), None)
    scores = {k: sum(w in t for w in words) for k, words in KEYWORDS.items()}
    if covariate or unmeasured:
        scores["confounder"] += 1
    best = max(scores, key=scores.get)
    archetype = best if scores[best] > 0 else None
    return {"archetype": archetype, "covariate": covariate if archetype == "confounder" else None,
            "unmeasured": unmeasured if archetype == "confounder" and not covariate else None, "scores": scores}


def _word(t: str, w: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(w), t) is not None


# ---------- the tests ----------

def _train(w: World, mask: np.ndarray | None = None) -> np.ndarray:
    """The training cohort, optionally narrowed. Refuses anything that reaches a vault."""
    train = w.mask("train")
    if mask is None:
        return train
    if np.any(mask & ~train):
        raise PermissionError("a Mystery Boss may only read the training cohort")
    return mask


def _fit(w: World, st, mask: np.ndarray, adjusted: bool | None = None, extra=None, outcome: str | None = None) -> dict:
    """Log rate ratio of the drug in the scroll's current design, optionally with extra columns."""
    mask = _train(w, mask)
    r = w.rows(outcome or st.outcome, st.design, mask)
    X = r["exposed"][:, None]
    if st.adjusted if adjusted is None else adjusted:
        X = np.column_stack([X, w.covariates(r["i"])])
    if extra is not None:
        X = np.column_stack([X, extra(r["i"])])
    b, se = J.poisson_fit(X, r["event"], r["pt"])
    beta, s = float(b[1]), float(se[1])
    return {"beta": beta, "se": s, "rr": math.exp(beta), "p": J.p_two(beta / s), "events": int(r["event"].sum())}


def _holds(e: dict, direction: int) -> bool:
    return e["p"] < rules.ALPHA and np.sign(e["beta"]) == direction


def _ci(e: dict) -> dict:
    return {"est": round(e["rr"], 4), "lo": round(math.exp(e["beta"] - 1.96 * e["se"]), 4),
            "hi": round(math.exp(e["beta"] + 1.96 * e["se"]), 4)}


def _quarter(w: World, i: np.ndarray) -> np.ndarray:
    return ((w.index[i] % 365) // 92).clip(0, 3)


def test_seasonal(w: World, a, spec: dict) -> dict:
    st, d = a.st, w.c.effect_direction
    train = _train(w)
    base = _fit(w, st, train)

    def season(i):
        q = _quarter(w, i)
        return np.column_stack([(q == k).astype(float) for k in (1, 2, 3)])

    adj = _fit(w, st, train, extra=season)
    per = []
    for k, name in enumerate(["Jan to Mar", "Apr to Jun", "Jul to Sep", "Oct to Dec"]):
        sub = train & (((w.index % 365) // 92).clip(0, 3) == k)
        e = _fit(w, st, sub)
        per.append({"label": name, **_ci(e)})
    shift = abs(base["beta"] - adj["beta"]) / max(abs(base["beta"]), 1e-9)
    ok = _holds(adj, d) and shift < 0.5
    return _out(ok, f"Rate ratio {base['rr']:.2f} without season, {adj['rr']:.2f} adjusted for the quarter of the index date "
                    f"(p = {adj['p']:.2g}); season moves the effect {shift * 100:.0f}%.",
                ("The relationship survives once the calendar is accounted for." if ok else
                 "Once season is accounted for, the relationship does not hold up in the claimed direction."
                 if _holds(base, d) else "There was no significant relationship in the claimed direction to begin with."),
                {"rr_without_season": base["rr"], "rr_season_adjusted": adj["rr"], "p_adjusted": adj["p"], "season_shift": shift},
                ARCHETYPES["seasonal"]["rule"],
                {"kind": "forest", "title": "Rate ratio in each quarter of the year (training cohort)", "ref": 1.0, "rows": per})


def test_chronolock(w: World, a, spec: dict) -> dict:
    st = a.st
    train = _train(w)
    share = J.immortal_share(w, st.outcome, st.design, train)
    cur = _fit(w, st, train)
    purged_st = _Copy(st, design="new_user")
    purged = _fit(w, purged_st, train)
    leak = st.design == "ever" and share > 0.01
    # the structural audit: every training row's index date is before the holdout begins
    structural = bool(np.all(w.index[train] < w.index[w.mask("holdout")].min())) if w.mask("holdout").any() else True
    ok = not leak and structural
    return _out(ok, (f"{share * 100:.0f}% of the 'treated' person-time came before the first fill; rate ratio {cur['rr']:.2f} "
                     f"as carried vs {purged['rr']:.2f} time-zero aligned." if leak else
                     f"Exposure starts at the first fill (no immortal time); rate ratio {cur['rr']:.2f}. Training rows all precede the holdout."),
                ("The scroll credits the drug with time before anyone took it: information from the future." if leak else
                 "No future information found in the design or the split."),
                {"immortal_share": share, "rr_as_carried": cur["rr"], "rr_time_zero": purged["rr"],
                 "split_respects_time": structural},
                ARCHETYPES["chronolock"]["rule"],
                {"kind": "forest", "title": "Rate ratio as carried vs time-zero aligned", "ref": 1.0,
                 "rows": [{"label": "As carried", **_ci(cur)}, {"label": "Time-zero aligned", **_ci(purged)}]},
                leakage=leak)


def test_regional(w: World, a, spec: dict) -> dict:
    st, d = a.st, w.c.effect_direction
    train = _train(w)
    sites = []
    for k, (name, rural) in enumerate(SITES):
        e = _fit(w, st, train & (w.site == k))
        sites.append({"name": name, "rural": rural, **e})
    b = np.array([s["beta"] for s in sites])
    v = np.array([s["se"] ** 2 for s in sites])
    wts = 1 / v
    pooled = float((wts * b).sum() / wts.sum())
    Q = float((wts * (b - pooled) ** 2).sum())
    df = len(sites) - 1
    p_q = float(stats.chi2.sf(Q, df))
    i2 = max(0.0, (Q - df) / Q) if Q > 0 else 0.0
    rural_mask = train & np.isin(w.site, [k for k, (_, r) in enumerate(SITES) if r])
    rural = _fit(w, st, rural_mask)
    ok = p_q >= rules.ALPHA and _holds(rural, d)
    n_hold = sum(_holds(s, d) for s in sites)
    return _out(ok, f"Cochran's Q = {Q:.1f} on {df} df (p = {p_q:.2g}, I² = {i2 * 100:.0f}%); rural sites pooled: rate ratio "
                    f"{rural['rr']:.2f} (p = {rural['p']:.2g}); holds on its own in {n_hold} of {len(sites)} sites.",
                ("The effect is consistent across sites, rural ones included." if ok else
                 "The sites disagree more than chance allows." if p_q < rules.ALPHA else
                 "The rural sites do not confirm the effect on their own."),
                {"cochran_q": Q, "p_heterogeneity": p_q, "i2": i2, "rr_rural": rural["rr"], "p_rural": rural["p"],
                 "sites_holding": n_hold},
                ARCHETYPES["regional"]["rule"],
                {"kind": "forest", "title": "Rate ratio in each EHR site (training cohort)", "ref": 1.0,
                 "rows": [{"label": s["name"] + (" (rural)" if s["rural"] else ""), **_ci(s)} for s in sites]})


def test_chance(w: World, a, spec: dict) -> dict:
    st, d = a.st, w.c.effect_direction
    outcome = spec.get("outcome") or st.outcome
    nu = w.new_user(outcome, _train(w))
    t, y = nu["treated"].astype(bool), nu["y"]
    if t.sum() < 10 or (~t).sum() < 10:
        return unresolved("Too few new users or comparators in the training cohort to shuffle.")
    obs = float(y[t].mean() - y[~t].mean())
    rng = np.random.default_rng(4242 + w.seed)
    perms = np.empty(rules.PERMUTATIONS)
    for k in range(rules.PERMUTATIONS):
        s = rng.permutation(t)
        perms[k] = y[s].mean() - y[~s].mean()
    # one-sided, in the claimed direction
    p_perm = float((1 + np.sum(d * perms >= d * obs)) / (1 + rules.PERMUTATIONS))
    K = st.K if outcome == st.outcome else st.K + 1
    p_corr = J.sidak(p_perm, K)
    ok = p_corr < rules.ALPHA and np.sign(obs) == d
    olabel = next(o.label for o in w.c.outcomes if o.key == outcome)
    hist, edges = np.histogram(perms, bins=8)
    return _out(ok, f"{olabel}: one-year risk difference {obs * 100:+.1f} points; {rules.PERMUTATIONS} shuffles give "
                    f"p_perm = {p_perm:.3g}, Sidak over K = {K}: p_corr = {p_corr:.3g}.",
                ("Shuffling who got the drug almost never produces a gap this large: not luck." if ok else
                 "Shuffled labels produce gaps this large too often: it could be luck."),
                {"risk_difference": obs, "p_perm": p_perm, "K": K, "p_corr": p_corr, "permutations": rules.PERMUTATIONS},
                ARCHETYPES["chance"]["rule"],
                {"kind": "bars", "title": "Shuffled risk differences (count per bin); the observed gap is "
                                          f"{obs * 100:+.1f} points",
                 "bars": [{"label": f"{edges[k] * 100:+.1f}", "value": int(hist[k])} for k in range(len(hist))]})


def test_replication(w: World, a, spec: dict) -> dict:
    st, d = a.st, w.c.effect_direction
    train = _train(w)
    cut = np.quantile(w.index[train], 1 - rules.VALIDATION_SLICE)
    early, late = train & (w.index < cut), train & (w.index >= cut)
    e1, e2 = _fit(w, st, early), _fit(w, st, late)
    ok = _holds(e2, d)
    return _out(ok, f"Earlier training years: rate ratio {e1['rr']:.2f}; the last quarter of them, estimated on its own: "
                    f"{e2['rr']:.2f} (p = {e2['p']:.2g}).",
                ("The effect reappears in the later period on its own." if ok else
                 "The later period does not confirm the effect on its own."),
                {"rr_earlier": e1["rr"], "rr_later": e2["rr"], "p_later": e2["p"], "split_day": float(cut)},
                ARCHETYPES["replication"]["rule"],
                {"kind": "forest", "title": "Rate ratio: earlier vs later training years", "ref": 1.0,
                 "rows": [{"label": "Earlier years", **_ci(e1)}, {"label": "Later quarter (independent)", **_ci(e2)}]})


def test_redundancy(w: World, a, spec: dict) -> dict:
    keep, g = J.ablation_keeps_drug(w, a.st)
    if g.get("no_overlap"):
        return unresolved("No matched pairs on the validation slice, so added value cannot be measured.")
    return _out(keep, f"On the validation slice the drug term gives SS = {g['ss_oos']:+.4f} vs the no-effect baseline "
                      f"({g['matched_pairs']} matched pairs, paired p = {g['p_dm']:.3g}).",
                ("Knowing about the drug lowers prediction loss beyond the baseline." if keep else
                 "The drug term adds nothing the baseline did not already know."),
                {"ss_validation": g["ss_oos"], "p_dm": g["p_dm"], "matched_pairs": g["matched_pairs"]},
                ARCHETYPES["redundancy"]["rule"],
                None)


def test_confounder(w: World, a, spec: dict) -> dict:
    st, d = a.st, w.c.effect_direction
    cov = spec.get("covariate")
    if spec.get("unmeasured"):
        return unresolved(f"\"{spec['unmeasured']}\" is not measured in this cohort, so no test can adjust for it. "
                          "The challenge stays open.")
    train = _train(w)
    base = _fit(w, st, train, adjusted=False)
    moves = []
    for k in COVARIATES:
        e = _fit(w, st, train, adjusted=False, extra=lambda i, k=k: w.X[k][i][:, None])
        moves.append({"label": COVARIATE_LABELS[k], "key": k, "value": round(abs(base["beta"] - e["beta"]) / max(abs(base["beta"]), 1e-9), 3), "e": e})
    if cov:
        chosen = next(m for m in moves if m["key"] == cov)
        adj = chosen["e"]
        what = COVARIATE_LABELS[cov].lower()
    else:
        adj = _fit(w, st, train, adjusted=True)
        what = "every measured confounder and site"
    worst = max(moves, key=lambda m: m["value"])
    ok = _holds(adj, d)
    return _out(ok, f"Rate ratio {base['rr']:.2f} unadjusted, {adj['rr']:.2f} adjusted for {what} (p = {adj['p']:.2g}); "
                    f"the biggest single mover is {worst['label'].lower()} ({worst['value'] * 100:.0f}%).",
                ("The effect keeps its direction and significance after the adjustment." if ok else
                 f"Adjusting for {what} takes the effect away: an alternative variable can explain it."),
                {"rr_unadjusted": base["rr"], "rr_adjusted": adj["rr"], "p_adjusted": adj["p"],
                 "largest_mover": worst["label"], "largest_shift": worst["value"]},
                ARCHETYPES["confounder"]["rule"],
                {"kind": "bars", "title": "How far each confounder alone moves the effect (share of log rate ratio)",
                 "bars": [{"label": m["label"], "value": m["value"]} for m in moves]})


TESTS = {"seasonal": test_seasonal, "chronolock": test_chronolock, "regional": test_regional, "chance": test_chance,
         "replication": test_replication, "redundancy": test_redundancy, "confounder": test_confounder}


def run(w: World, a, archetype: str, spec: dict) -> dict:
    """Validate the Skeptic's choice against the registry, then execute it. Unknown tests never run."""
    if archetype not in TESTS:
        return unresolved(f"No registered test for {archetype!r}.")
    if not a.active:
        return unresolved(f"{a.name} has already shattered; there is no claim left to test.")
    return TESTS[archetype](w, a, spec)


def unresolved(why: str) -> dict:
    return {"outcome": "UNRESOLVED", "line": why, "plain": "No valid test could be run, so the encounter stays open. "
            "Nothing was decided and no number was invented.", "numbers": {}, "rule": "no test: unresolved", "chart": None}


def _out(ok: bool, line: str, plain: str, numbers: dict, rule: str, chart, leakage: bool = False) -> dict:
    return {"outcome": "SURVIVED" if ok else "FALLEN", "leakage": leakage and not ok, "line": line, "plain": plain,
            "numbers": numbers, "rule": rule, "chart": chart}


class _Copy:
    """A read-only view of a ScrollState with some fields replaced."""

    def __init__(self, st, **over):
        self._st, self._over = st, over

    def __getattr__(self, k):
        return self._over[k] if k in self._over else getattr(self._st, k)
