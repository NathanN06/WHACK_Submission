"""All-values star database, preserving every original timestamped measurement.

Run python -i docs/database.py to build both databases from one full download.
The database remains in memory; CSVs are exported separately by the main script.
"""

import sqlite3

import pandas as pd

if __package__:
    from .data import MEASUREMENT_COLUMNS, NUTRITION_COLUMNS, add_participant_keys
    from .database import DIMENSION_SCHEMA, _dimension_dataframes, _insert_dataframe
else:
    from data import MEASUREMENT_COLUMNS, NUTRITION_COLUMNS, add_participant_keys
    from database import DIMENSION_SCHEMA, _dimension_dataframes, _insert_dataframe


SCHEMA = DIMENSION_SCHEMA + """
CREATE TABLE fact_health_reading (
    username TEXT NOT NULL,
    date TEXT NOT NULL CHECK (date = substr(timestamp, 1, 10)),
    timestamp TEXT NOT NULL,
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
    PRIMARY KEY (username, timestamp),
    FOREIGN KEY (username) REFERENCES dim_user(username),
    FOREIGN KEY (date) REFERENCES dim_date(date)
);
CREATE INDEX fact_health_reading_by_day ON fact_health_reading(username, date);
"""


def create_raw_database(raw_health_measurements_df):
    """Store each source timestamp without averaging, summing, or dropping rows."""
    if "timestamp" not in raw_health_measurements_df:
        raise ValueError("Pass raw_health_measurements_df, which contains timestamped readings.")
    frame = add_participant_keys(raw_health_measurements_df)
    users, dates = _dimension_dataframes(frame)
    # Optional source fields occur only in some participant files.
    for column in ("steps", "intensity", "sugar", "meal_image_path", "source_record_index"):
        if column not in frame:
            frame[column] = pd.NA
    facts = frame[
        ["username", "date", "timestamp"] + MEASUREMENT_COLUMNS + ["steps", "intensity"]
        + NUTRITION_COLUMNS + ["sugar", "meal_image_path", "source_record_index"]
    ].copy()
    facts["timestamp"] = facts["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA)
        with connection:
            _insert_dataframe(connection, "dim_user", users)
            _insert_dataframe(connection, "dim_date", dates)
            _insert_dataframe(connection, "fact_health_reading", facts)
    except Exception:
        connection.close()
        raise
    return connection
