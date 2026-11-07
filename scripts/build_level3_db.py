#!/usr/bin/env python3
"""Create a NEW level-three CGMacros database, separate from data/whack.duckdb.

Run: python scripts/build_level3_db.py
Optional: --source-csv path/to/readings.csv --output data/level3_health_run2.sqlite3

Default output: data/level3_health.sqlite3. Existing files are never overwritten.
Both raw timestamped readings and daily aggregates use participant/date dimensions.
The default input streams all CGMacros participant CSVs without saving the ZIP.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import math
import os
from pathlib import Path
import sqlite3

if __package__:
    from .download_data import CGMACROS_URL, iter_cgmacros_csvs
else:
    from download_data import CGMACROS_URL, iter_cgmacros_csvs

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "level3_health.sqlite3"
EXISTING_DB = ROOT / "data" / "whack.duckdb"
ALIASES = {
    "Timestamp": "timestamp", "Libre GL": "libre_glucose_mg_dl",
    "Dexcom GL": "dexcom_glucose_mg_dl", "HR": "heart_rate_bpm",
    "Calories (Activity)": "activity_calories_kcal", "METs": "mets_times_10",
    "Mets": "mets_times_10", "Steps": "steps", "Intensity": "intensity",
    "Meal Type": "meal_type", "Calories": "meal_calories_kcal",
    "Carbs": "carbs_g", "Protein": "protein_g", "Fat": "fat_g",
    "Fiber": "fiber_g", "Sugar": "sugar", "Amount Consumed": "amount_consumed_percent",
    "Image path": "meal_image_path", "Image Path": "meal_image_path",
    "RecordIndex": "source_record_index",
}
VALUE_COLUMNS = (
    "heart_rate_bpm", "libre_glucose_mg_dl", "dexcom_glucose_mg_dl",
    "activity_calories_kcal", "mets_times_10", "steps", "intensity",
    "meal_type", "meal_calories_kcal", "carbs_g", "protein_g", "fat_g",
    "fiber_g", "sugar", "amount_consumed_percent", "meal_image_path", "source_record_index",
)
TEXT_COLUMNS = {"meal_type", "meal_image_path"}
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE dataset_metadata (
    data_level INTEGER PRIMARY KEY CHECK (data_level = 3),
    dataset TEXT NOT NULL,
    source_url TEXT NOT NULL,
    input_source TEXT NOT NULL,
    built_at_utc TEXT NOT NULL
);
CREATE TABLE dim_participant (
    participant_id TEXT PRIMARY KEY NOT NULL,
    username TEXT UNIQUE NOT NULL,
    source_participant_id INTEGER UNIQUE NOT NULL,
    dataset TEXT NOT NULL
);
CREATE TABLE dim_date (
    date TEXT PRIMARY KEY NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    weekday_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);
CREATE TABLE fact_health_reading (
    participant_id TEXT NOT NULL REFERENCES dim_participant(participant_id),
    date TEXT NOT NULL REFERENCES dim_date(date),
    timestamp TEXT NOT NULL CHECK (date = substr(timestamp, 1, 10)),
    heart_rate_bpm REAL,
    libre_glucose_mg_dl REAL,
    dexcom_glucose_mg_dl REAL,
    activity_calories_kcal REAL,
    mets_times_10 REAL,
    steps REAL,
    intensity REAL,
    meal_type TEXT,
    meal_calories_kcal REAL,
    carbs_g REAL,
    protein_g REAL,
    fat_g REAL,
    fiber_g REAL,
    sugar REAL,
    amount_consumed_percent REAL,
    meal_image_path TEXT,
    source_record_index INTEGER,
    PRIMARY KEY (participant_id, timestamp)
);
CREATE INDEX health_reading_by_day ON fact_health_reading(participant_id, date);
CREATE TABLE fact_daily_health (
    participant_id TEXT NOT NULL REFERENCES dim_participant(participant_id),
    date TEXT NOT NULL REFERENCES dim_date(date),
    measurement_row_count INTEGER NOT NULL,
    mean_heart_rate_bpm REAL,
    heart_rate_reading_count INTEGER NOT NULL,
    mean_libre_glucose_mg_dl REAL,
    libre_glucose_reading_count INTEGER NOT NULL,
    mean_dexcom_glucose_mg_dl REAL,
    dexcom_glucose_reading_count INTEGER NOT NULL,
    mean_mets_times_10 REAL,
    recorded_activity_calories_kcal REAL,
    activity_reading_count INTEGER NOT NULL,
    recorded_steps REAL,
    steps_reading_count INTEGER NOT NULL,
    mean_intensity REAL,
    intensity_reading_count INTEGER NOT NULL,
    recorded_meal_count INTEGER NOT NULL,
    recorded_meal_calories_kcal REAL,
    recorded_carbs_g REAL,
    recorded_protein_g REAL,
    recorded_fat_g REAL,
    recorded_fiber_g REAL,
    recorded_sugar REAL,
    sugar_meal_count INTEGER NOT NULL,
    PRIMARY KEY (participant_id, date)
);
CREATE INDEX daily_health_by_date ON fact_daily_health(date);
"""
DAILY_SQL = """
INSERT INTO fact_daily_health
SELECT participant_id, date, COUNT(*),
       AVG(heart_rate_bpm), COUNT(heart_rate_bpm),
       AVG(libre_glucose_mg_dl), COUNT(libre_glucose_mg_dl),
       AVG(dexcom_glucose_mg_dl), COUNT(dexcom_glucose_mg_dl),
       AVG(mets_times_10), SUM(activity_calories_kcal), COUNT(activity_calories_kcal),
       SUM(steps), COUNT(steps), AVG(intensity), COUNT(intensity), COUNT(meal_type),
       SUM(CASE WHEN meal_type IS NOT NULL THEN meal_calories_kcal END),
       SUM(CASE WHEN meal_type IS NOT NULL THEN carbs_g END),
       SUM(CASE WHEN meal_type IS NOT NULL THEN protein_g END),
       SUM(CASE WHEN meal_type IS NOT NULL THEN fat_g END),
       SUM(CASE WHEN meal_type IS NOT NULL THEN fiber_g END),
       SUM(CASE WHEN meal_type IS NOT NULL THEN sugar END),
       COUNT(CASE WHEN meal_type IS NOT NULL THEN sugar END)
FROM fact_health_reading GROUP BY participant_id, date;
"""


