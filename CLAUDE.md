# CLAUDE.md

Hackathon project (WHACK): an AI researcher that proposes hypotheses from data and tests them rigorously to separate real discoveries from lucky/spurious ones.

## Layout
- `backend/` — API and research/statistics engine
- `frontend/` — web UI
- `docs/` — notes and pitch material

## Guidelines
- Hackathon pace: keep things simple and demo-able; prefer working end-to-end over polish.
- Every "discovery" should be backed by a test that guards against luck (e.g. holdout replication, permutation tests, multiple-comparison correction).
- Never commit secrets — API keys go in `.env` (gitignored).
