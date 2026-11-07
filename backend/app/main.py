"""FastAPI backend: starts games, serves ledger events, serves the frontend.

Run from the repo root:  uvicorn app.main:app --app-dir backend --port 8000
"""

import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .arena.agents import make_agents
from .arena.ledger import Ledger, load
from .arena.orchestrator import Arena

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data" / "runs"
DB = ROOT / "data" / "whack.duckdb"

app = FastAPI(title="Gladiator Arena")
_runs: dict[str, dict] = {}
_frames = None
_frames_lock = threading.Lock()


def frames():
    """(train, test, sensors), loaded once. Tests replace this function."""
    global _frames
    with _frames_lock:
        if _frames is None:
            from .arena.data import load_all
            _frames = load_all(DB)
    return _frames


class RunRequest(BaseModel):
    emperor: Literal["real", "fake"] | None = None
    llm: bool = False
    replay: str | None = None
    pace: float = 0.35
    seed: int = 0


class TheoryRequest(BaseModel):
    text: str
    llm: bool = False


def _new_id(prefix: str) -> str:
    return f"{prefix}{time.strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def _replay(ledger: Ledger, source: Path, pace: float) -> None:
    for e in load(source):
        ledger.write(**e.model_dump(exclude={"run_id", "seq", "ts"}))
        time.sleep(pace)


@app.post("/api/runs")
def start_run(req: RunRequest):
    run_id = _new_id("r")
    if req.replay:
        source = RUNS / f"{req.replay}.jsonl"
        if not source.exists():
            raise HTTPException(404, f"no recorded run {req.replay}")
        ledger = Ledger(run_id, RUNS)
        thread = threading.Thread(target=_replay, args=(ledger, source, req.pace), daemon=True)
    else:
        train, test, sensors = frames()
        lanista, sceptic = make_agents(req.llm)
        ledger = Ledger(run_id, RUNS)
        arena = Arena(run_id, train, test, sensors, lanista, sceptic, ledger,
                      emperor=req.emperor, seed=req.seed, pace=req.pace)
        thread = threading.Thread(target=arena.run, daemon=True)
    thread.start()
    _runs[run_id] = {"ledger": ledger, "thread": thread}
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs():
    return sorted((p.stem for p in Path(RUNS).glob("*.jsonl")), reverse=True)


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, after: int = 0):
    run = _runs.get(run_id)
    if run is not None:
        events, done = run["ledger"].since(after), not run["thread"].is_alive()
    else:
        path = Path(RUNS) / f"{run_id}.jsonl"
        if not path.exists():
            raise HTTPException(404, "unknown run")
        events, done = load(path)[after:], True
    return {"events": [e.model_dump() for e in events], "done": done}


@app.post("/api/theory")
def test_theory(req: TheoryRequest):
    train, test, sensors = frames()
    lanista, sceptic = make_agents(req.llm)
    run_id = _new_id("t")
    arena = Arena(run_id, train, test, sensors, lanista, sceptic, Ledger(run_id, RUNS), n_perm=100)
    state = arena.exhibition(req.text)
    return {"run_id": run_id, "verdict": state.verdict if state else None,
            "events": [e.model_dump() for e in arena.ledger.events]}


app.mount("/", StaticFiles(directory=ROOT / "frontend" / "src", html=True), name="ui")
