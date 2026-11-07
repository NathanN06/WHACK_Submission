"""The gauntlet's extra checks. Plain, deterministic statistics; no LLM ever touches a number.

The heavy tests (the Trial, the Shuffler, the Census, the holdout) are reused from
app.arena.engine. Everything here follows the same rules: people, not meals, are the
unit of resampling, and every result says whether it passed.
"""

import numpy as np
import pandas as pd

from ..arena import engine
from ..arena.engine import PID, participant_folds
from ..arena.features import Feature
from ..arena.models import Gladiator
from . import rules


def _people_with(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df.dropna(subset=[PID, *cols]).reset_index(drop=True)


def coverage(df: pd.DataFrame, g: Gladiator) -> dict:
    """Slime of Misinformation: can the claim be checked at all?"""
    need = [*g.add_features, *g.baseline_features, g.target]
    missing = [c for c in need if c not in df.columns]
    if missing:
        return {"passed": False, "untestable": True, "n_participants": 0,
                "reason": f"never measured: {', '.join(missing)}"}
    n = int(_people_with(df, need)[PID].nunique())
    ok = n >= rules.MIN_PEOPLE
    return {"passed": ok, "untestable": not ok, "n_participants": n,
            **({} if ok else {"reason": f"only {n} people have this data"})}


def _person_sums(d: pd.DataFrame, x: str, y: str) -> np.ndarray:
    """Per-person sufficient statistics [n, Σx, Σy, Σxx, Σyy, Σxy] for fast bootstraps."""
    xs, ys = d[x].astype(float), d[y].astype(float)
    t = pd.DataFrame({PID: d[PID], "n": 1.0, "x": xs, "y": ys, "xx": xs * xs, "yy": ys * ys, "xy": xs * ys})
    return t.groupby(PID)[["n", "x", "y", "xx", "yy", "xy"]].sum().to_numpy()


def _corr_from_sums(s: np.ndarray) -> np.ndarray:
    n, sx, sy, sxx, syy, sxy = (s[..., i] for i in range(6))
    cov = sxy - sx * sy / n
    vx, vy = sxx - sx * sx / n, syy - sy * sy / n
    with np.errstate(invalid="ignore", divide="ignore"):
        return cov / np.sqrt(vx * vy)


def raw_direction(df: pd.DataFrame, g: Gladiator, n_boot: int = 500, seed: int = 0) -> dict:
    """Rumour Goblin: before any modelling, does the raw data even point the claimed way?

    Pooled correlation of the (first) added feature with the outcome, with a
    bootstrap over people. 'contradicted' = the CI sits entirely on the wrong side.
    """
    f = g.add_features[0]
    d = _people_with(df, [f, g.target])
    sums = _person_sums(d, f, g.target)
    r = float(_corr_from_sums(sums.sum(axis=0)))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(n_boot, len(sums)))
    boots = _corr_from_sums(sums[idx].sum(axis=1))
    boots = boots[np.isfinite(boots)]
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if len(boots) else (r, r)
    claimed = g.expected_direction
    if claimed == "either":
        supported, contradicted = (lo > 0 or hi < 0), False
    else:
        sign = 1 if claimed == "positive" else -1
        supported = (lo > 0) if sign > 0 else (hi < 0)
        contradicted = (hi < 0) if sign > 0 else (lo > 0)
    return {"feature": f, "r": r, "ci_low": lo, "ci_high": hi, "claimed": claimed,
            "supported": bool(supported), "contradicted": bool(contradicted),
            "severe": bool(contradicted), "n_participants": int(len(sums)), "passed": bool(supported)}


def within_person(df: pd.DataFrame, g: Gladiator, min_meals: int = 5) -> dict:
    """Anecdote Bat: does the claim hold inside most individual people, not just on average?"""
    f = g.add_features[0]
    d = _people_with(df, [f, g.target])
    rs = []
    for _, p in d.groupby(PID):
        if len(p) >= min_meals and p[f].nunique() > 1 and p[g.target].nunique() > 1:
            rs.append(float(np.corrcoef(p[f].astype(float), p[g.target].astype(float))[0, 1]))
    rs = [r for r in rs if np.isfinite(r)]
    if len(rs) < rules.MIN_PEOPLE:
        return {"passed": False, "untestable": True, "n_participants": len(rs),
                "reason": "a person-level trait cannot vary within one person" if not rs
                else f"only {len(rs)} people have enough meals"}
    rs = np.array(rs)
    sign = {"positive": 1, "negative": -1}.get(g.expected_direction) or (1 if np.median(rs) >= 0 else -1)
    share = float(np.mean(np.sign(rs) == sign))
    return {"share_agree": share, "n_participants": int(len(rs)), "direction": "positive" if sign > 0 else "negative",
            "passed": bool(share > rules.MAJORITY)}


