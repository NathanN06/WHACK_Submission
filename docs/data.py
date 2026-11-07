"""Full CGMacros dataset with separate daily and timestamp-level analysis tables.

Install dependencies: python -m pip install pandas requests "python-dateutil>=2.8.2,<3"
Run: python -i docs/data.py (keeps the DataFrame variables available afterward).
PARTICIPANT_LIMIT and DAYS_PER_PARTICIPANT are None to include all available data.
Source: https://physionet.org/content/cgmacros/1.0.0/
CGMacros contains no sleep data. Missing measurements remain NaN, not zero.
Running this script exports CSVs; importing it does not download or write data.
Daily tables have one row per person/date; raw_* tables retain every timestamp.
CSVs are separated into files_csv/daily_mean and files_csv/all_values.
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests


DATASET_URL = "https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip"
PARTICIPANT_LIMIT = None  # None = every participant in the source archive.
DAYS_PER_PARTICIPANT = None  # None = every available day, without truncation.

MEASUREMENT_COLUMNS = [
    "heart_rate_bpm", "libre_glucose_mg_dl", "dexcom_glucose_mg_dl",
    "activity_calories_kcal", "mets_times_10",
]
NUTRITION_COLUMNS = [
    "meal_type", "meal_calories_kcal", "carbs_g", "protein_g", "fat_g",
    "fiber_g", "amount_consumed_percent",
]
DAILY_KEYS = ["participant_id", "username", "date"]


def add_participant_keys(health_measurements_df):
    """Preserve source IDs and derive the same username/date for every view."""
    frame = health_measurements_df.rename(columns={
        "Steps": "steps", "Intensity": "intensity", "Sugar": "sugar",
        "RecordIndex": "source_record_index",
    }).copy()
    # These fields are supplied by only a subset of the source participants.
    for column in ("steps", "intensity", "sugar"):
        if column not in frame:
            frame[column] = float("nan")
    ids = pd.to_numeric(frame["participant_id"], errors="raise")
    if ids.isna().any() or (ids % 1 != 0).any():
        raise ValueError("Each measurement needs an integer participant_id.")
    frame["participant_id"] = ids.astype("int64")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    if frame["timestamp"].isna().any():
        raise ValueError("Each measurement needs a valid timestamp.")
    if frame.duplicated(["participant_id", "timestamp"]).any():
        raise ValueError("Duplicate participant/timestamp measurements would inflate daily totals.")
    frame["username"] = frame["participant_id"].map(lambda value: f"participant_{value:03d}")
    frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
    keys = ["participant_id", "username", "date", "timestamp"]
    return frame[keys + [column for column in frame.columns if column not in keys]].sort_values(
        ["participant_id", "timestamp"], ignore_index=True
    )


class _RemoteZip(io.RawIOBase):
    """Let zipfile read selected archive sections using HTTP byte ranges."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        with session.head(DATASET_URL, allow_redirects=True, timeout=30) as response:
            response.raise_for_status()
            self.url = response.url
            self.size = int(response.headers["Content-Length"])
        self.position = 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.size + offset
        else:
            raise ValueError("Invalid seek origin.")
        if position < 0:
            raise ValueError("Cannot seek before the start of the archive.")
        self.position = position
        return position

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.position + size, self.size)
        if self.position >= end:
            return b""
        headers = {"Range": f"bytes={self.position}-{end - 1}"}
        with self.session.get(self.url, headers=headers, stream=True, timeout=60) as response:
            response.raise_for_status()
            # Fail before reading a full archive if the server ignores Range.
            if response.status_code != 206:
                raise RuntimeError("The dataset server must support HTTP byte ranges.")
            content = response.content
        if len(content) != end - self.position:
            raise RuntimeError("Incomplete dataset download; please try again.")
        self.position = end
        return content


