import pytest

from app.arena.features import default_registry
from app.arena.ledger import Ledger
from app.arena.models import Gladiator
from app.gauntlet import checks, rules
from app.gauntlet.campaign import Gauntlet
from app.gauntlet.models import QuestEvent
from tests.fixtures import make_meals, make_quest_world


@pytest.fixture(scope="module")
def quest(tmp_path_factory):
    train, test, sensors = make_quest_world(0, n_train=24, n_test=16)
    ledger = Ledger("q-test", tmp_path_factory.mktemp("quests"), model=QuestEvent)
    g = Gauntlet("q-test", train, test, sensors, ledger=ledger, n_perm=40, n_boot=150, seed=0)
    result = g.run()
    return g, result, ledger.events


def by_feature(g, result):
    feats = {h.id: h.gladiator.add_features[0] for h in g.heroes.values()}
    return {feats[r["id"]]: r for r in result["ranking"]}


def test_quest_reaches_the_finale_through_four_levels(quest):
    _, result, events = quest
    assert result is not None and events[-1].action == "finale"
    assert [e.level for e in events if e.action == "level_complete"] == [1, 2, 3, 4]
    assert not [e for e in events if e.action == "error"]


def test_true_effects_validate_and_every_decoy_is_caught(quest):
    g, result, _ = quest
    rows = by_feature(g, result)
    assert rows["carbs"]["verdict"] == "VALIDATED"
    assert rows["fiber"]["verdict"] == "VALIDATED"
    assert result["caught"] == len(result["decoys"]) == 4
    assert rows["meal_intensity_score"]["verdict"] == "FALLEN"  # the Leakage Reaper


def test_future_information_is_disqualified_even_when_accurate(quest):
    g, result, _ = quest
    walk = by_feature(g, result)["steps_after"]
    assert walk["verdict"] == "LOOK-AHEAD"
    hero = g.heroes[walk["id"]]
    assert hero.results["added_value"]["passed"]  # it really did predict well
    assert hero.results["temporal"]["passed"] is False


def test_every_hp_change_follows_the_rulebook(quest):
    _, _, events = quest
    for e in events:
        if e.action == "result" and not (e.result or {}).get("untestable"):
            enc = rules.ENCOUNTERS[e.enemy]
            if e.passed:
                assert 0 <= e.hp_delta <= rules.PASS_HEAL
            else:
                worst = max(enc["damage"], enc.get("damage_severe", 0))
                assert -worst <= e.hp_delta <= 0
        if e.action == "concede":
            assert -rules.CONCEDE_DAMAGE <= e.hp_delta <= 0
        if e.hp is not None:
            assert 0 <= e.hp <= rules.STARTING_HP
        if e.credits is not None:
            assert e.credits >= 0


def test_decoys_stay_hidden_until_the_finale(quest):
    _, _, events = quest
    recruits = [e for e in events if e.action == "recruit"]
    assert all("origin" not in e.agent for e in recruits)
    assert len(events[-1].result["decoys"]) == 4


def test_runs_are_reproducible(tmp_path):
    train, test, sensors = make_quest_world(1, n_train=14, n_test=12)

    def lines(d):
        ledger = Ledger("q", tmp_path / d, model=QuestEvent)
        Gauntlet("q", train, test, sensors, ledger=ledger, n_perm=20, n_boot=50, seed=3, max_heroes=3).run()
        return [(e.line, e.hp) for e in ledger.events]

    assert lines("a") == lines("b")


def test_inconclusive_when_nothing_survives(tmp_path):
    train = make_meals(14, seed=2)
    ledger = Ledger("q", tmp_path, model=QuestEvent)
    roster = [{"claim": "Protein matters", "add_features": ["protein"]}]
    result = Gauntlet("q", train, make_meals(12, seed=5, prefix="B"), {}, ledger=ledger, hypotheses=roster,
                      with_decoys=False, n_perm=20, n_boot=50).run()
    assert result["validated"] == 0 and "inconclusive" in result["conclusion"]


# ---------- the checks ----------

def test_echo_catches_a_copy_of_carbs():
    df = make_meals(12, seed=0)
    df["copy"] = df["carbs"] * 1.1
    g = Gladiator(id="x", claim="", add_features=["copy"], baseline_features=["carbs"])
    assert checks.echo(df, g)["passed"] is False
    g2 = g.model_copy(update={"add_features": ["protein"]})
    assert checks.echo(df, g2)["passed"] is True


def test_raw_direction_spots_a_contradiction():
    df = make_meals(20, seed=0)  # fibre lowers the rise
    wrong = Gladiator(id="x", claim="", add_features=["fiber"], expected_direction="positive")
    right = wrong.model_copy(update={"expected_direction": "negative"})
    assert checks.raw_direction(df, wrong, 200)["contradicted"]
    assert checks.raw_direction(df, right, 200)["passed"]


def test_person_level_traits_cannot_be_anecdote_checked():
    df = make_meals(12, seed=0)
    g = Gladiator(id="x", claim="", add_features=["hba1c"], baseline_features=["carbs"])
    assert checks.within_person(df, g)["untestable"]


def test_temporal_flags_after_meal_features():
    reg = default_registry()
    assert checks.temporal(Gladiator(id="x", claim="", add_features=["steps_after"]), reg)["passed"] is False
    assert checks.temporal(Gladiator(id="x", claim="", add_features=["fiber"]), reg)["passed"] is True


def test_coverage_and_provenance_need_enough_people():
    df = make_meals(12, seed=0)
    g = Gladiator(id="x", claim="", add_features=["nope"])
    assert checks.coverage(df, g)["untestable"]
    assert checks.provenance(df.drop(columns="fiber"),
                             Gladiator(id="x", claim="", add_features=["fiber"]))["untestable"]
