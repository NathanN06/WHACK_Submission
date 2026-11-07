"""The statistics engine: plain, deterministic Python. It decides every number.

Rules that keep it honest:
- Folds are split by participant, never by meal, so nobody's meals leak across.
- Improvement is averaged per person first, so heavy loggers don't dominate.
- Uncertainty comes from resampling people, not meals.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from . import config
from .features import Feature
from .models import Gladiator

PID = "participant_id"


def _columns(g: Gladiator) -> tuple[list[str], list[str]]:
    base = list(dict.fromkeys(g.baseline_features))
    full = base + [f for f in g.add_features if f not in base]
    return base, full


def _clean(df: pd.DataFrame, g: Gladiator) -> pd.DataFrame:
    _, full = _columns(g)
    return df.dropna(subset=[g.target, PID, *full]).reset_index(drop=True)


def participant_folds(df: pd.DataFrame, n_splits: int = config.N_SPLITS):
    """GroupKFold on participant_id. Yields (train_idx, test_idx)."""
    groups = df[PID].to_numpy()
    k = min(n_splits, len(np.unique(groups)))
    yield from GroupKFold(n_splits=k).split(df, groups=groups)


def _fit_predict(X_tr, y_tr, X_te):
    if X_tr.shape[1] == 0:
        return np.full(len(X_te), y_tr.mean())
    return LinearRegression().fit(X_tr, y_tr).predict(X_te)


def _cv_gain_per_person(d: pd.DataFrame, target: str, base: list[str], full: list[str]) -> pd.Series:
    """Out-of-fold (baseline error - full error), averaged per person. Positive = feature helps."""
    y = d[target].to_numpy(float)
    Xb = d[base].to_numpy(float)
    Xf = d[full].to_numpy(float)
    gain = np.empty(len(d))
    for tr, te in participant_folds(d):
        err_b = np.abs(y[te] - _fit_predict(Xb[tr], y[tr], Xb[te]))
        err_f = np.abs(y[te] - _fit_predict(Xf[tr], y[tr], Xf[te]))
        gain[te] = err_b - err_f
    return pd.Series(gain).groupby(d[PID].to_numpy()).mean()


def _bootstrap_ci(values: np.ndarray, n_boot: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _standalone_r(d: pd.DataFrame, target: str, features: list[str]) -> float:
    rs = [d[f].astype(float).corr(d[target].astype(float)) for f in features]
    rs = [abs(r) for r in rs if pd.notna(r)]
    return float(max(rs)) if rs else 0.0


def _untestable(n_people: int, reason: str) -> dict:
    return {"passed": False, "untestable": True, "n_participants": n_people, "reason": reason}


def added_value(df: pd.DataFrame, g: Gladiator, n_boot: int = config.N_BOOT, seed: int = 0) -> dict:
    """The Trial: does adding the features cut held-out error beyond the baseline?"""
    missing = [c for c in (*g.add_features, *g.baseline_features, g.target) if c not in df.columns]
    if missing:
        return _untestable(0, f"missing columns: {missing}")
    d = _clean(df, g)
    n_people = d[PID].nunique()
    if n_people < config.MIN_PARTICIPANTS:
        return _untestable(n_people, f"only {n_people} people have this data")
    base, full = _columns(g)
    gains = _cv_gain_per_person(d, g.target, base, full).to_numpy()
    lo, hi = _bootstrap_ci(gains, n_boot, seed)
    y = d[g.target].to_numpy(float)
    mae_base = float(np.mean(np.abs(y - _oof_predictions(d, g.target, base))))
    coefs = LinearRegression().fit(d[full].to_numpy(float), y).coef_
    return {
        "gain": float(gains.mean()),
        "ci_low": lo,
        "ci_high": hi,
        "mae_baseline": mae_base,
        "too_good": bool(gains.mean() > config.TOO_GOOD_GAIN_SHARE * mae_base),
        "standalone_r": _standalone_r(d, g.target, g.add_features),
        "direction": {f: ("positive" if c > 0 else "negative")
                      for f, c in zip(full, coefs) if f in g.add_features},
        "n_participants": int(n_people),
        "n_meals": int(len(d)),
        "passed": bool(lo > 0),
    }


def _oof_predictions(d: pd.DataFrame, target: str, cols: list[str]) -> np.ndarray:
    y = d[target].to_numpy(float)
    X = d[cols].to_numpy(float)
    pred = np.empty(len(d))
    for tr, te in participant_folds(d):
        pred[te] = _fit_predict(X[tr], y[tr], X[te])
    return pred


def _shuffle(d: pd.DataFrame, cols: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """Break the link between features and outcome but keep everything else.

    Meal-level features are shuffled within each person. Person-level features
    (constant within a person, e.g. HbA1c) are shuffled across people.
    """
    out = d.copy()
    for c in cols:
        per_person = d.groupby(PID)[c].nunique(dropna=False)
        if (per_person <= 1).all():
            people = d.groupby(PID)[c].first()
            mapping = pd.Series(rng.permutation(people.to_numpy()), index=people.index)
            out[c] = d[PID].map(mapping).to_numpy()
        else:
            out[c] = d.groupby(PID)[c].transform(lambda s: rng.permutation(s.to_numpy()))
    return out


def shuffle_test(df: pd.DataFrame, g: Gladiator, n_perm: int = config.N_PERM, seed: int = 0) -> dict:
    """The Shuffler: does the real feature beat shuffled copies of itself?"""
    d = _clean(df, g)
    base, full = _columns(g)
    observed = float(_cv_gain_per_person(d, g.target, base, full).mean())
    rng = np.random.default_rng(seed)
    added = [f for f in full if f not in base]
    null = np.array([
        _cv_gain_per_person(_shuffle(d, added, rng), g.target, base, full).mean()
        for _ in range(n_perm)
    ])
    k = int((null >= observed).sum())
    p = (k + 1) / (n_perm + 1)
    return {
        "observed_gain": observed,
        "null_mean": float(null.mean()),
        "beaten_by": k,
        "n_perm": n_perm,
        "p": p,
        "passed": bool(p < config.ALPHA),
    }


def penalty(pvalues: dict[str, float], alpha: float = config.ALPHA) -> dict[str, dict]:
    """The Census: Benjamini-Hochberg across every claim shuffle-tested this run."""
    if not pvalues:
        return {}
    ids = list(pvalues)
    p = np.array([pvalues[i] for i in ids], dtype=float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adj_sorted = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1.0)
    adj = np.empty(m)
    adj[order] = adj_sorted
    return {i: {"p": float(p[j]), "p_adj": float(adj[j]), "m": m, "passed": bool(adj[j] < alpha)}
            for j, i in enumerate(ids)}