def load_health_sample(participant_limit=PARTICIPANT_LIMIT, days=DAYS_PER_PARTICIPANT):
    """Load all timestamped CSV data into RAM; optional limits allow small samples."""
    if ((participant_limit is not None and participant_limit < 1)
            or (days is not None and days < 1)):
        raise ValueError("participant_limit and days must be positive or None.")

    frames = []
    with requests.Session() as session, _RemoteZip(session) as remote:
        with zipfile.ZipFile(remote) as archive:
            # Exclude metadata CSVs and macOS archive duplicates.
            participant_files = sorted(
                name for name in archive.namelist()
                if re.search(r"(?:^|/)CGMacros-\d+\.csv$", name)
                and "__MACOSX" not in name
            )[:participant_limit]
            if not participant_files:
                raise ValueError("No participant CSVs found in the CGMacros archive.")

            for name in participant_files:
                participant_id = int(re.search(r"CGMacros-(\d+)\.csv$", name).group(1))
                with archive.open(name) as csv_file:
                    frame = pd.read_csv(csv_file)
                frame.columns = frame.columns.str.strip()
                frame = frame.loc[:, ~frame.columns.str.startswith("Unnamed:")]
                frame = frame.rename(columns={
                    "Timestamp": "timestamp",
                    "Libre GL": "libre_glucose_mg_dl",
                    "Dexcom GL": "dexcom_glucose_mg_dl",
                    "HR": "heart_rate_bpm",
                    "Calories (Activity)": "activity_calories_kcal",
                    "Mets": "mets_times_10",
                    "METs": "mets_times_10",
                    "Meal Type": "meal_type",
                    "Calories": "meal_calories_kcal",
                    "Carbs": "carbs_g",
                    "Protein": "protein_g",
                    "Fat": "fat_g",
                    "Fiber": "fiber_g",
                    "Amount Consumed": "amount_consumed_percent",
                    "Image path": "meal_image_path",
                    "Image Path": "meal_image_path",
                    "Steps": "steps",
                    "RecordIndex": "source_record_index",
                    "Intensity": "intensity",
                    "Sugar": "sugar",
                })
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
                if days is not None:
                    start = frame["timestamp"].min().normalize()
                    frame = frame.loc[frame["timestamp"] < start + pd.Timedelta(days=days)].copy()
                frame.insert(0, "participant_id", participant_id)
                frames.append(frame)

    return add_participant_keys(pd.concat(frames, ignore_index=True))


def build_daily_summary(health_measurements_df):
    """Shared daily calculation for the DataFrames, CSVs, and star database."""
    frame = add_participant_keys(health_measurements_df)
    keys = DAILY_KEYS
    sensors = frame.groupby(keys).agg(
        measurement_row_count=("timestamp", "size"),
        mean_heart_rate_bpm=("heart_rate_bpm", "mean"),
        heart_rate_reading_count=("heart_rate_bpm", "count"),
        mean_libre_glucose_mg_dl=("libre_glucose_mg_dl", "mean"),
        libre_glucose_reading_count=("libre_glucose_mg_dl", "count"),
        mean_dexcom_glucose_mg_dl=("dexcom_glucose_mg_dl", "mean"),
        dexcom_glucose_reading_count=("dexcom_glucose_mg_dl", "count"),
        mean_mets_times_10=("mets_times_10", "mean"),
        recorded_activity_calories_kcal=("activity_calories_kcal", lambda s: s.sum(min_count=1)),
        activity_reading_count=("activity_calories_kcal", "count"),
        recorded_steps=("steps", lambda s: s.sum(min_count=1)),
        steps_reading_count=("steps", "count"),
        mean_intensity=("intensity", "mean"),
        intensity_reading_count=("intensity", "count"),
    ).reset_index()
    meals = frame.loc[frame["meal_type"].notna()].groupby(keys).agg(
        recorded_meal_count=("meal_type", "count"),
        recorded_meal_calories_kcal=("meal_calories_kcal", lambda s: s.sum(min_count=1)),
        recorded_carbs_g=("carbs_g", lambda s: s.sum(min_count=1)),
        recorded_protein_g=("protein_g", lambda s: s.sum(min_count=1)),
        recorded_fat_g=("fat_g", lambda s: s.sum(min_count=1)),
        recorded_fiber_g=("fiber_g", lambda s: s.sum(min_count=1)),
        recorded_sugar=("sugar", lambda s: s.sum(min_count=1)),
        sugar_meal_count=("sugar", "count"),
    ).reset_index()
    summary = sensors.merge(meals, on=keys, how="left", validate="one_to_one")
    for column in ("recorded_meal_count", "sugar_meal_count"):
        summary[column] = summary[column].fillna(0).astype(int)
    return summary.sort_values(["participant_id", "date"], ignore_index=True)


