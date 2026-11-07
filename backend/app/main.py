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
from pydantic import BaseModel, Field

from .arena.agents import RosterLanista, default_roster, llm_available, make_agents, schedule
from .arena.features import default_registry, public_catalog
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


class RosterEntry(BaseModel):
    claim: str = Field(min_length=1, max_length=200)
    add_features: list[str] = Field(min_length=1, max_length=2)
    expected_direction: Literal["positive", "negative", "either"] = "either"


class RunRequest(BaseModel):
    hypotheses: list[RosterEntry] | None = Field(None, max_length=40)  # the ones you ticked, in order
    max_in: int = Field(12, ge=1, le=40)
    emperor: Literal["real", "fake"] | None = None
    llm: bool | None = None  # None = Claude if an API key is set
    replay: str | None = None
    pace: float = 0.35
    seed: int = 0


class TheoryRequest(BaseModel):
    text: str
    llm: bool | None = None


def _use_llm(requested: bool | None) -> bool:
    return llm_available() if requested is None else requested


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
        source = Path(RUNS) / f"{req.replay}.jsonl"
        if source.resolve().parent != Path(RUNS).resolve() or not source.exists():
            raise HTTPException(404, f"no recorded run {req.replay}")
        ledger = Ledger(run_id, RUNS)
        thread = threading.Thread(target=_replay, args=(ledger, source, req.pace), daemon=True)
    else:
        train, test, sensors = frames()
        lanista, sceptic = make_agents(_use_llm(req.llm))
        if req.hypotheses is not None:
            chosen = [e.model_dump() for e in req.hypotheses[: req.max_in]]
            lanista = RosterLanista(schedule(chosen, _catalog(train)), base=lanista)
        ledger = Ledger(run_id, RUNS)
        arena = Arena(run_id, train, test, sensors, lanista, sceptic, ledger,
                      emperor=req.emperor, seed=req.seed, pace=req.pace, k=req.max_in)
        thread = threading.Thread(target=arena.run, daemon=True)
    thread.start()
    _runs[run_id] = {"ledger": ledger, "thread": thread}
    return {"run_id": run_id}


@app.get("/api/status")
def status():
    return {"claude": llm_available()}


def _catalog(train) -> list[dict]:
    return public_catalog(default_registry(), 3, set(train.columns))


@app.get("/api/roster")
def roster():
    """Every feature, and the pre-filled hypotheses the roster editor starts from."""
    train, _, _ = frames()
    catalog = _catalog(train)
    hypotheses = default_roster(catalog)
    return {"features": catalog, "hypotheses": hypotheses, "max_in": len(hypotheses)}


@app.get("/api/runs")
def list_runs():
    return sorted((p.stem for p in Path(RUNS).glob("*.jsonl")), reverse=True)


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, after: int = 0):
    run = _runs.get(run_id)
    if run is not None:
        done = not run["thread"].is_alive()  # first: events written after this are read next poll
        events = run["ledger"].since(after)
    else:
        path = Path(RUNS) / f"{run_id}.jsonl"
        if not path.exists():
            raise HTTPException(404, "unknown run")
        events, done = load(path)[after:], True
    return {"events": [e.model_dump() for e in events], "done": done}


@app.post("/api/theory")
def test_theory(req: TheoryRequest):
    train, test, sensors = frames()
    lanista, sceptic = make_agents(_use_llm(req.llm))
    run_id = _new_id("t")
    arena = Arena(run_id, train, test, sensors, lanista, sceptic, Ledger(run_id, RUNS), n_perm=100)
    state = arena.exhibition(req.text)
    return {"run_id": run_id, "verdict": state.verdict if state else None,
            "events": [e.model_dump() for e in arena.ledger.events]}


app.mount("/", StaticFiles(directory=ROOT / "frontend" / "src", html=True), name="ui")
