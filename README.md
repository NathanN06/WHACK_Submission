# WHACK_Submission

https://drive.google.com/file/d/1hBc-9XsDW2u1nPB54zo3ZmzCCmPHL_BW/view?usp=sharing <- Link to the video demonstration of our project.

**An AI researcher that tests its own ideas — and can tell a real discovery from a lucky one.**

Finding patterns in data is easy; knowing which ones to trust is hard. This project generates hypotheses from a dataset (markets, sport, medicine, online experiments…), then stress-tests each one before calling it a discovery.

## Structure

```
backend/    API + research/statistics engine
frontend/   Web UI
docs/       Notes, design, pitch material
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

## Getting started: the Hypothesis Gauntlet (Peptide & GLP-1 Discovery)

The Alchemist-Epidemiologist carries three hypothesis scrolls about peptides and GLP-1 drugs through four
levels of evidence (Rumour Dungeon, Forgotten Archives, Temple of Replication, Citadel of Truth). A
deterministic Statistical Judge measures every claim; the hero only chooses abilities. Each scroll has its
own HP and shatters at 0. Only a scroll that predicts unseen, matched patients better than the Gatekeeper
Skeptic's active-comparator baseline, by a margin unlikely to be luck, wins.
Rules, formulas and HP weights: [docs/gauntlet-rules.md](docs/gauntlet-rules.md).

**The four campaigns are simulated** worlds with planted, known effects (revealed in the brief). They are
not real findings and not medical advice.

```bash
.venv/bin/uvicorn app.main:app --app-dir backend --port 8000   # then open http://localhost:8000
```

- Pick a campaign (A to D). **Begin** runs it live; with `ANTHROPIC_API_KEY` in `.env` you can let Claude
  play the Alchemist, otherwise each scroll follows its scripted plan.
- **Watch the recorded run** plays `frontend/src/demo/demo-<letter>.jsonl` and needs no server:
  `cd frontend/src && python3 -m http.server`, then open `index.html#watch=A`.
- Command line: `.venv/bin/python scripts/run_pep.py A` (or `all --out frontend/src/demo` to re-record the demos).
- Split screen: battle stage (the hero, three floating scrolls, the Gatekeeper and its speech bubbles, a
  HUD for the scroll under test), combat console (Run/Pause, 1×/2×/4×, Step, Skip level, Exit) and, on the
  right, the Test Inspector (test, chart, formula, the HP clamp, the telemetry record) above a filterable
  append-only ledger.
- After level IV the laboratory shows the Research Decision Brief: decision, evidence with encounter
  citations, what misled the other scrolls, uncertainty, the composite score with the Gatekeeper's
  benchmark row, HP per level, damage by trap, and the planted truth.

- Every claim gets a **scientific status** that is decided apart from HP and the game: supported on synthetic
  validation, provisionally supported, inconclusive, contradicted, or invalid analysis
  ([docs/gauntlet-rules.md](docs/gauntlet-rules.md#research-integrity-analysis-version-pep-judge-22)).
- Each live quest draws a fresh synthetic cohort; a sealed vault confirms a claim at most once. A champion persists
  per campaign and defends its title against new challengers on fresh cohorts.
- Truth-versus-luck benchmark (120 seeded worlds, the whole pipeline, scored against the planted truth after each run):
  `.venv/bin/python scripts/evaluate_pep.py --seeds 20 --out docs`. Results: [docs/evaluation_summary.json](docs/evaluation_summary.json).

Tests: `.venv/bin/python -m pytest` and `node --test frontend/tests/*.test.js`.
