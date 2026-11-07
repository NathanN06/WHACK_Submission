#!/usr/bin/env python3
"""Build data/whack.duckdb from the raw CSVs downloaded by download_data.py.

Usage:
  .venv/bin/python scripts/build_db.py

The database is rebuilt from scratch on every run (takes a few seconds).

Conventions (apply to every table):
  participant_id  one PERSON, e.g. 'CGM-001' (CGMacros) or 'BUT-101' (BUT CGM).
                  Use this for train/holdout splits - never split by session.
  session_id      one ~10-day measurement period, e.g. 'CGM-001' or 'BUT-101001'.
                  BUT participants 154 and 155 have several sessions each.
  dataset         'cgmacros' or 'but_cgm'
  glucose         always mg/dL (BUT CGM's mmol/L is converted: x 18.016)
  timestamps      local time; both datasets are date-shifted for privacy, so
                  absolute dates are meaningless but within-session timing,
                  time-of-day and weekday are preserved.

Every table and column carries a COMMENT (see `duckdb_tables()` /
`duckdb_columns()`), which is what the AI agent's schema tool shows it.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "whack.duckdb"
CGM_DIR = DATA / "cgmacros" / "CGMacros"
BUT_DIR = DATA / "but-cgm"

MMOL_TO_MGDL = 18.016
# Meal-response window definitions (used by the meal_responses table)
BASELINE_MIN = 15  # minutes before the meal averaged for baseline glucose
RESPONSE_MIN = 120  # minutes after the meal analysed for the glucose response
MEAL_GAP_MIN = 30  # food items logged within this many minutes of the previous item = one meal event
# Quality gates for a meal response (meal_responses.quality_ok)
MIN_BASELINE_READINGS = 2
MIN_COVERAGE_PCT = 70  # readings found / readings expected in the response window
MIN_LAST_READING_MIN = 105  # the window must be observed at least this far
MAX_GAP_MIN = 20  # longest allowed stretch without a reading inside the window
SENSOR_LO, SENSOR_HI = 40, 400  # CGM reporting limits (mg/dL): values at/beyond these are clipped, not real
MIN_MEAL_KCAL = 50  # meal events below this (coffee, water...) are 'minor' and don't confound other meals
EXPECTED_READING_MIN = 5  # primary sensors (Dexcom in both datasets) report every 5 min


def but_csv(pattern: str, **extra: str) -> str:
    """read_csv() expression for BUT CGM's semicolon-separated files."""
    opts = ", ".join(f"{k}={v}" for k, v in extra.items())
    return (
        f"read_csv('{BUT_DIR / pattern}', delim=';', header=true, nullstr='NA', "
        f"filename=true, union_by_name=true{', ' + opts if opts else ''})"
    )


def but_ids(digits6: str) -> tuple[str, str]:
    """(session_id, participant_id) SQL expressions from a 6-digit BUT ID string expression.

    The single place that encodes BUT's ID layout: PPPSSS = 3-digit person + 3-digit session.
    """
    return f"'BUT-' || {digits6}", f"'BUT-' || substr({digits6}, 1, 3)"


# Per-file tables: paths look like .../but-cgm/101001/101001_CGM.csv
BUT_SESSION, BUT_PERSON = but_ids("regexp_extract(filename, '(\\d{6})_[^/]*$', 1)")
# Top-level CSVs: numeric ID column
BUT_SID, BUT_PID = but_ids("lpad(CAST(ID AS VARCHAR), 6, '0')")

STEPS: list[tuple[str, str]] = []  # (table name, SQL) executed in order


def table(name: str, sql: str) -> None:
    STEPS.append((name, f"CREATE OR REPLACE TABLE {name} AS {sql}"))


# --------------------------------------------------------------------------
# CGMacros
# --------------------------------------------------------------------------
CGM_SID = "'CGM-' || regexp_extract(filename, 'CGMacros-(\\d{3})', 1)"
# Staging table: the raw minute CSVs are parsed once and feed both cgmacros_minute and meals.
# Tables starting with '_' are dropped at the end of the build.
CGM_RAW = "_cgm_raw"
table(
    CGM_RAW,
    f"SELECT * FROM read_csv('{CGM_DIR}/CGMacros-*/CGMacros-*.csv', header=true, filename=true, union_by_name=true)",
)

table(
    "cgmacros_minute",
    f"""
    SELECT {CGM_SID} AS session_id, {CGM_SID} AS participant_id,
           "Timestamp" AS ts,
           "Libre GL" AS glucose_libre_mgdl, "Dexcom GL" AS glucose_dexcom_mgdl,
           "HR" AS heart_rate_bpm, "Calories (Activity)" AS activity_kcal,
           "METs" AS mets, "Steps" AS steps, "Intensity" AS intensity
    FROM {CGM_RAW}
    ORDER BY session_id, ts
    """,
)

