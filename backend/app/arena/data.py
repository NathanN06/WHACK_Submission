"""Load meal-level frames from data/whack.duckdb in the arena's canonical columns.

This is the ONLY file that knows the database's column names. If a name differs
from what `scripts/inspect_schema.py` prints, edit SELECT below. Expressions that
don't resolve are skipped with a warning, and the feature simply never unlocks.
"""

import warnings
from pathlib import Path

import pandas as pd

REQUIRED = ["participant_id", "meal_event_id", "rise", "carbs"]

# canonical column -> SQL expression. r = meal_responses, p = participants.
# meal_responses already carries the macros and timing (copied from meal_events).
SELECT = {
    "participant_id": "r.participant_id",
    "meal_event_id": "CAST(r.meal_event_id AS VARCHAR)",
    "rise": "r.glucose_rise_mgdl",
    "time_to_peak": "r.minutes_to_peak",
    "baseline_glucose": "r.baseline_mgdl",
    "carbs": "r.carbs_g",
    "fiber": "r.fiber_g",
    "protein": "r.protein_g",
    "fat": "r.fat_g",
    "sugar": "r.sugar_g",
    "calories": "r.calories",
    "hour_of_day": "r.hour_of_day",
    "hba1c": "p.hba1c_pct",
    # Gap to the previous real (>= 50 kcal) meal in the same session, from ALL logged
    # meals, not just the clean ones we analyse.
    "hours_since_last_meal": (
        "(SELECT date_diff('minute', max(e.ts), r.meal_ts) / 60.0 FROM meal_events e "
        "WHERE e.session_id = r.session_id AND e.ts < r.meal_ts "
        "AND NOT coalesce(e.calories < 50, false))"),
    # Day III lifestyle, from the minute table (CGMacros only; BUT CGM people get NULL).
    "steps_after": ("(SELECT sum(m.steps) FROM cgmacros_minute m WHERE m.participant_id = r.participant_id "
                    "AND m.ts >= r.meal_ts AND m.ts < r.meal_ts + INTERVAL 2 HOUR)"),
    "hr_after": ("(SELECT avg(m.heart_rate_bpm) FROM cgmacros_minute m WHERE m.participant_id = r.participant_id "
                 "AND m.ts >= r.meal_ts AND m.ts < r.meal_ts + INTERVAL 2 HOUR)"),
}

FROM = """
FROM meal_responses r
LEFT JOIN participants p ON p.participant_id = r.participant_id
"""


def _working_selects(con) -> dict[str, str]:
    ok = {}
    for name, expr in SELECT.items():
        try:
            con.execute(f"SELECT {expr} AS {name} {FROM} LIMIT 0")
            ok[name] = expr
        except Exception as e:  # unknown column or table: skip this feature
            warnings.warn(f"skipping {name}: {str(e).splitlines()[0]}")
    missing = [c for c in REQUIRED if c not in ok]
    if missing:
        raise RuntimeError(f"required columns not found: {missing}. Edit SELECT in data.py.")
    return ok


def _columns_of(con, table: str) -> set[str]:
    return {row[0] for row in con.execute(f"DESCRIBE {table}").fetchall()}


def load_meals(con, id_pattern: str, sensor: str | None = None) -> pd.DataFrame:
    selects = _working_selects(con)
    cols = ",\n  ".join(f"{expr} AS {name}" for name, expr in selects.items())
    where = "WHERE r.clean AND r.participant_id LIKE ?"
    params = [id_pattern]
    if sensor is not None:
        where += " AND r.sensor = ?"
        params.append(sensor)
    df = con.execute(f"SELECT {cols} {FROM} {where} ORDER BY r.meal_event_id", params).df()
    return add_derived(df)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Features computed in pandas from what was loaded (used when SQL didn't provide them)."""
    out = df.copy()
    if "meal_start" in out.columns:
        if "hours_since_last_meal" not in out.columns:
            start = pd.to_datetime(out["meal_start"])
            gaps = (out.assign(_t=start).sort_values(["participant_id", "_t"])
                    .groupby("participant_id")["_t"].diff().dt.total_seconds() / 3600)
            out["hours_since_last_meal"] = gaps.reindex(out.index)
        out = out.drop(columns="meal_start")
    return out


def load_all(db_path: str | Path = "data/whack.duckdb"):
    """Returns (train, test, sensors): CGMacros, BUT CGM, and CGMacros per sensor."""
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    sensors: dict[str, pd.DataFrame] = {}
    if "sensor" in _columns_of(con, "meal_responses"):
        names = [r[0] for r in con.execute(
            "SELECT DISTINCT sensor FROM meal_responses WHERE participant_id LIKE 'CGM-%'").fetchall()]
        sensors = {s: load_meals(con, "CGM-%", s) for s in names}
    train = sensors.get("libre") if sensors else None
    if train is None:
        train = load_meals(con, "CGM-%", next(iter(sensors)) if sensors else None)
    test = load_meals(con, "BUT-%")
    return train, test, sensors if len(sensors) >= 2 else {}
