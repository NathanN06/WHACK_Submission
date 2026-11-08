"""Challenger Mode: a title for each research question that must be defended on fresh patients every round.

A track is a campaign's primary question ("A:alcohol"). data/champions.json holds, per track, the reigning
champion's frozen claim and the record of every round. One round is one quest:
  - the world is simulated with a fresh seed (the round number), so nobody has seen these patients before;
  - the incumbent, if there is one, is carried in as a scroll whose words are frozen (hashed), and has to earn the
    title again like everyone else;
  - the Scribe forms challengers that differ from the incumbent in outcome or archetype.
The registry is written once per round: atomically (a temporary file, then os.replace), only if nobody settled
this track in between (a revision check), and at most once per run (idempotent by run id). Every number it keeps is
copied from the round's finale; nothing here measures anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from . import rules

PATH = Path(__file__).resolve().parents[3] / "data" / "champions.json"
_LOCK = threading.Lock()
RESULTS = {
    "NEW CHAMPION": "A challenger met every condition and beat the incumbent (or the title was vacant).",
    "CHAMPION DEFENDED": "The incumbent met every condition again on fresh patients, and no challenger beat it.",
    "TIE - INCUMBENT RETAINED": "A challenger matched the incumbent within the skill margin: a tie keeps the title where it is.",
    "NO ELIGIBLE CHAMPION": "Nobody met every condition this round. A reigning champion keeps the title, marked not defended.",
    "NOT APPLIED": "Another round of this track was settled while this one ran, so this result was not written.",
}
ELIGIBILITY = ("on the track's question, still standing, time-zero (new-user) design, reached the Guardian, VALIDATED "
               "(beat the baseline on the holdout), scientific status SUPPORTED or INCONCLUSIVE, and not rejected at "
               "the Trial of Truth")


def track_key(c) -> str:
    return f"{c.letter}:{c.outcomes[0].key}"


def subject_key(c) -> str:
    return f"medicine:{c.id.lower()}"


def load(path: Path = PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return {"tracks": {}, "runs": []}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"tracks": {}, "runs": [], "error": "the registry file could not be read"}
    data.setdefault("tracks", {})
    data.setdefault("runs", [])
    return data


def public(path: Path = PATH) -> dict:
    """What the title screen shows: each track's champion and its last rounds."""
    reg = load(path)
    return {"tracks": {k: {**{f: t.get(f) for f in ("track", "campaign", "letter", "outcome", "subject", "rounds",
                                                     "revision", "champion")},
                           "history": [{f: v for f, v in h.items() if f != "settled"}
                                       for h in (t.get("history") or [])[-10:]]} for k, t in reg["tracks"].items()},
            "results": RESULTS, "eligibility": ELIGIBILITY}


def frozen_spec(a) -> dict:
    """The words and structure a champion carries into every later round. Only words: numbers are re-measured."""
    s = a.scroll
    return {"title": s.title, "claim": s.claim, "archetype": s.archetype, "outcome": s.outcome, "origin": s.origin,
            "evidence_topic": s.evidence_topic or None}


def claim_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def plan(c, path: Path = PATH) -> dict:
    """The next round of this campaign's track: its number (which is also the cohort's seed), the incumbent, and the
    track's revision the round is played against."""
    t = load(path)["tracks"].get(track_key(c)) or {}
    rnd = int(t.get("rounds") or 0) + 1
    return {"track": track_key(c), "subject": subject_key(c), "round": rnd, "seed": rnd,
            "incumbent": t.get("champion"), "revision": int(t.get("revision") or 0)}


def settle(q, fin: dict, path: Path = PATH) -> dict:
    """Decide the round from the finale's numbers and write it to the registry (atomically, once)."""
    p = q.challenger
    outcome = q.c.outcomes[0].key
    rows = {r["id"]: r for r in fin["ranking"]}
    trial = q.trial or {}
    entries = []
    for a in q.agents.values():
        r = rows[a.id]
        sci = (r.get("science") or {}).get("status")
        ok, why = _eligible(a, r, sci, outcome, trial)
        reached = bool(a.encounters.get("final"))    # only a scroll that faced the Guardian has a holdout skill
        entries.append({"id": a.id, "name": a.name, "archetype": a.archetype, "outcome": a.st.outcome,
                        "incumbent": a.id == "champion", "eligible": ok, "why": why, "verdict": r["verdict"],
                        "science": sci, "ss_oos": (r.get("skill") or {}).get("ss_oos") if reached else None,
                        "hp": r["hp"]})
    inc = next((e for e in entries if e["incumbent"]), None)
    best = max((e for e in entries if e["eligible"] and not e["incumbent"]), key=_score, default=None)
    if inc and inc["eligible"]:
        if best and _beats(best, inc):
            result, winner = "NEW CHAMPION", best
        elif best and _ties(best, inc):
            result, winner = "TIE - INCUMBENT RETAINED", inc
        else:
            result, winner = "CHAMPION DEFENDED", inc
    elif best:
        result, winner = "NEW CHAMPION", best
    else:
        result, winner = "NO ELIGIBLE CHAMPION", None
    out = {"track": p["track"], "subject": p["subject"], "round": p["round"], "seed": p["seed"], "result": result,
           "why": RESULTS[result], "winner": winner["id"] if winner else None,
           "winner_name": winner["name"] if winner else None, "entries": entries, "eligibility": ELIGIBILITY,
           "incumbent": (p["incumbent"] or {}).get("hid")}
    return _write(q, p, out, winner, path)