# ---- participants / sessions -------------------------------------------------
table(
    "cgmacros_bio",
    f"""
    SELECT 'CGM-' || lpad(CAST(subject AS VARCHAR), 3, '0') AS participant_id, *
    FROM read_csv('{CGM_DIR}/bio.csv', header=true, normalize_names=true)
    """,
)
table(
    "gut_health",
    f"""
    SELECT 'CGM-' || lpad(CAST(subject AS VARCHAR), 3, '0') AS participant_id, * EXCLUDE (subject)
    FROM read_csv('{CGM_DIR}/gut_health_test.csv', header=true, normalize_names=true)
    """,
)
table(
    "microbes",
    f"""
    SELECT participant_id, trim(microbe) AS microbe, value
    FROM (
        UNPIVOT (
            SELECT 'CGM-' || lpad(CAST(subject AS VARCHAR), 3, '0') AS participant_id, * EXCLUDE (subject)
            FROM read_csv('{CGM_DIR}/microbes.csv', header=true)
        ) ON COLUMNS(* EXCLUDE (participant_id)) INTO NAME microbe VALUE value
    )
    """,
)

# ---- BUT CGM raw-ish tables ----------------------------------------------------
table(
    "but_subject_info",
    f"SELECT {BUT_SID} AS session_id, {BUT_PID} AS participant_id, * EXCLUDE (ID) "
    f"FROM read_csv('{BUT_DIR / 'subject-info.csv'}', delim=';', header=true, nullstr='NA')",
)
table(
    "daily_questionnaire",
    f"SELECT {BUT_SID} AS session_id, {BUT_PID} AS participant_id, * EXCLUDE (ID) "
    f"FROM read_csv('{BUT_DIR / 'daily_questionnaire.csv'}', delim=';', header=true, nullstr='NA')",
)
table(
    "but_data_completeness",
    f"SELECT {BUT_SID} AS session_id, {BUT_PID} AS participant_id, * EXCLUDE (ID) "
    f"FROM read_csv('{BUT_DIR / 'data_completness.csv'}', delim=';', header=true, nullstr='NA', normalize_names=true)",
)

# ---- unified participants & sessions ----------------------------------------------
table(
    "participants",
    f"""
    SELECT participant_id, 'cgmacros' AS dataset,
           age, gender AS sex, bmi,
           body_weight * 0.45359237 AS weight_kg,   -- lbs -> kg
           height * 2.54 AS height_cm,              -- inches -> cm
           a1c_pdl_lab AS hba1c_pct,
           fasting_glu_pdl_lab AS fasting_glucose_mgdl,
           CASE WHEN a1c_pdl_lab IS NULL THEN NULL
                WHEN a1c_pdl_lab >= 6.5 THEN 'type2_diabetes'
                WHEN a1c_pdl_lab >= 5.7 THEN 'prediabetes'
                ELSE 'healthy' END AS glycemic_status
    FROM cgmacros_bio
    UNION ALL BY NAME
    SELECT participant_id, 'but_cgm' AS dataset,
           any_value(age) AS age, any_value(sex) AS sex, any_value(BMI) AS bmi,
           any_value(weight) AS weight_kg, any_value(height) * 100 AS height_cm,
           NULL AS hba1c_pct, NULL AS fasting_glucose_mgdl,
           'healthy_active' AS glycemic_status
    FROM but_subject_info GROUP BY participant_id
    ORDER BY participant_id
    """,
)
table(
    "sessions",
    f"""
    SELECT session_id, participant_id, 'cgmacros' AS dataset,
           min(ts) AS start_ts, max(ts) AS end_ts,
           date_diff('day', min(ts), max(ts)) + 1 AS n_days
    FROM cgmacros_minute GROUP BY ALL
    UNION ALL
    SELECT {BUT_SID}, {BUT_PID}, 'but_cgm', start, stop, number_of_days
    FROM read_csv('{BUT_DIR / 'measurement_starts_and_ends.csv'}', delim=';', header=true, nullstr='NA')
    ORDER BY session_id
    """,
)

