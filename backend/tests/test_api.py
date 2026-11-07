import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from tests.fixtures import make_meals, make_sensor_pair  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    train = make_meals(30, seed=0)
    monkeypatch.setattr(main, "frames",
                        lambda: (train, make_meals(20, seed=9, prefix="B"), make_sensor_pair(train)))
    monkeypatch.setattr(main, "RUNS", tmp_path)
    return TestClient(main.app)


def wait_for(client, run_id, timeout=60):
    seen, deadline = [], time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/runs/{run_id}/events", params={"after": len(seen)}).json()
        seen += body["events"]
        if body["done"]:
            return seen
        time.sleep(0.1)
    raise TimeoutError


def test_a_game_streams_to_the_end_and_replays(client):
    run_id = client.post("/api/runs", json={"emperor": "real", "pace": 0}).json()["run_id"]
    events = wait_for(client, run_id)
    assert events[-1]["action"] == "summary"
    replay = client.post("/api/runs", json={"replay": run_id, "pace": 0}).json()["run_id"]
    assert [e["line"] for e in wait_for(client, replay)] == [e["line"] for e in events]
    assert run_id in client.get("/api/runs").json()


def test_crowd_theory(client):
    body = client.post("/api/theory", json={"text": "fibre flattens the spike"}).json()
    assert body["verdict"] == "CHAMPION"
    assert client.post("/api/theory", json={"text": "pineapple"}).json()["verdict"] is None


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/events").status_code == 404


def test_replay_cannot_leave_the_runs_folder(client, tmp_path):
    (tmp_path.parent / "secret.jsonl").write_text("")
    assert client.post("/api/runs", json={"replay": "../secret", "pace": 0}).status_code == 404


def test_done_is_decided_before_reading_events(client):
    class Thread:
        alive = True

        def is_alive(self):
            return self.alive

    thread = Thread()

    class Ledger:  # the run finishes (and writes its last event) while we read
        def since(self, after):
            thread.alive = False
            return []

    main._runs["race"] = {"ledger": Ledger(), "thread": thread}
    assert client.get("/api/runs/race/events").json()["done"] is False


def test_roster_endpoint_lists_days_features_and_defaults(client):
    days = client.get("/api/roster").json()["days"]
    assert [d["day"] for d in days] == [1, 2, 3]
    assert "fiber" in days[1]["features"] and days[1]["hypotheses"]
    assert all(f["name"] for d in days for f in d["catalog"])


def test_a_game_plays_your_roster(client):
    roster = {"1": [{"claim": "Carbs drive it", "add_features": ["carbs"]}],
              "2": [{"claim": "My fibre hunch", "add_features": ["fiber"]}], "3": []}
    run_id = client.post("/api/runs", json={"roster": roster, "max_per_day": 3, "pace": 0}).json()["run_id"]
    proposed = [e["line"] for e in wait_for(client, run_id)
                if e["action"] == "propose" and e["actor"] == "lanista"]
    assert proposed == ["Carbs drive it", "My fibre hunch"]


def test_roster_requests_are_bounded(client):
    assert client.post("/api/runs", json={"max_per_day": 0}).status_code == 422
    too_many = {"2": [{"claim": "x", "add_features": ["fiber", "fat", "sugar"]}]}
    assert client.post("/api/runs", json={"roster": too_many}).status_code == 422