def _eligible(a, r, sci, outcome, trial) -> tuple[bool, str]:
    if a.st.outcome != outcome:
        return False, "answers another question (a different outcome)"
    if not a.active:
        return False, "shattered"
    if a.st.design != "new_user":
        return False, "not time-zero aligned (immortal time)"
    if not a.encounters.get("final"):
        return False, "never reached the Guardian"
    if r["verdict"] != "VALIDATED":
        return False, "did not beat the comparator on the vaulted holdout"
    if sci not in ("SUPPORTED", "INCONCLUSIVE"):
        return False, f"scientific status {sci or 'NOT ASSESSED'}"
    if trial.get("scroll") == a.id and trial.get("outcome") in ("INVALID METHODOLOGY", "UNJUSTIFIED CONFIDENCE"):
        return False, f"rejected at the Trial of Truth ({trial['outcome'].lower()})"
    return True, "meets every condition"


def _score(e: dict) -> tuple:
    return (e["science"] == "SUPPORTED", e["ss_oos"] if e["ss_oos"] is not None else -9.0)


def _beats(c: dict, i: dict) -> bool:
    if _score(c)[0] != _score(i)[0]:
        return _score(c)[0] > _score(i)[0]
    return _score(c)[1] > _score(i)[1] + rules.SS_MARGIN


def _ties(c: dict, i: dict) -> bool:
    return _score(c)[0] == _score(i)[0] and abs(_score(c)[1] - _score(i)[1]) <= rules.SS_MARGIN


def _write(q, p: dict, out: dict, winner: dict | None, path: Path) -> dict:
    path = Path(path)
    with _LOCK:
        reg = load(path)
        if reg.get("error"):
            return {**out, "applied": False, "result": "NOT APPLIED", "why": reg["error"]}
        done = next((h for t in reg["tracks"].values() for h in t.get("history", []) if h.get("run_id") == q.run_id), None)
        if q.run_id in reg["runs"] and done:
            return {**done.get("settled", out), "applied": True, "duplicate": True}
        t = reg["tracks"].setdefault(p["track"], {"track": p["track"], "campaign": q.c.id, "letter": q.c.letter,
                                                  "outcome": q.c.outcomes[0].key, "subject": p["subject"],
                                                  "rounds": 0, "revision": 0, "champion": None, "history": []})
        if int(t.get("revision") or 0) != p["revision"]:
            return {**out, "applied": False, "result": "NOT APPLIED", "why": RESULTS["NOT APPLIED"],
                    "would_have_been": out["result"]}
        champ = t.get("champion")
        if out["result"] == "NEW CHAMPION":
            a = q.agents[winner["id"]]
            spec = frozen_spec(a)
            h = claim_hash(spec)
            champ = {"hid": "H-" + h[:8], "spec": spec, "claim_hash": h, "won_round": p["round"], "won_run": q.run_id,
                     "seed": p["seed"], "defended": 0, "not_defended": 0, "last_round": p["round"],
                     "ss_oos": winner["ss_oos"], "science": winner["science"]}
        elif champ and out["result"] in ("CHAMPION DEFENDED", "TIE - INCUMBENT RETAINED"):
            champ = {**champ, "defended": int(champ.get("defended") or 0) + 1, "last_round": p["round"],
                     "ss_oos": winner["ss_oos"], "science": winner["science"]}
        elif champ:
            champ = {**champ, "not_defended": int(champ.get("not_defended") or 0) + 1, "last_round": p["round"]}
        t.update(champion=champ, rounds=p["round"], revision=int(t.get("revision") or 0) + 1)
        settled = {**out, "champion": champ, "applied": True, "revision": t["revision"]}
        t["history"] = (t.get("history") or [])[-49:] + [{
            "round": p["round"], "run_id": q.run_id, "seed": p["seed"], "result": out["result"],
            "winner": out["winner_name"], "champion": (champ or {}).get("hid"), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "settled": settled}]
        reg["runs"] = (reg["runs"] + [q.run_id])[-500:]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(reg, indent=1, sort_keys=True))
        os.replace(tmp, path)
        return settled
