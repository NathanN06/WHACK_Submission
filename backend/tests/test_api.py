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


def test_roster_endpoint_is_one_list_with_every_feature(client):
    body = client.get("/api/roster").json()
    assert {"carbs", "fiber", "hba1c"} <= {f["name"] for f in body["features"]}
    assert body["hypotheses"][0]["add_features"] == ["carbs"] and body["max_in"] >= 1


def test_a_game_plays_your_list_up_to_the_max(client):
    hyps = [{"claim": "HbA1c matters", "add_features": ["hba1c"]},
            {"claim": "My fibre hunch", "add_features": ["fiber"]},
            {"claim": "Carbs drive it", "add_features": ["carbs"]},
            {"claim": "Over the max", "add_features": ["fat"]}]
    run_id = client.post("/api/runs", json={"hypotheses": hyps, "max_in": 3, "pace": 0}).json()["run_id"]
    proposed = [e["line"] for e in wait_for(client, run_id)
                if e["action"] == "propose" and e["actor"] == "lanista"]
    assert proposed == ["Carbs drive it", "My fibre hunch", "HbA1c matters"]  # played in unlock order


def test_roster_requests_are_bounded(client):
    assert client.post("/api/runs", json={"max_in": 0}).status_code == 422
    too_many = [{"claim": "x", "add_features": ["fiber", "fat", "sugar"]}]
    assert client.post("/api/runs", json={"hypotheses": too_many}).status_code == 422


def test_claude_is_used_automatically_when_a_key_exists(client, monkeypatch):
    used = []
    real = main.make_agents
    monkeypatch.setattr(main, "make_agents", lambda llm: used.append(llm) or real(False))
    for available in (True, False):
        monkeypatch.setattr(main, "llm_available", lambda: available)
        assert client.get("/api/status").json() == {"claude": available}
        wait_for(client, client.post("/api/runs", json={"pace": 0}).json()["run_id"])
    assert used == [True, False]


@pytest.fixture
def quest_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "QUESTS", tmp_path)
    # hermetic: never call Claude from the tests, even when a real key sits in .env
    monkeypatch.setattr(main, "llm_available", lambda: False)
    monkeypatch.setattr(main, "client_or_none", lambda use: None)
    return TestClient(main.app)


def wait_for_quest(client, quest_id, timeout=120):
    seen, deadline = [], time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/quests/{quest_id}/events", params={"after": len(seen)}).json()
        seen += body["events"]
        if body["done"]:
            return seen
        time.sleep(0.1)
    raise TimeoutError


def test_a_quest_streams_to_the_finale_and_replays(quest_client):
    quest_id = quest_client.post("/api/quests", json={"campaign": "A", "llm": False}).json()["quest_id"]
    events = wait_for_quest(quest_client, quest_id)
    assert events[0]["action"] == "quest_start" and events[-1]["action"] == "finale"
    replay = quest_client.post("/api/quests", json={"replay": quest_id}).json()["quest_id"]
    assert [e["line"] for e in wait_for_quest(quest_client, replay)] == [e["line"] for e in events]
    assert quest_id in quest_client.get("/api/quests").json()
    rules = quest_client.get("/api/quests-rules").json()
    assert rules["d_max"]["4"] == 60 and rules["starting_hp"] == 100
    assert [c["letter"] for c in quest_client.get("/api/campaigns").json()] == ["A", "B", "C", "D"]


def test_live_quests_get_fresh_cohorts_and_a_champion_defends_its_title(quest_client):
    assert quest_client.post("/api/quests", json={"campaign": "A", "scrolls": 1}).status_code == 422   # never one scroll
    assert quest_client.get("/api/champions").json() == {}
    first = wait_for_quest(quest_client, quest_client.post("/api/quests", json={"campaign": "A", "llm": False,
                                                                                "scrolls": 3}).json()["quest_id"])
    second = wait_for_quest(quest_client, quest_client.post("/api/quests", json={"campaign": "A", "llm": False,
                                                                                 "scrolls": 3}).json()["quest_id"])
    seeds = [q[0]["result"]["cohort"]["seed"] for q in (first, second)]
    assert seeds == [1, 2] and all(q[0]["result"]["cohort"]["fresh"] for q in (first, second))   # never the demo's seed 0
    champ = quest_client.get("/api/champions").json()["GLP1_ADDICTION"]
    assert second[0]["result"]["incumbent"]["hypothesis_id"] == champ["hypothesis"]["hypothesis_id"]
    assert next(e for e in second if e["action"] == "champion")["result"]["outcome"] in ("DEFENDED", "REPLACED", "UNRESOLVED")
    campaigns = {c["letter"]: c for c in quest_client.get("/api/campaigns").json()}
    card = campaigns["A"]["champion"]
    assert card and card["title"] and "not clinical evidence" in card["label"].lower()
    assert campaigns["A"]["last_quest"]["quest_id"] == second[0]["run_id"]          # the latest round, not the first
    assert campaigns["B"]["champion"] is None and campaigns["B"]["last_quest"] is None


