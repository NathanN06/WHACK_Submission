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
- The hero (agents.py) only chooses abilities and says why, from the blinded payload telemetry.py builds (outcome-free flags + earlier-level findings, allowlisted and leak-guarded). Never put holdout, vault, Guardian/Trial numbers or planted truths in a planning payload.
- Only judge.py measures; only campaign.py applies the damage rules in rules.py; only science.py assigns scientific statuses (rules.STATUSES), and never from HP; report.py and provenance.py only copy measured numbers and stored identifiers.
- The Scribe (hypotheses.py) writes 2-6 TYPED claims (outcome, direction, subgroup, ...) when a quest asks for `scrolls: N`; textpolicy.py decides which numbers model-written text may contain. The Judge tests the typed claim, in its subgroup and direction. Each scroll's papers and trials are copied from the REAL `data/pep_evidence.duckdb`; without `scrolls`, the three hand-written scrolls are used.
- All Claude calls go through app/llm.py (`ask_traced`): every decision records its execution mode and fallback reason.
- The patient cohort and social corpus are still a simulated world (world.py) with planted truths: never present results as real findings or medical advice.
- The "vault2" split (index day >= 1450) is read only by the Trial of Truth, after the spec is locked and the opening logged in registry.py; never in levels I to IV, the Skeptic or Mystery tests. A reused vault never counts as a new confirmation.
- Bump rules.ANALYSIS_VERSION when an estimator or status rule changes. Then re-record the demos: .venv/bin/python scripts/run_pep.py all --out frontend/src/demo --quiet
- Benchmark (truth vs luck over many seeded worlds): .venv/bin/python scripts/evaluate_pep.py --seeds 20 --out docs, then copy docs/evaluation_summary.json to frontend/src/demo/.
- On Windows the venv's Python is .venv\Scripts\python (not .venv/bin/python).
