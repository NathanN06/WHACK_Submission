"""The evidence ledger: append-only JSON Lines, one file per run.

Every event the UI shows comes from here, so every number on screen is auditable.
JSONL is also queryable later: duckdb -c "FROM read_json('data/runs/r1.jsonl')".
"""

import hashlib
import json
import threading
import time
from pathlib import Path

from .models import Event, Gladiator


class Ledger:
    def __init__(self, run_id: str, directory: str | Path = "data/runs", on_write=None):
        self.run_id = run_id
        self.path = Path(directory) / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("")
        self.events: list[Event] = []
        self.on_write = on_write  # optional callback, e.g. print each event live
        self._lock = threading.Lock()

    def write(self, **fields) -> Event:
        with self._lock:
            event = Event(run_id=self.run_id, seq=len(self.events) + 1, ts=time.time(), **fields)
            self.events.append(event)
            with self.path.open("a") as f:
                f.write(event.model_dump_json() + "\n")
        if self.on_write:
            self.on_write(event)
        return event

    def since(self, seq: int) -> list[Event]:
        with self._lock:
            return list(self.events[seq:])


def load(path: str | Path) -> list[Event]:
    return [Event.model_validate_json(line) for line in Path(path).read_text().splitlines() if line]


def preregister(g: Gladiator) -> str:
    """Lock a gladiator before the Final Boss: any later edit changes this hash."""
    blob = json.dumps(g.model_dump(), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()
