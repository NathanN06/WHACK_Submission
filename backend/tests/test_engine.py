import numpy as np
import pytest

from app.arena import engine
from app.arena.features import default_registry
from app.arena.models import Gladiator
from tests.fixtures import make_meals, make_sensor_pair


def glad(*add, base=("carbs",), gid="H1"):
    return Gladiator(id=gid, claim="test", add_features=list(add), baseline_features=list(base))


@pytest.fixture(scope="module")
def meals():
    df = make_meals(n_people=30, meals=40, seed=0)
    df["noise"] = np.random.default_rng(1).normal(size=len(df))
    return df


def test_folds_never_split_a_person(meals):
    for tr, te in engine.participant_folds(meals):
        assert set(meals.participant_id.iloc[tr]).isdisjoint(meals.participant_id.iloc[te])


def test_trial_passes_a_real_feature(meals):
    r = engine.added_value(meals, glad("fiber"), n_boot=300)
    assert r["passed"] and r["gain"] > 0 and r["ci_low"] > 0
    assert r["direction"]["fiber"] == "negative"


def test_trial_rejects_noise(meals):
    r = engine.added_value(meals, glad("noise"), n_boot=300)
    assert not r["passed"]


def test_trial_marks_copycat_as_correlated(meals):
    r = engine.added_value(meals, glad("calories"), n_boot=300)
    assert not r["passed"]
    assert r["standalone_r"] > 0.15  # correlates alone, adds nothing beyond carbs


def test_trial_untestable_with_few_people():
    df = make_meals(n_people=5, meals=20)
    r = engine.added_value(df, glad("fiber"))
    assert r["untestable"] and not r["passed"]


def test_trial_untestable_when_column_missing(meals):
    r = engine.added_value(meals, glad("not_a_column"))
    assert r["untestable"]


def test_shuffler_spares_real_and_kills_noise(meals):
    assert engine.shuffle_test(meals, glad("fiber"), n_perm=100)["p"] < 0.05
    assert engine.shuffle_test(meals, glad("noise"), n_perm=100)["p"] > 0.05


def test_shuffler_handles_person_level_feature(meals):
    r = engine.shuffle_test(meals, glad("hba1c"), n_perm=100)
    assert r["passed"]  # HbA1c really shifts each person's rise in the fixture


def test_census_benjamini_hochberg():
    out = engine.penalty({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
    assert out["a"]["p_adj"] == pytest.approx(0.04)
    assert out["b"]["p_adj"] == pytest.approx(0.04 * 4 / 3)
    assert out["c"]["p_adj"] == pytest.approx(0.04 * 4 / 3)
    assert out["d"]["p_adj"] == pytest.approx(0.5)
    assert [k for k, v in out.items() if v["passed"]] == ["a"]


def test_inquisitor_finds_outcome_features():
    reg = default_registry()
    from app.arena.features import Feature, register
    reg = register(reg, Feature("time_to_peak", 4, "outcome", "Minutes to peak"))
    assert not engine.leak_audit(glad("time_to_peak"), reg)["passed"]
    assert engine.leak_audit(glad("fiber"), reg)["passed"]
    assert not engine.leak_audit(glad("made_up"), reg)["passed"]


def test_twins_agree_and_disagree(meals):
    agree = engine.sensor_check(make_sensor_pair(meals), glad("fiber"))
    assert agree["passed"]
    disagree = engine.sensor_check(make_sensor_pair(meals, fiber_on_second=False), glad("fiber"))
    assert not disagree["passed"]


def test_champion_of_brno():
    train = make_meals(n_people=30, seed=0)
    same_truth = make_meals(n_people=20, seed=7, prefix="B")
    no_fiber = make_meals(n_people=20, seed=7, prefix="B", fiber_effect=0.0)
    assert engine.final_boss(train, same_truth, glad("fiber"), n_boot=300)["passed"]
    assert not engine.final_boss(train, no_fiber, glad("fiber"), n_boot=300)["passed"]
    assert engine.final_boss(train, same_truth.drop(columns="fiber"), glad("fiber"))["untestable"]
