"""Decoys: fake gladiators whose true nature we know, so the arena can be scored.

Decoy columns are attached to sandbox copies of the data, never the real tables.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import Feature

LEAK = "meal_intensity_score"
NOISE = "lucky_charm"
LUCKY = "moon_phase"
COPYCAT = "carb_load_index"
EMPEROR = "emperors_choice"
PLANT_STRENGTH = 0.25  # in standard deviations of the target per 1 SD of the plant


@dataclass
class DecoyPlan:
    lucky_source: int  # which random draw scored best at the Trial
    emperor: str | None  # "real", "fake" or None
    seed: int


DECOY_FEATURES = [
    Feature(NOISE, 4, "before_meal", "Lucky charm worn at the meal (0 or 1)"),
    Feature(LUCKY, 4, "before_meal", "Moon phase on the day of the meal"),
    Feature(LEAK, 4, "outcome", "Composite intensity score for the meal"),
    Feature(COPYCAT, 4, "before_meal", "Carbohydrate load index"),
    Feature(EMPEROR, 4, "before_meal", "The Emperor's secret ingredient"),
]

CLAIMS = {
    NOISE: "Wearing a lucky charm lowers the rise",
    LUCKY: "The moon phase changes the rise",
    LEAK: "The meal intensity score predicts the rise",
    COPYCAT: "The carb load index adds to carbs",
    EMPEROR: "The Emperor's secret ingredient moves the rise",
}


N_LUCKY_DRAWS = 100


def lucky_gains(train: pd.DataFrame, target: str, seed: int) -> np.ndarray:
    """Trial score (cross-validated gain over carbs) of each of 100 pure-noise columns."""
    from .engine import PID, _cv_gain_per_person  # local import: engine is the measuring stick

    draws = np.random.default_rng(seed).normal(size=(N_LUCKY_DRAWS, len(train)))
    keep = train[[PID, target, "carbs"]].notna().all(axis=1).to_numpy()
    d = train.loc[keep, [PID, target, "carbs"]].reset_index(drop=True)
    gains = []
    for x in draws:
        d["_noise"] = x[keep]
        gains.append(_cv_gain_per_person(d, target, ["carbs"], ["carbs", "_noise"]).mean())
    return np.array(gains)


def plan(train: pd.DataFrame, target: str, emperor: str | None, seed: int) -> DecoyPlan:
    """Pick the lucky winner: the noise column that scores best at the Trial out of 100.

    This is the garden of forking paths: try enough random ideas and one will
    look like a discovery. Only people it has never seen can unmask it.
    """
    best = int(np.argmax(lucky_gains(train, target, seed)))
    return DecoyPlan(lucky_source=best, emperor=emperor, seed=seed)


def attach(frame: pd.DataFrame, target: str, p: DecoyPlan, salt: int = 0,
           like: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return a sandbox copy of `frame` with decoy columns.

    - The training frame: salt=0, like=None (the lucky winner matches `plan`).
    - Another sensor on the same meals: like=<decorated training frame>, so
      every meal keeps the same decoy values (matched on meal_event_id).
    - The holdout population: salt=1, like=None (fresh draws, same rules).
    The leak and the copycat are always rebuilt from the frame's own columns.
    """
    out = frame.copy()
    n = len(out)
    rng = np.random.default_rng(p.seed + 1000 * (salt + 1))
    if like is not None:
        keyed = like.set_index("meal_event_id")
        for c in [LUCKY, NOISE] + ([EMPEROR] if p.emperor else []):
            out[c] = out["meal_event_id"].map(keyed[c]).to_numpy(float)
    else:
        draw_rng = np.random.default_rng(p.seed) if salt == 0 else rng
        draws = draw_rng.normal(size=(N_LUCKY_DRAWS, n))
        out[LUCKY] = draws[p.lucky_source]
        out[NOISE] = rng.integers(0, 2, n).astype(float)
        if p.emperor:
            out[EMPEROR] = rng.normal(size=n)
    y = out[target].to_numpy(float)
    if p.emperor == "real":
        y = y + PLANT_STRENGTH * np.nanstd(y) * out[EMPEROR].to_numpy(float)
        out[target] = y
    out[LEAK] = 0.8 * y + rng.normal(0, 0.2 * np.nanstd(y), n)
    out[COPYCAT] = 1.1 * out["carbs"].to_numpy(float) + rng.normal(0, 0.5, n)
    return out


def caught(name: str, status: str, emperor: str | None = None) -> bool:
    """Did the arena reach the right answer for this decoy?"""
    dead = status in ("dead", "dropped", "fallen")
    if name == EMPEROR:
        return (not dead) if emperor == "real" else dead
    return dead