# ---- unified glucose ------------------------------------------------------------------
table(
    "glucose",
    f"""
    -- CGMacros ships both sensors linearly interpolated to 1-min (Libre scans every 15 min,
    -- Dexcom every 5), which hides real gaps. Keep only the real readings: the points where
    -- the straight line bends, plus the ends of each non-NULL run.
    WITH cgm_long AS (
        SELECT session_id, participant_id, ts, 'libre' AS sensor, glucose_libre_mgdl AS v FROM cgmacros_minute
        UNION ALL
        SELECT session_id, participant_id, ts, 'dexcom', glucose_dexcom_mgdl FROM cgmacros_minute
    ),
    nb AS (
        SELECT *, lag(v) OVER w AS pv, lead(v) OVER w AS nv, lag(ts) OVER w AS pts, lead(ts) OVER w AS nts
        FROM cgm_long WINDOW w AS (PARTITION BY session_id, sensor ORDER BY ts)
    )
    SELECT session_id, participant_id, 'cgmacros' AS dataset, ts, sensor, v AS glucose_mgdl
    FROM nb
    WHERE v IS NOT NULL
      AND (pv IS NULL OR nv IS NULL
           OR pts <> ts - INTERVAL 1 MINUTE OR nts <> ts + INTERVAL 1 MINUTE
           OR abs((nv - v) - (v - pv)) > 1e-6)
    UNION ALL
    SELECT {BUT_SESSION}, {BUT_PERSON}, 'but_cgm', "Timestamp", 'dexcom_g7',
           round(Glycemia * {MMOL_TO_MGDL}, 1)
    FROM {but_csv('*/*_CGM.csv')} WHERE Glycemia IS NOT NULL
    ORDER BY session_id, sensor, ts
    """,
)

# ---- unified meals ----------------------------------------------------------------------
table(
    "meals",
    f"""
    WITH m AS (
        SELECT {CGM_SID} AS session_id, {CGM_SID} AS participant_id, 'cgmacros' AS dataset,
               "Timestamp" AS ts,
               CASE WHEN lower(trim("Meal Type")) LIKE 'snack%' THEN 'snack' ELSE lower(trim("Meal Type")) END AS meal_type,
               NULL::VARCHAR AS description,
               Calories AS calories, Carbs AS carbs_g, Protein AS protein_g, Fat AS fat_g,
               Fiber AS fiber_g, Sugar AS sugar_g, "Amount Consumed" AS amount_consumed_raw,
               "Image path" AS image_path
        FROM {CGM_RAW}
        WHERE "Meal Type" IS NOT NULL OR Calories IS NOT NULL
        UNION ALL
        SELECT {BUT_SESSION}, {BUT_PERSON}, 'but_cgm', "Time", NULL, Meal,
               Calories, Carbs, Protein, Fats, NULL, Sugar, NULL, NULL
        FROM {but_csv('*/*_meals.csv')}
    ),
    -- an item logged with all-zero calories and macros is missing nutrition data, not an empty meal
    cleaned AS (
        SELECT * REPLACE (
                   CASE WHEN miss THEN NULL ELSE calories END AS calories,
                   CASE WHEN miss THEN NULL ELSE carbs_g END AS carbs_g,
                   CASE WHEN miss THEN NULL ELSE protein_g END AS protein_g,
                   CASE WHEN miss THEN NULL ELSE fat_g END AS fat_g,
                   CASE WHEN miss THEN NULL ELSE fiber_g END AS fiber_g,
                   CASE WHEN miss THEN NULL ELSE sugar_g END AS sugar_g),
               miss AS nutrition_missing
        FROM (SELECT *, coalesce(calories, 0) = 0 AND coalesce(carbs_g, 0) = 0
                        AND coalesce(protein_g, 0) = 0 AND coalesce(fat_g, 0) = 0 AS miss FROM m)
    ),
    numbered AS (
        SELECT row_number() OVER (ORDER BY session_id, ts, description, image_path, calories, carbs_g,
                                           protein_g, fat_g, meal_type) AS meal_id,
               * EXCLUDE (miss)
        FROM cleaned
    ),
    -- items logged within MEAL_GAP_MIN of the previous item in the session belong to the same meal event
    starts AS (
        SELECT *, CASE WHEN lag(ts) OVER w IS NULL
                         OR ts - lag(ts) OVER w > INTERVAL {MEAL_GAP_MIN} MINUTE THEN 1 ELSE 0 END AS new_event
        FROM numbered WINDOW w AS (PARTITION BY session_id ORDER BY ts, meal_id)
    )
    SELECT meal_id,
           sum(new_event) OVER (ORDER BY session_id, ts, meal_id ROWS UNBOUNDED PRECEDING) AS meal_event_id,
           * EXCLUDE (meal_id, new_event)
    FROM starts ORDER BY meal_id
    """,
)
table(
    "meal_events",
    """
    SELECT meal_event_id, any_value(session_id) AS session_id, any_value(participant_id) AS participant_id,
           any_value(dataset) AS dataset, min(ts) AS ts, max(ts) AS last_item_ts, count(*) AS n_items,
           first(meal_type ORDER BY ts) FILTER (WHERE meal_type IS NOT NULL) AS meal_type,
           string_agg(description, ' + ' ORDER BY ts, meal_id) AS description,
           bool_or(nutrition_missing) AS nutrition_missing,
           -- totals are NULL if any item's nutrition is missing (a partial sum would understate the meal)
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(calories) END AS calories,
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(carbs_g) END AS carbs_g,
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(protein_g) END AS protein_g,
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(fat_g) END AS fat_g,
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(fiber_g) END AS fiber_g,
           CASE WHEN NOT bool_or(nutrition_missing) THEN sum(sugar_g) END AS sugar_g
    FROM meals GROUP BY meal_event_id ORDER BY meal_event_id
    """,
)

