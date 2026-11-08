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
from .pep import champions
from .pep import challenges as pep_challenges
from .pep import rules as pep_rules
from .pep.agents import make_hero
from .pep.campaign import PepQuest
from .pep.hypotheses import DB_PATH as EVIDENCE_DB, MAX_SCROLLS, MIN_SCROLLS
from .pep.campaigns import ARCHETYPES, BY_LETTER, CAMPAIGNS, HERO
from .pep.director import DirectorError, Expedition
from .pep.models import QuestEvent

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data" / "runs"
QUESTS = ROOT / "data" / "quests"
CHAMPIONS = ROOT / "data" / "champions.json"
DB = ROOT / "data" / "whack.duckdb"

app = FastAPI(title="Hypothesis Gauntlet")
_runs: dict[str, dict] = {}
_quests: dict[str, dict] = {}
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
    pace: float = Field(0.35, ge=0, le=5)
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


# The original arena (blood-sugar edition) endpoints are kept for its tests but hidden from the API docs.
@app.post("/api/runs", include_in_schema=False)
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


@app.get("/api/roster", include_in_schema=False)
def roster():
    """Every feature, and the pre-filled hypotheses the roster editor starts from."""
    train, _, _ = frames()
    catalog = _catalog(train)
    hypotheses = default_roster(catalog)
    return {"features": catalog, "hypotheses": hypotheses, "max_in": len(hypotheses)}


@app.get("/api/runs", include_in_schema=False)
def list_runs():
    return sorted((p.stem for p in Path(RUNS).glob("*.jsonl")), reverse=True)


@app.get("/api/runs/{run_id}/events", include_in_schema=False)
def run_events(run_id: str, after: int = 0):
    run = _runs.get(run_id)
    if run is not None:
        done = not run["thread"].is_alive()  # first: events written after this are read next poll
        events = run["ledger"].since(after)
    else:
        path = Path(RUNS) / f"{run_id}.jsonl"
        if path.resolve().parent != Path(RUNS).resolve() or not path.exists():
            raise HTTPException(404, "unknown run")
        events, done = load(path)[after:], True
    return {"events": [e.model_dump() for e in events], "done": done}


@app.post("/api/theory", include_in_schema=False)
def test_theory(req: TheoryRequest):
    train, test, sensors = frames()
    lanista, sceptic = make_agents(_use_llm(req.llm))
    run_id = _new_id("t")
    arena = Arena(run_id, train, test, sensors, lanista, sceptic, Ledger(run_id, RUNS), n_perm=100)
    state = arena.exhibition(req.text)
    return {"run_id": run_id, "verdict": state.verdict if state else None,
            "events": [e.model_dump() for e in arena.ledger.events]}


# ---------- Hypothesis Gauntlet: Peptide & GLP-1 Edition ----------


MAX_LIVE = 4          # live expeditions at once; a fifth is refused (429) until one ends
IDLE_LIMIT = 120      # seconds without a poll or a Director action before an expedition stops itself


class QuestRequest(BaseModel):
    campaign: str = Field("A", max_length=40)  # A-D or a campaign id
    llm: bool | None = None  # None = Claude plays the Alchemist if an API key is set
    replay: str | None = None
    pace: float = Field(0.0, ge=0, le=5)
    seed: int = Field(0, ge=0, le=1_000_000)
    interactive: bool = False  # True: the quest waits for the screen and the Research Director's console is open
    scrolls: int | None = Field(None, ge=MIN_SCROLLS, le=MAX_SCROLLS)  # None: the hand-written scrolls; else the Scribe forms this many
    challenger: bool = False  # True: one round of the campaign's title track (champions.py), on a fresh seed


def _replay_quest(ledger: Ledger, source: Path, pace: float) -> None:
    for e in load(source, QuestEvent):
        ledger.write(**e.model_dump(exclude={"run_id", "seq", "ts"}))
        time.sleep(pace)


def _campaign_id(key: str) -> str:
    cid = BY_LETTER[key.upper()].id if key.upper() in BY_LETTER else key
    if cid not in CAMPAIGNS:
        raise HTTPException(404, f"no campaign {key}")
    return cid