def echo(df: pd.DataFrame, g: Gladiator) -> dict:
    """Echo Chamber Wisp: is the claim just the baseline repeated in a new costume?"""
    if not g.baseline_features:
        return {"passed": True, "max_abs_r": 0.0, "note": "nothing to echo: this is the baseline itself"}
    rs = {}
    for f in g.add_features:
        for b in g.baseline_features:
            d = df[[f, b]].dropna().astype(float)
            if len(d) > 2 and d[f].std() > 0 and d[b].std() > 0:
                rs[f"{f}~{b}"] = float(d[f].corr(d[b]))
    worst = max((abs(v) for v in rs.values()), default=0.0)
    return {"max_abs_r": worst, "pairs": rs, "passed": bool(worst < rules.ECHO_CORR)}


def person_gains(df: pd.DataFrame, g: Gladiator) -> pd.Series:
    """Out-of-fold error drop per person (positive = the claim helps), from the arena engine."""
    base, full = engine._columns(g)
    d = engine._clean(df, g)
    return engine._cv_gain_per_person(d, g.target, base, full)


def majority_benefit(gains: pd.Series) -> dict:
    """Small Sample Skeleton: do most people benefit, or is the average carried by a few?"""
    share = float((gains > 0).mean())
    return {"share_benefit": share, "n_participants": int(len(gains)), "passed": bool(share > rules.MAJORITY)}


def confounding(direction: dict, trial: dict) -> dict:
    """Confounding Phantom: does the raw sign survive adjusting for the baseline?

    A sign that flips once carbs are in the model means the raw pattern was really carbs.
    """
    f = direction["feature"]
    adjusted = (trial.get("direction") or {}).get(f)
    raw_sign = "positive" if direction["r"] > 0 else "negative"
    raw_clear = direction["ci_low"] > 0 or direction["ci_high"] < 0
    flipped = bool(adjusted and raw_clear and adjusted != raw_sign)
    return {"feature": f, "raw": raw_sign, "adjusted": adjusted, "raw_clear": bool(raw_clear),
            "flipped": flipped, "passed": not flipped}


def too_good(trial: dict) -> dict:
    """Citation Spider: an improvement over a quarter of the baseline error is suspicious."""
    share = trial["gain"] / trial["mae_baseline"] if trial.get("mae_baseline") else 0.0
    return {"gain": trial["gain"], "share_of_error": float(share), "passed": not trial.get("too_good", False)}


def fold_replication(df: pd.DataFrame, g: Gladiator) -> dict:
    """Replication Sentinel: split people into 5 independent groups; how many replicate?"""
    base, full = engine._columns(g)
    d = engine._clean(df, g)
    y, Xb, Xf = d[g.target].to_numpy(float), d[base].to_numpy(float), d[full].to_numpy(float)
    folds = []
    for tr, te in participant_folds(d):
        err_b = np.abs(y[te] - engine._fit_predict(Xb[tr], y[tr], Xb[te]))
        err_f = np.abs(y[te] - engine._fit_predict(Xf[tr], y[tr], Xf[te]))
        per_person = pd.Series(err_b - err_f).groupby(d[PID].to_numpy()[te]).mean()
        folds.append(round(float(per_person.mean()), 4))
    k = sum(v > 0 for v in folds)
    return {"fold_gains": folds, "replicated": int(k), "n_groups": len(folds),
            "passed": bool(k >= rules.FOLDS_NEEDED)}


def trimmed_gain(gains: pd.Series) -> dict:
    """Chimera, Selection Bias head: drop the top 10% of contributors. Is there still a gain?"""
    s = gains.sort_values(ascending=False)
    k = max(1, int(round(rules.TRIM_SHARE * len(s))))
    rest = s.iloc[k:]
    trimmed = float(rest.mean()) if len(rest) else 0.0
    return {"gain": float(s.mean()), "trimmed_gain": trimmed, "dropped": k, "passed": bool(trimmed > 0)}


def temporal(g: Gladiator, registry: dict[str, Feature]) -> dict:
    """Chronolock Guardian: was every feature known when the meal was eaten?"""
    later = [f for f in g.add_features if f in registry and registry[f].available == "after_meal"]
    return {"after_meal": later, "passed": not later}


def provenance(test: pd.DataFrame | None, g: Gladiator) -> dict:
    """Bureaucratic Titan: is the claim even recorded in the independent records?"""
    if test is None:
        return {"passed": False, "untestable": True, "reason": "no independent records loaded"}
    need = [*g.add_features, *g.baseline_features, g.target]
    missing = [c for c in need if c not in test.columns]
    if missing:
        return {"passed": False, "untestable": True, "reason": f"not recorded there: {', '.join(missing)}"}
    present = test.dropna(subset=need)
    n = int(present[PID].nunique())
    share = float(1 - len(present) / max(1, len(test)))
    ok = n >= rules.MIN_PEOPLE
    return {"n_participants": n, "missing_share": share, "passed": ok, "untestable": not ok,
            **({} if ok else {"reason": f"only {n} people recorded there"})}