# ---- BUT CGM lifestyle tables -----------------------------------------------------------
table(
    "activities",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
           "Activity Type" AS activity_type, try_cast("Date" AS TIMESTAMP) AS start_ts,
           epoch(try_cast(Duration AS INTERVAL)) / 60.0 AS duration_min,
           try_cast("Zone 1" AS DOUBLE) AS zone1_min,
           try_cast("Zone 2" AS DOUBLE) AS zone2_min,
           try_cast("Zone 3" AS DOUBLE) AS zone3_min,
           Note AS session_type
    FROM {but_csv('*/*_activities.csv', all_varchar='true')}
    ORDER BY session_id, start_ts
    """,
)
table(
    "sleep",
    f"""
    SELECT session_id, participant_id, wake_date,
           CASE WHEN st > en THEN wake_date - 1 + st ELSE wake_date + st END AS sleep_start_ts,
           wake_date + en AS sleep_end_ts,
           duration_min
    FROM (
        SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
               try_cast("Date" AS DATE) AS wake_date,
               try_cast(Sleep_Start AS TIME) AS st, try_cast(Sleep_End AS TIME) AS en,
               try_cast(Duration_Minutes AS DOUBLE) AS duration_min
        FROM {but_csv('*/*_sleep.csv', all_varchar='true')}
    )
    WHERE wake_date IS NOT NULL AND st IS NOT NULL AND en IS NOT NULL
    ORDER BY session_id, wake_date
    """,
)
table(
    "daily_steps",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
           CAST("Date" AS DATE) AS date, Steps AS steps
    FROM {but_csv('*/*_daily_steps_summary.csv')} ORDER BY session_id, date
    """,
)
table(
    "daily_nutrition",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
           CAST("Date" AS DATE) AS date, Calories AS calories, Protein AS protein_g,
           Carbs AS carbs_g, Sugar AS sugar_g, Fats AS fat_g
    FROM {but_csv('*/*_daily_meal_summary.csv')} ORDER BY session_id, date
    """,
)
table(
    "cpet_data",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
           try_cast(split_part(t, ':', 1) AS DOUBLE) * 60 + try_cast(split_part(t, ':', 2) AS DOUBLE) AS t_seconds,
           * EXCLUDE (filename, t)
    FROM {but_csv('*/*_CPET_data.csv')}
    """,
)
table(
    "cpet_summary",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id,
           "Data" AS feature, Unit AS unit, VT1 AS vt1, VT2 AS vt2, VO2peak AS vo2peak
    FROM {but_csv('*/*_CPET_summary.csv', all_varchar='true')}
    """,
)
table(
    "cpet_metadata",
    f"""
    SELECT {BUT_SESSION} AS session_id, {BUT_PERSON} AS participant_id, Field AS field, "Value" AS value
    FROM {but_csv('*/*_CPET_metadata.csv', all_varchar='true')}
    """,
)

# ---- derived: glucose response to each meal -----------------------------------------------
# Primary sensor: Dexcom in both datasets (CGMacros 'dexcom', BUT 'dexcom_g7'). Both report every
# 5 min, so the quality gates mean the same thing in both. (CGMacros Libre only scans every 15 min
# and several Libre sensors are stuck at the 40 mg/dL floor for long stretches.)
table(
    "meal_responses",
    f"""
    WITH g AS (
        SELECT * FROM glucose WHERE sensor IN ('dexcom', 'dexcom_g7')
    ),
    ev AS (
        SELECT *, {RESPONSE_MIN} // {EXPECTED_READING_MIN} AS expected_readings FROM meal_events
    ),
    sess AS (SELECT DISTINCT session_id FROM g),
    base AS (
        SELECT e.meal_event_id, avg(g.glucose_mgdl) AS baseline_mgdl, count(*) AS n_baseline_readings,
               bool_or(g.glucose_mgdl <= {SENSOR_LO} OR g.glucose_mgdl >= {SENSOR_HI}) AS base_clipped
        FROM ev e JOIN g ON g.session_id = e.session_id
         AND g.ts BETWEEN e.ts - INTERVAL {BASELINE_MIN} MINUTE AND e.ts
        GROUP BY e.meal_event_id
    ),
    post AS (
        SELECT e.meal_event_id, g.glucose_mgdl,
               date_diff('second', e.ts, g.ts) / 60.0 AS t,
               greatest(g.glucose_mgdl - b.baseline_mgdl, 0) AS inc  -- NULL when there is no baseline
        FROM ev e JOIN g ON g.session_id = e.session_id
         AND g.ts > e.ts AND g.ts <= e.ts + INTERVAL {RESPONSE_MIN} MINUTE
        LEFT JOIN base b ON b.meal_event_id = e.meal_event_id
    ),
    seg AS (  -- each reading paired with the previous one; the curve starts at baseline at t = 0
        SELECT *, lag(t, 1, 0.0) OVER w AS t_prev, lag(inc, 1, 0.0) OVER w AS inc_prev
        FROM post WINDOW w AS (PARTITION BY meal_event_id ORDER BY t)
    ),
    agg AS (
        SELECT meal_event_id,
               count(*) AS n_readings,
               max(glucose_mgdl) AS peak_mgdl,
               arg_max(t, glucose_mgdl) AS minutes_to_peak,
               max(t) AS last_reading_min,
               greatest(max(t - t_prev), {RESPONSE_MIN} - max(t)) AS max_gap_min,
               bool_or(glucose_mgdl <= {SENSOR_LO} OR glucose_mgdl >= {SENSOR_HI}) AS post_clipped,
               -- trapezoid rule over actual reading times, last value carried to the end of the window
               sum((t - t_prev) * (inc + inc_prev) / 2) + ({RESPONSE_MIN} - max(t)) * arg_max(inc, t) AS iauc_2h
        FROM seg GROUP BY meal_event_id
    ),
    j AS (
        SELECT e.*, b.baseline_mgdl, coalesce(b.n_baseline_readings, 0) AS n_baseline_readings,
               coalesce(a.n_readings, 0) AS n_readings,
               round(100.0 * coalesce(a.n_readings, 0) / e.expected_readings, 1) AS coverage_pct,
               a.last_reading_min, coalesce(a.max_gap_min, {RESPONSE_MIN}) AS max_gap_min,
               a.peak_mgdl, a.minutes_to_peak, a.iauc_2h,
               coalesce(b.base_clipped, false) OR coalesce(a.post_clipped, false) AS clipped,
               e.session_id IN (SELECT session_id FROM sess) AS session_has_glucose
        FROM ev e LEFT JOIN base b USING (meal_event_id) LEFT JOIN agg a USING (meal_event_id)
    ),
    q AS (
        SELECT *, CASE
                    WHEN NOT session_has_glucose THEN 'no_glucose_in_session'
                    WHEN n_baseline_readings = 0 AND n_readings = 0 THEN 'no_glucose_near_meal'
                    WHEN n_baseline_readings = 0 THEN 'no_baseline'
                    WHEN n_baseline_readings < {MIN_BASELINE_READINGS} THEN 'sparse_baseline'
                    WHEN coverage_pct < {MIN_COVERAGE_PCT} THEN 'low_coverage'
                    WHEN last_reading_min < {MIN_LAST_READING_MIN} THEN 'truncated'
                    WHEN max_gap_min > {MAX_GAP_MIN} THEN 'gappy'
                    WHEN clipped THEN 'sensor_limit'
                  END AS exclusion_reason
        FROM j
    ),
    -- events that count as "another meal" for confounding: not minor (unknown calories count, to be safe)
    real_ev AS (SELECT * FROM meal_events WHERE calories IS NULL OR calories >= {MIN_MEAL_KCAL})
    SELECT *,
           prior_meal_within_window OR later_meal_within_window OR long_event AS confounded,
           quality_ok AND NOT (prior_meal_within_window OR later_meal_within_window OR long_event)
             AND NOT minor_event AND NOT nutrition_missing AS clean
    FROM (
    SELECT q.meal_event_id, q.session_id, q.participant_id, q.dataset, q.ts AS meal_ts,
           hour(q.ts) AS hour_of_day, dayofweek(q.ts) AS day_of_week,
           q.meal_type, q.description, q.n_items, q.nutrition_missing,
           q.calories, q.carbs_g, q.protein_g, q.fat_g, q.fiber_g, q.sugar_g,
           coalesce(q.calories < {MIN_MEAL_KCAL}, false) AS minor_event,
           date_diff('minute', q.ts, q.last_item_ts) > {MEAL_GAP_MIN} AS long_event,
           q.baseline_mgdl,
           CASE WHEN ok THEN q.peak_mgdl END AS peak_mgdl,
           CASE WHEN ok THEN q.peak_mgdl - q.baseline_mgdl END AS glucose_rise_mgdl,
           CASE WHEN ok THEN q.minutes_to_peak END AS minutes_to_peak,
           CASE WHEN ok THEN q.iauc_2h END AS iauc_2h,
           q.n_baseline_readings, q.n_readings, q.coverage_pct, q.last_reading_min, q.max_gap_min,
           ok AS quality_ok, q.exclusion_reason,
           EXISTS (SELECT 1 FROM real_ev o WHERE o.session_id = q.session_id
                   AND o.meal_event_id <> q.meal_event_id
                   AND o.ts < q.ts AND o.last_item_ts >= q.ts - INTERVAL {RESPONSE_MIN} MINUTE) AS prior_meal_within_window,
           EXISTS (SELECT 1 FROM real_ev o WHERE o.session_id = q.session_id
                   AND o.meal_event_id <> q.meal_event_id
                   AND o.ts >= q.ts AND o.ts <= q.ts + INTERVAL {RESPONSE_MIN} MINUTE) AS later_meal_within_window
    FROM (SELECT *, exclusion_reason IS NULL AS ok FROM q) q
    ) ORDER BY meal_event_id
    """,
)

# --------------------------------------------------------------------------
# Documentation (COMMENT ON) - this is what the agent sees in the schema
# --------------------------------------------------------------------------
TABLE_DOCS = {
    "participants": "One row per PERSON across both datasets. Split train/holdout on participant_id.",
    "sessions": "One row per ~10-day measurement period. BUT participants 154/155 have several sessions.",
    "glucose": "Real CGM readings in mg/dL, long format. CGMacros: 'dexcom' (~5-min) and 'libre' (~15-min scans; several Libre sensors sit at the 40 mg/dL floor for long stretches - prefer dexcom); BUT CGM: 'dexcom_g7' (5-min). CGMacros' interpolated minute values are only in cgmacros_minute.",
    "meals": "Every logged food item from both datasets with macronutrients (BUT CGM often logs one meal as several items). CGMacros has meal_type and photos; BUT CGM has free-text Czech descriptions. Items logged with all-zero nutrition have NULL macros and nutrition_missing = TRUE.",
    "meal_events": f"One row per eating occasion: food items in a session logged within {MEAL_GAP_MIN} min of the previous item are merged, macros summed (NULL if any item's nutrition is missing).",
    "meal_responses": f"DERIVED: one row per meal EVENT (every event, none dropped) with the glucose response from Dexcom in both datasets (CGMacros 'dexcom', BUT 'dexcom_g7'; both 5-min). Baseline = mean of {BASELINE_MIN} min before; response window = {RESPONSE_MIN} min after. Response outcomes are NULL unless quality_ok. For meal-effect analyses use WHERE clean.",
    "cgmacros_minute": "CGMacros minute-level wearable data: both CGM sensors (LINEARLY INTERPOLATED to 1-min - the interpolation also bridges sensor gaps; use the glucose table for real readings), heart rate, activity calories, METs, steps.",
    "cgmacros_bio": "CGMacros raw participant bio/lab sheet (all original columns, names normalised). Weight in lbs, height in inches.",
    "gut_health": "CGMacros gut-health test scores per participant (categorical 1-3 scores). Includes CGM-024 and CGM-025, who have no bio, glucose or meal data.",
    "microbes": "CGMacros gut microbiome, long format: one row per participant x microbe. Not every participant has microbiome data.",
    "but_subject_info": "BUT CGM raw entry questionnaire (one row per session). See column comments for coding.",
    "daily_questionnaire": "BUT CGM daily self-report questionnaire (load, illness, sleep quality, menstruation...). See column comments for coding.",
    "but_data_completeness": "BUT CGM: which data modalities are present/complete per session.",
    "activities": "BUT CGM exercise sessions with minutes in each training-intensity zone (zones from the participant's CPET test).",
    "sleep": "BUT CGM nightly sleep: start/end timestamps and duration. Nights logged without start/end times are omitted.",
    "daily_steps": "BUT CGM daily step totals.",
    "daily_nutrition": "BUT CGM daily macronutrient totals.",
    "cpet_data": "BUT CGM cardiopulmonary exercise test time series (breath-by-breath-ish), one test per participant. Not every session has a CPET test.",
    "cpet_summary": "BUT CGM CPET values at ventilatory thresholds VT1, VT2 and at VO2peak (text, with units).",
    "cpet_metadata": "BUT CGM CPET test/environment metadata as field/value pairs.",
}

COLUMN_DOCS = {
    ("*", "participant_id"): "Person ID ('CGM-001', 'BUT-101'). Use for train/holdout splits.",
    ("*", "session_id"): "Measurement-period ID ('CGM-001', 'BUT-101001').",
    ("*", "dataset"): "'cgmacros' or 'but_cgm'.",
    ("participants", "glycemic_status"): "CGMacros: from HbA1c (<5.7 healthy, 5.7-6.4 prediabetes, >=6.5 type2_diabetes). BUT CGM: all healthy active adults.",
    ("participants", "hba1c_pct"): "HbA1c % (CGMacros only).",
    ("glucose", "sensor"): "'libre' | 'dexcom' (CGMacros, both worn simultaneously) | 'dexcom_g7' (BUT CGM).",
    ("glucose", "glucose_mgdl"): "Interstitial glucose in mg/dL.",
    ("meals", "amount_consumed_raw"): "CGMacros raw 'Amount Consumed' field. NOT a clean percentage: mixes scales (mostly 100; also 1-6 and 200-600, likely servings) and 0. Macros are as logged, not scaled by it. Avoid in analyses.",
    ("*", "nutrition_missing"): "TRUE if the item (or any item in the event) was logged with all-zero calories and macros, which are then NULL.",
    ("meal_responses", "minor_event"): f"TRUE if the event has < {MIN_MEAL_KCAL} kcal (coffee, water...). Minor events don't count as confounders for other meals.",
    ("meal_responses", "long_event"): f"TRUE if the event's items span more than {MEAL_GAP_MIN} min, so food eaten during the response window is part of the event.",
    ("meal_responses", "clean"): "quality_ok AND NOT confounded AND NOT minor_event AND NOT nutrition_missing. Default filter for meal-effect hypotheses.",
    ("meals", "image_path"): "CGMacros: relative path of the meal photo inside the participant folder.",
    ("*", "meal_event_id"): f"Eating-occasion ID: food items logged within {MEAL_GAP_MIN} min of each other share one. Join meals <-> meal_events <-> meal_responses.",
    ("meal_events", "ts"): "Time of the first food item of the event.",
    ("meal_events", "last_item_ts"): "Time of the last food item of the event.",
    ("*", "n_items"): "Number of logged food items merged into this meal event.",
    ("meal_responses", "meal_ts"): "Time of the first food item of the meal event.",
    ("meal_responses", "baseline_mgdl"): f"Mean glucose in the {BASELINE_MIN} min up to the meal.",
    ("meal_responses", "peak_mgdl"): f"Max glucose within {RESPONSE_MIN} min after the meal. NULL unless quality_ok.",
    ("meal_responses", "glucose_rise_mgdl"): f"Peak minus baseline within {RESPONSE_MIN} min after the meal. Main outcome for most hypotheses. Can be NEGATIVE when glucose only fell (don't log-transform; iauc_2h is 0 then). NULL unless quality_ok.",
    ("meal_responses", "minutes_to_peak"): "Minutes from meal to peak glucose. NULL unless quality_ok.",
    ("meal_responses", "iauc_2h"): f"Incremental area under the glucose curve above baseline over {RESPONSE_MIN} min (mg/dL x min), trapezoid rule over actual reading times. NULL unless quality_ok.",
    ("meal_responses", "n_baseline_readings"): "Glucose readings used for the baseline.",
    ("meal_responses", "n_readings"): f"Glucose readings in the response window (expected {RESPONSE_MIN // EXPECTED_READING_MIN}, one per {EXPECTED_READING_MIN} min).",
    ("meal_responses", "coverage_pct"): "n_readings as % of the readings expected in the response window.",
    ("meal_responses", "last_reading_min"): "Minutes after the meal of the last reading in the window.",
    ("meal_responses", "max_gap_min"): "Longest stretch (min) without a reading in the response window, including its start and end.",
    ("meal_responses", "quality_ok"): f"TRUE if >= {MIN_BASELINE_READINGS} baseline readings, coverage >= {MIN_COVERAGE_PCT}%, last reading >= {MIN_LAST_READING_MIN} min, no gap > {MAX_GAP_MIN} min and no reading at the sensor limits (<= {SENSOR_LO} or >= {SENSOR_HI} mg/dL).",
    ("meal_responses", "exclusion_reason"): "Why quality_ok is FALSE: no_glucose_in_session | no_glucose_near_meal | no_baseline | sparse_baseline | low_coverage | truncated | gappy | sensor_limit. NULL if OK.",
    ("meal_responses", "prior_meal_within_window"): f"TRUE if another (non-minor) meal event happened in the {RESPONSE_MIN} min before - baseline/rise contaminated.",
    ("meal_responses", "later_meal_within_window"): f"TRUE if another (non-minor) meal event started within the {RESPONSE_MIN} min response window.",
    ("meal_responses", "confounded"): "prior_meal_within_window OR later_meal_within_window OR long_event.",
    ("meal_responses", "day_of_week"): "0 = Sunday ... 6 = Saturday.",
    ("meal_responses", "hour_of_day"): "Local hour (0-23) of the meal.",
    ("*", "meal_type"): "CGMacros only: breakfast | lunch | dinner | snack. NULL for BUT CGM.",
    ("*", "description"): "BUT CGM only: free-text (Czech) food description; items of an event joined with ' + '.",
    ("*", "calories"): "kcal as logged. NULL if nutrition is missing.",
    ("*", "carbs_g"): "Carbohydrates (g) as logged.",
    ("*", "protein_g"): "Protein (g) as logged.",
    ("*", "fat_g"): "Fat (g) as logged.",
    ("*", "fiber_g"): "Fiber (g); CGMacros only.",
    ("*", "sugar_g"): "Sugar (g) as logged.",
    ("activities", "session_type"): "basic / tempo / interval.",
    ("sleep", "wake_date"): "Date the participant woke up.",
}


def _sql_str(s: str) -> str:
    """Quote a Python string as a SQL string literal (COMMENT ON doesn't accept parameters)."""
    return "'" + s.replace("'", "''") + "'"


def load_codebooks(con: duckdb.DuckDBPyConnection) -> None:
    """Attach BUT CGM codebook descriptions as column comments."""
    mapping = {
        "subject-info_code.csv": "but_subject_info",
        "daily_questionnaire_code.csv": "daily_questionnaire",
        "data_completness_code.csv": "but_data_completeness",
    }
    for fname, tbl in mapping.items():
        path = BUT_DIR / fname
        if not path.exists():
            continue
        cols = {r[0] for r in con.execute(f"SELECT column_name FROM duckdb_columns() WHERE table_name = '{tbl}'").fetchall()}
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                var = (row.get("Variable") or "").strip()
                # data_completeness column names were normalised (spaces -> underscores, lowercase)
                candidates = [var, var.lower().replace(" ", "_")]
                col = next((c for c in candidates if c in cols), None)
                if col:
                    # DictReader gives None (not the default) for missing trailing fields
                    text = f"{(row.get('Description') or '').strip()}. Coding: {(row.get('Coding') or '').strip()}"
                    con.execute(f'COMMENT ON COLUMN {tbl}."{col}" IS {_sql_str(text)}')


def add_comments(con: duckdb.DuckDBPyConnection) -> None:
    q = _sql_str
    for tbl, doc in TABLE_DOCS.items():
        con.execute(f"COMMENT ON TABLE {tbl} IS {q(doc)}")
    all_cols = con.execute("SELECT table_name, column_name FROM duckdb_columns() WHERE schema_name = 'main'").fetchall()
    for tbl, col in all_cols:
        doc = COLUMN_DOCS.get((tbl, col)) or COLUMN_DOCS.get(("*", col))
        if doc:
            con.execute(f'COMMENT ON COLUMN {tbl}."{col}" IS {q(doc)}')
    load_codebooks(con)


def main() -> int:
    if not CGM_DIR.exists() or not BUT_DIR.exists():
        print("Raw data missing - run: python3 scripts/download_data.py", file=sys.stderr)
        return 1
    tmp = DB_PATH.with_suffix(".building.duckdb")
    wal = tmp.with_name(tmp.name + ".wal")

    def clean_tmp() -> None:
        tmp.unlink(missing_ok=True)
        wal.unlink(missing_ok=True)

    clean_tmp()
    t0 = time.time()
    ok = False
    con = duckdb.connect(str(tmp))
    try:
        for name, sql in STEPS:
            t = time.time()
            con.execute(sql)
            n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            print(f"  {name:<24} {n:>10,} rows  ({time.time() - t:.1f}s)")
        for (name,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE table_name LIKE '\\_%' ESCAPE '\\'").fetchall():
            con.execute(f"DROP TABLE {name}")  # staging tables
        add_comments(con)
        ok = True
    finally:
        con.close()
        if not ok:
            clean_tmp()
            print("Build failed - nothing written; existing database left untouched.", file=sys.stderr)
    # a WAL left by a crashed reader of the old DB would be replayed onto the new one
    DB_PATH.with_name(DB_PATH.name + ".wal").unlink(missing_ok=True)
    tmp.replace(DB_PATH)  # atomic swap so a failed build never leaves a half-built DB
    print(f"Built {DB_PATH.relative_to(ROOT)} in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