@app.post("/api/quests")
def start_quest(req: QuestRequest):
    quest_id = _new_id("q")
    if req.replay:
        source = Path(QUESTS) / f"{req.replay}.jsonl"
        if source.resolve().parent != Path(QUESTS).resolve() or not source.exists():
            raise HTTPException(404, f"no recorded quest {req.replay}")
        ledger = Ledger(quest_id, QUESTS, model=QuestEvent)
        thread = threading.Thread(target=_replay_quest, args=(ledger, source, req.pace), daemon=True)
        quest = None
    else:
        cid = _campaign_id(req.campaign)
        live = sum(1 for e in _quests.values() if e.get("quest") is not None and e["thread"].is_alive())
        if live >= MAX_LIVE:
            raise HTTPException(429, f"{live} expeditions are already running; wait for one to end or leave it first.")
        ledger = Ledger(quest_id, QUESTS, model=QuestEvent)
        use_llm = _use_llm(req.llm)
        scribe = None
        if use_llm and req.scrolls is not None:
            from .arena.agents import ENV_FILE, anthropic_complete, load_env_key
            load_env_key(ENV_FILE)
            scribe = anthropic_complete()
        quest = PepQuest(quest_id, cid, ledger, make_hero(use_llm), seed=req.seed, pace=req.pace,
                         n_scrolls=req.scrolls, scribe=scribe, challenger=req.challenger, champions_path=CHAMPIONS)
        quest.idle_limit = IDLE_LIMIT
        if req.interactive:
            Expedition(quest)
        thread = threading.Thread(target=quest.run, daemon=True)
    thread.start()
    _quests[quest_id] = {"ledger": ledger, "thread": thread, "quest": quest}
    return {"quest_id": quest_id}


@app.post("/api/quests/{quest_id}/stop")
def stop_quest(quest_id: str):
    """The player left: stop the quest so it stops spending Claude calls."""
    entry = _quests.get(quest_id)
    if entry is None:
        raise HTTPException(404, "unknown quest")
    running = entry["thread"].is_alive() and entry.get("quest") is not None
    if running:
        entry["quest"].stop()
    return {"stopped": running}


@app.get("/api/quests")
def list_quests():
    return sorted((p.stem for p in Path(QUESTS).glob("*.jsonl")), reverse=True)


@app.get("/api/quests/{quest_id}/events")
def quest_events(quest_id: str, after: int = 0):
    quest = _quests.get(quest_id)
    if quest is not None:
        if quest.get("quest") is not None:
            quest["quest"].touch()   # someone is still watching
        done = not quest["thread"].is_alive()
        events = quest["ledger"].since(after)
    else:
        path = Path(QUESTS) / f"{quest_id}.jsonl"
        if path.resolve().parent != Path(QUESTS).resolve() or not path.exists():
            raise HTTPException(404, "unknown quest")
        events, done = load(path, QuestEvent)[after:], True
    return {"events": [e.model_dump() for e in events], "done": done}


# ---------- the Research Director's console (director.py, bridge.py) ----------


class Upload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content_b64: str = Field(max_length=1_400_000)  # about 1 MB once decoded


class ChatRequest(BaseModel):
    mode: Literal["ASK", "CHALLENGE", "ADD_EVIDENCE", "NEW_HYPOTHESIS", "SUMMON"] = "ASK"
    text: str = Field("", max_length=2000)
    # a challenge chip: the registered test the Director picked, instead of routing the text
    archetype: Literal["seasonal", "chronolock", "regional", "chance", "replication", "redundancy", "confounder"] | None = None
    url: str | None = Field(None, max_length=500)
    file: Upload | None = None
    level: int | None = Field(None, ge=1, le=5)
    target: str | None = Field(None, max_length=40)
    request_id: str | None = Field(None, max_length=80)


class MysteryRequest(BaseModel):
    action: Literal["summon", "save", "explain", "cancel"]
    level: int | None = Field(None, ge=1, le=5)
    request_id: str | None = Field(None, max_length=80)


