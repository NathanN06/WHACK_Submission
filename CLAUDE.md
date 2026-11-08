# CLAUDE.md

Hackathon project (WHACK): an AI researcher that proposes hypotheses from data and tests them rigorously to separate real discoveries from lucky/spurious ones.

## Layout
- `backend/` — API and research/statistics engine
- `frontend/` — web UI
- `docs/` — notes and pitch material
- `scripts/download_data.py` — downloads datasets into `data/` (gitignored; never commit data)
- `scripts/build_db.py` — loads the CSVs into `data/whack.duckdb` (run with `.venv/bin/python`)
- `scripts/download_pep_evidence.py` — fetches REAL Europe PMC papers, ClinicalTrials.gov studies and openFDA FAERS counts for the Gauntlet campaigns into `data/pep_evidence.duckdb` (separate file because `build_db.py` rebuilds `whack.duckdb`)

## Data conventions
- `participant_id` = a person (`CGM-001`, `BUT-101`); `session_id` = one measurement period. Train/holdout splits must be by `participant_id`.
- Glucose is always mg/dL. Timestamps are date-shifted (absolute dates meaningless; time-of-day/weekday valid).
- Table/column docs live in the DB as comments (`duckdb_tables()`, `duckdb_columns()`); keep `TABLE_DOCS`/`COLUMN_DOCS` in `build_db.py` updated when changing tables.
- In CGMacros the Dexcom reads ~30 mg/dL higher than the Libre on average; `meal_responses` uses Dexcom in both datasets (5-min readings). CGMacros ships CGM values interpolated to 1-min; the `glucose` table keeps only real readings.
- Meal-effect analyses should filter `meal_responses` on `clean`.

## Guidelines
- Hackathon pace: keep things simple and demo-able; prefer working end-to-end over polish.
- Every "discovery" should be backed by a test that guards against luck (e.g. holdout replication, permutation tests, multiple-comparison correction).
- Never commit secrets — API keys go in `.env` (gitignored).

## The Arena: rules for anyone (human or Claude) editing backend/app/arena
- Agents never produce numbers, p-values or verdicts. Only engine.py measures; only referee.py rules.
- Cross-validation folds are split by participant_id, never by meal.
- Every number the UI shows comes from the ledger (data/runs/*.jsonl).
- Run tests with: .venv/bin/python -m pytest -q   and   node --test frontend/tests/*.test.js

## The Gauntlet (Peptide & GLP-1 Edition): rules for editing backend/app/pep
- The hero (agents.py) only chooses abilities for each scroll. Only judge.py measures; only campaign.py applies the damage rules in rules.py; report.py only copies measured numbers.
- The Scribe (hypotheses.py) only writes the words of 2-6 scrolls (title, claim, origin, outcome, topic, archetype) when a quest asks for `scrolls: N`; it never writes numbers, and no two scrolls share an (outcome, archetype) structure. Each scroll's papers and completed-RCT count are copied from the REAL `data/pep_evidence.duckdb`; without `scrolls`, the three hand-written scrolls are used.
- The patient cohort and social corpus are still a simulated world (world.py) with planted truths: never present results as real findings or medical advice.
- The "vault2" split (index day >= 1450) is opened once, by the Trial of Truth (bridge.py): never read it in levels I to IV.
- Point-in-time training: anything fit or measured on the training years uses `cutoff=TRAIN_END` (world.rows / world.new_user), so no follow-up after day 1100 is ever read.
- The Guardian reports prediction (SS_oos, the verdict) and causation (the matched risk ratio's scientific status, judge.science_status) separately; champions are per outcome track, never across outcomes.
- Every encounter carries methodId, sourceIds and rulesetVersion (sources.py); a new enemy or test needs an entry in sources.METHODS / ENEMY_TRACE, and any rule change bumps rules.RULESET_VERSION.
- Challenger Mode keeps its registry in `data/champions.json` (gitignored, written only by champions.py: atomically, once per run, revision-checked).
- After changing the engine, re-record the demos: .venv/bin/python scripts/run_pep.py all --out frontend/src/demo --quiet
