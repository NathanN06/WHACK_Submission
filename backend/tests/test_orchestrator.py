import pytest

from app.arena import decoys
from app.arena.ledger import load
from app.arena.agents import ScriptedLanista
from app.arena.models import Gladiator
from app.arena.orchestrator import Arena
from tests.fixtures import make_meals, make_sensor_pair


def arena(tmp_path, emperor="real", **kw):
    train = make_meals(n_people=30, seed=0)
    return Arena("t1", train, test=make_meals(n_people=20, seed=9, prefix="B"),
                 sensors=make_sensor_pair(train), emperor=emperor, n_perm=400, n_boot=300,
                 runs_dir=str(tmp_path), **kw)


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    a = arena(tmp_path_factory.mktemp("runs"))
    a.run()
    return a


def by_feature(a):
    return {s.gladiator.add_features[0]: s for s in a.states.values()}


def test_real_effects_become_champions(played):
    g = by_feature(played)
    assert g["carbs"].verdict == "CHAMPION"
    assert g["fiber"].verdict == "CHAMPION"


def test_copycat_and_noise_die(played):
    g = by_feature(played)
    assert g["calories"].verdict == "REDUNDANT"
    assert g["protein"].status in ("dead", "dropped")


def test_the_leak_is_caught_by_the_inquisitor(played):
    leak = by_feature(played)[decoys.LEAK]
    assert leak.results["added_value"]["too_good"]
    assert leak.verdict == "LEAKY"


def test_every_decoy_is_caught(played):
    summary = [e for e in played.ledger.events if e.action == "summary"][-1].result
    assert summary["total_decoys"] == 5
    assert summary["caught"] == 5
    assert by_feature(played)[decoys.EMPEROR].verdict == "CHAMPION"


def test_fake_emperor_is_not_crowned(tmp_path):
    a = arena(tmp_path, emperor="fake")
    a.run()
    assert by_feature(a)[decoys.EMPEROR].status in ("dead", "dropped")


def test_backed_leak_costs_reputation(played):
    rep_events = [e for e in played.ledger.events if e.action == "reputation"]
    assert any(e.line.startswith("Lanista reputation -20") for e in rep_events)
    assert played.reputation == 100 + 15 * sum(
        s.verdict == "CHAMPION" and s.backed for s in played.states.values()) - 20 * sum(
        s.status in ("dead", "fallen") and s.backed for s in played.states.values())


def test_ledger_is_complete_and_replayable(played):
    events = load(played.ledger.path)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert all(e.denarii >= 0 for e in events)
    assert events[0].action == "day_start" and events[-1].action == "summary"


def test_survivors_are_preregistered_before_the_boss(played):
    for s in played.states.values():
        if "final_boss" in s.results:
            assert s.prereg_hash is not None


def test_running_out_of_money_leaves_gladiators_unproven(tmp_path, monkeypatch):
    from app.arena import config
    monkeypatch.setattr(config, "STARTING_DENARII", 3)
    a = arena(tmp_path)
    a.play_day(1)
    carbs = by_feature(a)["carbs"]
    assert carbs.status == "unproven" and a.denarii >= 0


def test_gate_turns_away_bad_and_repeat_gladiators(tmp_path):
    from app.arena.models import Gladiator

    class Repeater:  # a Lanista that keeps proposing the same idea and one made-up column
        def propose(self, day, catalog, graveyard, k):
            return [Gladiator(id="x", claim="fibre", add_features=["fiber"]),
                    Gladiator(id="y", claim="fibre again", add_features=["fiber"]),
                    Gladiator(id="z", claim="vibes", add_features=["vibes"])]

        def decide(self, state):
            return False, "drop"

    a = arena(tmp_path, lanista=Repeater())
    a.play_day(2)
    rejected = [e.line for e in a.ledger.events if e.action == "rejected"]
    assert len(a.states) == 1 and len(rejected) == 2
    assert any("already fought" in r for r in rejected) and any("unknown" in r for r in rejected)


def test_census_kills_a_survivor_once_enough_claims_are_tried(tmp_path):
    from app.arena.models import Gladiator, GladiatorState
    a = arena(tmp_path)
    for i, p in enumerate([0.02, 0.5, 0.6, 0.7, 0.8]):
        s = GladiatorState(gladiator=Gladiator(id=f"X{i}", claim="x", add_features=["fiber"]),
                           backed=True, status="survivor" if i == 0 else "dead")
        s.results["shuffle_test"] = {"p": p, "passed": p < 0.05}
        a.states[s.gladiator.id] = s
    a.census()
    assert a.states["X0"].verdict == "LUCKY"  # 0.02 * 5 = 0.10 after the Census
    assert a.reputation == 80


def test_crowd_theory_runs_without_stakes(tmp_path):
    a = arena(tmp_path)
    s = a.exhibition("Fibre flattens the spike")
    assert s.gladiator.add_features == ["fiber"] and s.verdict == "CHAMPION"
    assert a.reputation == 100
    assert a.exhibition("pineapple on pizza") is None


def test_real_emperor_does_not_touch_anyone_elses_outcome(tmp_path):
    train = make_meals(n_people=30, seed=0)
    test = make_meals(n_people=20, seed=9, prefix="B")
    a = Arena("e1", train, test=test, emperor="real", n_perm=10, n_boot=50, runs_dir=str(tmp_path))
    assert (a.train["rise"].to_numpy() == train["rise"].to_numpy()).all()
    assert (a.test["rise"].to_numpy() == test["rise"].to_numpy()).all()
    s = a.enter(Gladiator(id="x", claim="plant", add_features=[decoys.EMPEROR], origin="emperor"),
                actor="emperor", auto_back=False)
    assert s.gladiator.target == decoys.EMPEROR_TARGET


def test_census_counts_every_claim_the_trial_judged(played):
    judged = sum(1 for s in played.states.values()
                 if "added_value" in s.results and not s.results["added_value"].get("untestable"))
    ms = [r["m"] for s in played.states.values() for t, r in s.results.items() if t == "penalty"]
    assert ms and max(ms) == judged


def test_a_crash_mid_game_is_written_to_the_ledger(tmp_path):
    class Broken:
        def propose(self, day, catalog, graveyard, k):
            raise RuntimeError("boom")

    a = arena(tmp_path, lanista=Broken())
    a.run()
    actions = [e.action for e in a.ledger.events]
    assert "error" in actions and actions[-1] == "summary"


def test_crowd_theory_fights_with_the_validated_features(tmp_path):
    class Greedy(ScriptedLanista):
        def theory(self, text, catalog):
            return Gladiator(id="new", claim=text, add_features=["carbs", "fiber", "fat", "protein"],
                             origin="crowd")

    a = arena(tmp_path, lanista=Greedy())
    s = a.exhibition("everything")
    assert s.gladiator.add_features == ["fiber", "fat"]