class AdvanceRequest(BaseModel):
    level: int = Field(ge=0, le=5)


class BridgeRequest(BaseModel):
    choice: Literal["cross", "evolve", "inconclusive"]
    request_id: str | None = Field(None, max_length=80)


def _director(quest_id: str) -> Expedition:
    entry = _quests.get(quest_id)
    quest = entry and entry.get("quest")
    if quest is None or quest.director is None:
        raise HTTPException(409, "This quest has no Research Director's console (it is a recording or was started without one).")
    if not entry["thread"].is_alive():
        raise HTTPException(409, "This expedition has ended.")
    quest.touch()
    return quest.director


def _call(fn):
    from .pep.campaign import QuestStopped
    try:
        return fn()
    except DirectorError as e:
        raise HTTPException(409, str(e)) from e
    except QuestStopped as e:
        raise HTTPException(409, "This expedition was stopped.") from e


@app.post("/api/quests/{quest_id}/advance")
def advance_quest(quest_id: str, req: AdvanceRequest):
    """The screen has finished showing this level: the quest may compute the next one."""
    return _director(quest_id).advance(req.level)


@app.post("/api/quests/{quest_id}/chat")
def quest_chat(quest_id: str, req: ChatRequest):
    """CHALLENGE THE HERO: ask, challenge, add evidence, propose a hypothesis or summon a Mystery Boss."""
    d = _director(quest_id)
    return _call(lambda: d.chat(req.model_dump()))


@app.post("/api/quests/{quest_id}/mystery/{mystery_id}")
def quest_mystery(quest_id: str, mystery_id: str, req: MysteryRequest):
    d = _director(quest_id)
    return _call(lambda: d.mystery(mystery_id, req.action, req.request_id, req.level))


@app.post("/api/quests/{quest_id}/bridge")
def quest_bridge(quest_id: str, req: BridgeRequest):
    """The Research Director's choice at the Bridge of Judgment. The hero designs; the Judge decides."""
    d = _director(quest_id)
    return _call(lambda: d.choose(req.choice, req.request_id))


@app.get("/api/quests/{quest_id}/director")
def quest_director(quest_id: str):
    return _director(quest_id).summary()


@app.get("/api/campaigns")
def campaigns():
    """The four peptide campaigns the title screen offers."""
    return [{"id": c.id, "letter": c.letter, "title": c.title, "question": c.question, "drug": c.drug,
             "comparator": c.comparator, "target": c.outcomes[0].label, "scrolls": [s.title for s in c.scrolls],
             "simulated": True, "min_scrolls": MIN_SCROLLS, "max_scrolls": MAX_SCROLLS,
             "real_evidence": EVIDENCE_DB.exists(), "track": champions.track_key(c)} for c in CAMPAIGNS.values()]


@app.get("/api/champions")
def champion_registry():
    """Challenger Mode: each campaign's title track, its reigning champion and its last rounds."""
    return champions.public(CHAMPIONS)


@app.get("/api/quests-rules")
def quest_rulebook():
    """Every HP, credit, damage and score rule, so the screen can show the rulebook it is judged by."""
    R = pep_rules
    return {"levels": R.LEVELS, "abilities": R.ABILITIES, "enemies": R.ENEMIES, "d_max": R.D_MAX,
            "score_weights": R.SCORE_WEIGHTS, "score_rules": R.SCORE_RULES, "verdicts": R.VERDICTS,
            "traps": R.TRAPS, "trap_labels": R.TRAP_LABELS, "archetypes": ARCHETYPES, "hero": HERO,
            "starting_hp": R.STARTING_HP, "starting_credits": R.STARTING_CREDITS, "ruleset_version": R.RULESET_VERSION,
            "mystery_hp": R.MYSTERY_HP, "science": R.SCIENCE,
            "challenges": {k: {f: v[f] for f in ("boss", "key", "question", "test", "ability", "rule")}
                           for k, v in pep_challenges.ARCHETYPES.items()}}


app.mount("/", StaticFiles(directory=ROOT / "frontend" / "src", html=True), name="ui")
