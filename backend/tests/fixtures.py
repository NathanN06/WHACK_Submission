"""Synthetic meals with KNOWN truth, so every test knows the right answer.

Truth: rise = 30 + person offset + 0.6*carbs - 1.5*fiber + noise.
The person offset depends on HbA1c. Protein, fat, sugar, hour_of_day have no effect.
Calories mostly repeats carbs. time_to_peak is built from the outcome (a leak).
"""

import numpy as np
import pandas as pd


def make_meals(n_people: int = 30, meals: int = 40, seed: int = 0,
               fiber_effect: float = -1.5, prefix: str = "P") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for p in range(n_people):
        hba1c = rng.uniform(5.0, 8.0)
        offset = 8 * (hba1c - 6.0) + rng.normal(0, 4)
        carbs = rng.uniform(5, 120, meals)
        fiber = rng.uniform(0, 15, meals)
        protein = rng.uniform(5, 50, meals)
        fat = rng.uniform(2, 40, meals)
        sugar = rng.uniform(0, 40, meals)
        rise = 30 + offset + 0.6 * carbs + fiber_effect * fiber + rng.normal(0, 8, meals)
        frames.append(pd.DataFrame({
            "participant_id": f"{prefix}{p:02d}",
            "meal_event_id": [f"{prefix}{p:02d}-{i:03d}" for i in range(meals)],
            "carbs": carbs,
            "fiber": fiber,
            "protein": protein,
            "fat": fat,
            "sugar": sugar,
            "calories": 4 * carbs + 4 * protein + 9 * fat + rng.normal(0, 20, meals),
            "baseline_glucose": rng.normal(100, 10, meals),
            "hour_of_day": rng.integers(6, 23, meals),
            "hba1c": hba1c,
            "rise": rise,
            "time_to_peak": 30 + 0.4 * rise + rng.normal(0, 3, meals),
        }))
    return pd.concat(frames, ignore_index=True)


def make_sensor_pair(df: pd.DataFrame, seed: int = 0, fiber_on_second: bool = True) -> dict:
    """Two sensors on the same meals. Optionally the second sensor sees no fibre effect."""
    rng = np.random.default_rng(seed + 100)
    second = df.copy()
    second["rise"] = df["rise"] + rng.normal(0, 5, len(df))
    if not fiber_on_second:
        second["rise"] = second["rise"] + 1.5 * df["fiber"]
    return {"libre": df.copy(), "dexcom": second}