def build_dataframes(health_measurements_df):
    """Build separate sets of daily summaries and original timestamped values."""
    frame = add_participant_keys(health_measurements_df)
    summary = build_daily_summary(frame)
    frames = {
        "raw_health_measurements_df": frame,
        "health_measurements_df": summary.copy(),
        "participants_df": frame[["participant_id", "username"]].drop_duplicates().reset_index(drop=True),
    }
    for name, columns in (
        ("heart_rate_df", ["mean_heart_rate_bpm", "heart_rate_reading_count"]),
        ("glucose_df", ["mean_libre_glucose_mg_dl", "libre_glucose_reading_count",
                        "mean_dexcom_glucose_mg_dl", "dexcom_glucose_reading_count"]),
        ("activity_df", ["recorded_activity_calories_kcal", "mean_mets_times_10",
                         "activity_reading_count", "recorded_steps", "steps_reading_count",
                         "mean_intensity", "intensity_reading_count"]),
        ("nutrition_df", ["recorded_meal_count", "recorded_meal_calories_kcal",
                          "recorded_carbs_g", "recorded_protein_g", "recorded_fat_g",
                          "recorded_fiber_g", "recorded_sugar", "sugar_meal_count"]),
    ):
        # Keep every person/date even when a modality has no measurements.
        frames[name] = summary[DAILY_KEYS + columns].copy()
    frames["daily_summary_df"] = summary
    raw_keys = DAILY_KEYS + ["timestamp"]
    for name, columns in (
        ("raw_heart_rate_df", ["heart_rate_bpm"]),
        ("raw_glucose_df", ["libre_glucose_mg_dl", "dexcom_glucose_mg_dl"]),
        ("raw_activity_df", ["activity_calories_kcal", "mets_times_10", "steps", "intensity"]),
        ("raw_nutrition_df", NUTRITION_COLUMNS + ["sugar"]),
    ):
        # Preserve the complete timestamp grid, including missing measurements.
        frames[name] = frame[raw_keys + columns].copy()
    return frames


def export_dataframes(dataframes):
    """Export daily and original values into clearly separated CSV folders."""
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "docs" / "files_csv"
    daily_dir = output_dir / "daily_mean"
    raw_dir = output_dir / "all_values"
    daily_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, dataframe in dataframes.items():
        if name == "participants_df":
            for directory in (daily_dir, raw_dir):
                dataframe.to_csv(directory / "participants.csv", index=False)
        else:
            directory = raw_dir if name.startswith("raw_") else daily_dir
            filename = name.removeprefix("raw_").removesuffix("_df") + ".csv"
            dataframe.to_csv(directory / filename, index=False)


if __name__ == "__main__":
    print("Loading every available CGMacros participant and day...")
    dataframes = build_dataframes(load_health_sample())
    globals().update(dataframes)
    print("Participant mapping (use these identifiers, not spreadsheet row numbers):")
    print(participants_df.to_string(index=False))
    print("Daily tables: daily means/totals, one row per person/date.")
    print("raw_* tables: every original timestamp, with no daily aggregation.")
    for name, dataframe in dataframes.items():
        print(f"\n{name}: {len(dataframe):,} rows")
        print(dataframe.head(3).to_string(index=False))
    export_dataframes(dataframes)
    print("CSV files saved successfully from the same participant sample.")


