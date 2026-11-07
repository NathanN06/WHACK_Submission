"""Build separate daily-summary and all-values star databases from CGMacros.

Run: python -i docs/database.py
Databases stay in RAM as `daily_connection` and `raw_connection`.
CSV exports go to files_csv/daily_mean and files_csv/all_values.
The source is anonymous, so usernames are generated as participant_001, etc.
Grain: one fact row per username and date; raw readings stay in raw_health_measurements_df.
See database_schema.md for the Mermaid entity-relationship diagram.
"""

import sqlite3

import pandas as pd

if __package__:
    from .data import (
        MEASUREMENT_COLUMNS, NUTRITION_COLUMNS, add_participant_keys,
        build_daily_summary, build_dataframes, export_dataframes, load_health_sample,
    )
else:
    from data import (
        MEASUREMENT_COLUMNS, NUTRITION_COLUMNS, add_participant_keys,
        build_daily_summary, build_dataframes, export_dataframes, load_health_sample,
    )

DIMENSION_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE dim_user (
    username TEXT PRIMARY KEY NOT NULL,
    participant_id INTEGER UNIQUE NOT NULL
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
"""

SCHEMA = DIMENSION_SCHEMA + """
-- Each fact links directly to both dimensions: one row per user per date.
-- Sums describe recorded data; partial days are not complete-day totals.
CREATE TABLE fact_daily_health (
    username TEXT NOT NULL,
    date TEXT NOT NULL,
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
    PRIMARY KEY (username, date),
    FOREIGN KEY (username) REFERENCES dim_user(username),
    FOREIGN KEY (date) REFERENCES dim_date(date)
);
CREATE INDEX fact_daily_health_by_date ON fact_daily_health(date);
"""


def _insert_dataframe(connection, table, frame):
    """Insert into existing tables, preserving their keys and foreign keys."""
    columns = ", ".join(frame.columns)
    placeholders = ", ".join("?" for _ in frame.columns)
    # Convert pandas NaN/NA values to SQL NULL without filling missing readings.
    values = frame.astype(object).where(frame.notna(), None)
    connection.executemany(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        values.itertuples(index=False, name=None),
    )


def _daily_facts(frame):
    """Use the exact daily summary calculation used by the other DataFrames."""
    return build_daily_summary(frame).drop(columns=["participant_id"])


def _dimension_dataframes(frame):
    """Use identical user identities and calendar attributes in both databases."""
    dates = pd.to_datetime(frame["date"].drop_duplicates().sort_values()).reset_index(drop=True)
    date_dimension = pd.DataFrame({
        "date": dates.dt.strftime("%Y-%m-%d"),
        "year": dates.dt.year,
        "quarter": dates.dt.quarter,
        "month": dates.dt.month,
        "day": dates.dt.day,
        "day_of_week": dates.dt.dayofweek,  # Monday = 0, Sunday = 6.
        "weekday_name": dates.dt.day_name(),
        "is_weekend": (dates.dt.dayofweek >= 5).astype(int),
    })
    users = frame[["username", "participant_id"]].drop_duplicates()
    return users, date_dimension


def create_database(health_measurements_df):
    """Build daily facts from raw timestamped readings without modifying them."""
    if "timestamp" not in health_measurements_df:
        raise ValueError("Pass raw_health_measurements_df, which contains timestamped readings.")
    frame = add_participant_keys(health_measurements_df)
    users, date_dimension = _dimension_dataframes(frame)
    facts = _daily_facts(frame)

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA)
        with connection:
            _insert_dataframe(connection, "dim_user", users)
            _insert_dataframe(connection, "dim_date", date_dimension)
            _insert_dataframe(connection, "fact_daily_health", facts)
    except Exception:
        connection.close()
        raise
    return connection


if __name__ == "__main__":
    if __package__:
        from .raw_database import create_raw_database
    else:
        from raw_database import create_raw_database

    print("Loading every available CGMacros participant and day...")
    dataframes = build_dataframes(load_health_sample())
    globals().update(dataframes)
    daily_connection = create_database(raw_health_measurements_df)
    raw_connection = create_raw_database(raw_health_measurements_df)
    connection = daily_connection  # Backwards-compatible name for daily SQL queries.
    export_dataframes(dataframes)

    # Convenient DataFrames for interactive inspection; SQL is available too.
    dim_user_df = pd.read_sql_query("SELECT * FROM dim_user ORDER BY username", connection)
    dim_date_df = pd.read_sql_query("SELECT * FROM dim_date ORDER BY date", connection)
    fact_daily_health_df = pd.read_sql_query(
        "SELECT * FROM fact_daily_health ORDER BY username, date", connection
    )
    daily_summary_df = pd.read_sql_query(
        "SELECT u.participant_id, f.* FROM fact_daily_health AS f "
        "JOIN dim_user AS u ON u.username = f.username ORDER BY u.participant_id, f.date",
        connection,
    )
    daily_mean_df = daily_summary_df
    all_values_df = raw_health_measurements_df
    print(f"Daily database: {len(daily_mean_df):,} person/day rows (daily_connection)")
    print(f"All-values database: {len(all_values_df):,} timestamped rows (raw_connection)")
    print("Participant mapping:")
    print(dim_user_df[["participant_id", "username"]].to_string(index=False))
    print("Daily summary preview:")
    print(daily_summary_df.head(10).to_string(index=False))