def _missing(value):
    return value is None or str(value).strip().lower() in ("", "nan", "na", "null", "none")


def _reading(row, source_id=None):
    row = {ALIASES.get(key.strip(), key.strip()): value for key, value in row.items() if key is not None}
    value = source_id if source_id is not None else row.get("source_participant_id", row.get("participant_id"))
    if isinstance(value, str) and value.startswith("CGM-"):
        value = value[4:]
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid source participant ID: {value!r}") from None
    if not math.isfinite(number) or not number.is_integer() or number < 1:
        raise ValueError(f"Invalid source participant ID: {value!r}")
    source_id = int(number)
    text = row.get("timestamp") or ""
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
            try:
                timestamp = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid timestamp for CGM-{source_id:03d}: {text!r}")
    values = []
    for column in VALUE_COLUMNS:
        value = row.get(column)
        if _missing(value):
            values.append(None)
        elif column in TEXT_COLUMNS:
            values.append(value.strip())
        else:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"Invalid {column} for CGM-{source_id:03d}: {value!r}")
            values.append(number)
    return source_id, timestamp, tuple(values)


def _source_rows(source_csv=None):
    if source_csv is not None:
        with Path(source_csv).open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                yield _reading(row)
    else:
        for source_id, content in iter_cgmacros_csvs():
            print(f"Loading CGM-{source_id:03d}...", flush=True)
            for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
                yield _reading(row, source_id)


def build_level3_database(output=DEFAULT_DB, source_csv=None):
    """Create a separate database; refuse every pre-existing output file."""
    output = Path(output).resolve()
    if output == EXISTING_DB.resolve():
        raise ValueError("The level-three builder cannot target data/whack.duckdb.")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    connection = None
    try:
        connection = sqlite3.connect(output)
        connection.executescript(SCHEMA)
        users_seen, dates_seen = set(), set()
        batch = []
        placeholders = ", ".join("?" for _ in range(3 + len(VALUE_COLUMNS)))
        insert_sql = f"INSERT INTO fact_health_reading VALUES ({placeholders})"
        with connection:
            connection.execute(
                "INSERT INTO dataset_metadata VALUES (3, ?, ?, ?, ?)",
                ("cgmacros", CGMACROS_URL, str(source_csv or CGMACROS_URL), datetime.now(timezone.utc).isoformat()),
            )
            for source_id, timestamp, values in _source_rows(source_csv):
                participant = f"CGM-{source_id:03d}"
                date = timestamp.date()
                if source_id not in users_seen:
                    connection.execute("INSERT INTO dim_participant VALUES (?, ?, ?, ?)",
                                       (participant, f"participant_{source_id:03d}", source_id, "cgmacros"))
                    users_seen.add(source_id)
                if date not in dates_seen:
                    connection.execute("INSERT INTO dim_date VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                       (date.isoformat(), date.year, (date.month - 1) // 3 + 1,
                                        date.month, date.day, date.weekday(), date.strftime("%A"), int(date.weekday() >= 5)))
                    dates_seen.add(date)
                batch.append((participant, date.isoformat(), timestamp.isoformat(sep=" "), *values))
                if len(batch) >= 10000:
                    connection.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                connection.executemany(insert_sql, batch)
            if not users_seen:
                raise ValueError("No timestamped measurements found in the input.")
            connection.execute(DAILY_SQL)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Database validation failed: invalid dimension references.")
        counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("dim_participant", "fact_health_reading", "fact_daily_health")}
        connection.close()
        return counts
    except BaseException:
        if connection is not None:
            connection.close()
        output.unlink(missing_ok=True)  # Only the new file reserved by this invocation.
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_DB, help="new SQLite file; must not already exist")
    parser.add_argument("--source-csv", type=Path, help="optional local timestamp-level CSV instead of downloading")
    args = parser.parse_args()
    try:
        counts = build_level3_database(args.output, args.source_csv)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Could not create level-three database: {error}\n")
    print(f"Created level-three database: {args.output.resolve()}")
    for table, count in counts.items():
        print(f"  {table}: {count:,} rows")


if __name__ == "__main__":
    main()