def test_the_ui_is_always_revalidated_so_a_stale_script_never_hides_new_features(quest_client):
    assert quest_client.get("/").headers["cache-control"] == "no-cache"
    assert quest_client.get("/pep.js").headers["cache-control"] == "no-cache"
    assert "cache-control" not in {k.lower() for k in quest_client.get("/api/campaigns").headers if k.lower() == "cache-control"} \
        or quest_client.get("/api/campaigns").headers.get("cache-control") != "no-cache"


def test_unknown_campaigns_and_paths_are_refused(quest_client, tmp_path):
    (tmp_path.parent / "secret.jsonl").write_text("")
    assert quest_client.post("/api/quests", json={"campaign": "Z"}).status_code == 404
    assert quest_client.post("/api/quests", json={"replay": "../secret"}).status_code == 404
    assert quest_client.get("/api/quests/..%2Fsecret/events").status_code == 404


def test_leaving_stops_a_live_quest(quest_client):
    body = {"campaign": "B", "llm": False, "pace": 0.05}
    quest_id = quest_client.post("/api/quests", json=body).json()["quest_id"]
    time.sleep(0.3)
    assert quest_client.post(f"/api/quests/{quest_id}/stop").json() == {"stopped": True}
    events = wait_for_quest(quest_client, quest_id, timeout=10)
    assert events[-1]["action"] == "stopped"
    assert not any(e["action"] == "finale" for e in events)
    assert quest_client.post("/api/quests/nope/stop").status_code == 404


def test_run_paths_stay_in_the_runs_folder_and_pace_is_bounded(client, tmp_path):
    (tmp_path.parent / "secret.jsonl").write_text("")
    assert client.get("/api/runs/..%2Fsecret/events").status_code == 404
    assert client.post("/api/runs", json={"pace": -1}).status_code == 422
    assert client.post("/api/runs", json={"pace": 1e9}).status_code == 422


def test_the_directors_console_over_http(quest_client):
    c = quest_client
    qid = c.post("/api/quests", json={"campaign": "A", "llm": False, "interactive": True}).json()["quest_id"]
    time.sleep(1.5)
    out = c.post(f"/api/quests/{qid}/chat", json={"mode": "CHALLENGE", "text": "Could this be luck?", "target": "pioneer",
                                                  "request_id": "x1"})
    assert out.status_code == 200, out.text
    mid = out.json()["mystery"]["id"]
    fight = c.post(f"/api/quests/{qid}/mystery/{mid}", json={"action": "summon", "request_id": "x2"})
    assert fight.status_code == 200, fight.text
    assert fight.json()["mystery"]["status"] in ("survived", "fallen")
    again = c.post(f"/api/quests/{qid}/mystery/{mid}", json={"action": "summon", "request_id": "x3"})
    assert again.status_code == 409
    assert c.post(f"/api/quests/{qid}/bridge", json={"choice": "cross"}).status_code == 409   # not at the bridge yet
    for lv in (1, 2, 3, 4):
        c.post(f"/api/quests/{qid}/advance", json={"level": lv})
    for _ in range(200):
        if c.get(f"/api/quests/{qid}/director").json()["waiting"] == "bridge":
            break
        time.sleep(0.1)
    assert c.post(f"/api/quests/{qid}/bridge", json={"choice": "inconclusive", "request_id": "b1"}).status_code == 200
    events = wait_for_quest(c, qid)
    assert events[-1]["action"] == "finale" and events[-1]["result"]["overworld"]["trial"]["outcome"] == "JUSTIFIED UNCERTAINTY"


def test_a_recording_has_no_console(quest_client):
    qid = quest_client.post("/api/quests", json={"campaign": "A", "llm": False}).json()["quest_id"]
    assert quest_client.post(f"/api/quests/{qid}/chat", json={"mode": "ASK", "text": "hi"}).status_code == 409
