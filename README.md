# WHACK_Submission

**An AI researcher that tests its own ideas — and can tell a real discovery from a lucky one.**

Finding patterns in data is easy; knowing which ones to trust is hard. This project generates hypotheses from a dataset (markets, sport, medicine, online experiments…), then stress-tests each one before calling it a discovery.

## Structure

```
backend/    API + research/statistics engine
frontend/   Web UI
scripts/    Utility scripts (e.g. dataset download)
data/       Downloaded datasets (gitignored, not committed)
```

## Data

We use two open-access continuous glucose monitoring (CGM) datasets from PhysioNet:

| Dataset | Role | What's in it |
|---|---|---|
| [CGMacros 1.0.0](https://physionet.org/content/cgmacros/1.0.0/) | Main dataset | CGM readings, meal macronutrients, meal photos and activity data |
| [BUT CGM 1.0.0](https://physionet.org/content/but-cgm/1.0.0/) | Validation | 60 healthy, active adults over ~10 days: CGM, meals, activities, sleep, steps, CPET (lab exercise tests), questionnaires |

Download both into `data/` (needs Python 3.9+, no extra packages):

```bash
python3 scripts/download_data.py
```

| Command | Downloads |
|---|---|
| `python3 scripts/download_data.py` | CGMacros (~628 MB zip, extracted) and BUT CGM CSV files only |
| `python3 scripts/download_data.py --only cgmacros` | CGMacros only |
| `python3 scripts/download_data.py --only but-cgm` | BUT CGM only |
| `python3 scripts/download_data.py --include-hr` | Also BUT CGM beat-by-beat heart rate CSVs |
| `python3 scripts/download_data.py --include-signals` | Also BUT CGM raw ECG/accelerometer `.h5` files (**~60 GB**) |
| `python3 scripts/download_data.py --delete-zip` | Delete the CGMacros zip after extracting it (saves ~650 MB) |
| `python3 scripts/download_data.py --unzip-only` | Don't download, just extract any `.zip` already in `data/` |

Re-running the script only fetches files that are missing, so it's safe to run again if a download fails.

Resulting layout:

```
data/
  cgmacros/   CGMacros (zip + extracted files)
  but-cgm/    BUT CGM: top-level CSVs + one folder per participant/session (e.g. 101001/)
```

### Build the database

All the CSVs are loaded into a single [DuckDB](https://duckdb.org) database, `data/whack.duckdb` (a relational database you query with SQL):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_db.py     # a few seconds, rebuilds from scratch
```

Both datasets are merged into shared tables:

- IDs: `participant_id` (`CGM-001`, `BUT-101`) is one **person**; `session_id` is one ~10-day measurement period.
- Units: glucose is always **mg/dL**.

| Table | What it holds |
|---|---|
| `participants` | One row per person: age, sex, BMI, HbA1c, `glycemic_status` (healthy / prediabetes / type2_diabetes / healthy_active) |
| `sessions` | Measurement periods (start, end, days) |
| `glucose` | Every CGM reading (~1.5M rows), with `sensor` (libre / dexcom / dexcom_g7) |
| `meals` | Every logged food item with calories, carbs, protein, fat, fiber, sugar, and its `meal_event_id` |
| `meal_events` | One row per eating occasion: items logged within 30 min of each other merged, macros summed |
| `meal_responses` | **Derived**: glucose response to each meal event (baseline, peak, rise, time-to-peak, 2h area under curve). Every event has a row; use `WHERE clean` for meal-effect analyses (`exclusion_reason` says why a row failed quality checks) |
| `cgmacros_minute` | CGMacros minute-level heart rate, METs, activity calories, steps |
| `activities`, `sleep`, `daily_steps`, `daily_nutrition`, `daily_questionnaire` | BUT CGM lifestyle data |
| `cpet_data`, `cpet_summary`, `cpet_metadata` | BUT CGM lab exercise tests |
| `gut_health`, `microbes`, `cgmacros_bio` | CGMacros gut microbiome and full lab sheet |
| `but_subject_info`, `but_data_completeness` | BUT CGM entry questionnaire and data availability |

Every table and column has a description stored in the database:

```sql
SELECT table_name, comment FROM duckdb_tables();
SELECT column_name, comment FROM duckdb_columns() WHERE table_name = 'meal_responses';
```

Quick look from the terminal: `.venv/bin/python -c "import duckdb; print(duckdb.connect('data/whack.duckdb').sql('FROM meal_responses LIMIT 5'))"`

### Separate level-three health database

Run `python scripts/build_level3_db.py` to create a new, separate
`data/level3_health.sqlite3` from all CGMacros participant CSVs. The builder uses
only Python's standard library and the streaming code in `scripts/download_data.py`.
It does not download the photo archive or save intermediate CSVs.

The database has `dim_participant` and `dim_date` dimensions, plus two fact tables:
`fact_health_reading` stores every original timestamp; `fact_daily_health` stores
one row per participant/date with sensor means, recorded totals and reading counts.
`dataset_metadata` records data level 3, source and build time.

The full data has 45 participants, 687,580 timestamped rows and 533 person-day
summaries. Missing readings remain NULL. Raw CGM values retain the source's
interpolation; recorded daily totals can cover partial days. Split training and
holdout data by participant ID.

The builder refuses existing output files and cannot target `data/whack.duckdb`.
Use `--output data/level3_health_run2.sqlite3` for another build, or
`--source-csv path/to/readings.csv` to reuse an existing timestamp-level CSV.

## Getting started

_Setup instructions coming soon._
