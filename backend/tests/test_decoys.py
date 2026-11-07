import numpy as np

from app.arena import decoys, engine
from app.arena.models import Gladiator
from tests.fixtures import make_meals, make_sensor_pair


def glad(feature):
    return Gladiator(id=feature, claim="decoy", add_features=[feature])


def test_leak_looks_amazing_at_the_trial():
    df = make_meals()
    p = decoys.plan(df, "rise", emperor=None, seed=3)
    d = decoys.attach(df, "rise", p)
    r = engine.added_value(d, glad(decoys.LEAK), n_boot=200)
    assert r["passed"] and r["too_good"]


def test_copycat_adds_nothing_beyond_carbs():
    df = make_meals()
    d = decoys.attach(df, "rise", decoys.plan(df, "rise", None, 3))
    r = engine.added_value(d, glad(decoys.COPYCAT), n_boot=200)
    assert not r["passed"] and r["standalone_r"] > 0.15


def test_lucky_winner_is_the_best_of_a_hundred_noise_columns():
    df = make_meals()
    p = decoys.plan(df, "rise", None, seed=3)
    gains = decoys.lucky_gains(df, "rise", seed=3)
    assert p.lucky_source == int(np.argmax(gains))
    d = decoys.attach(df, "rise", p)
    draws = np.random.default_rng(3).normal(size=(decoys.N_LUCKY_DRAWS, len(df)))
    assert np.allclose(d[decoys.LUCKY], draws[p.lucky_source])


def test_lucky_winner_is_fresh_noise_in_the_holdout():
    df = make_meals()
    p = decoys.plan(df, "rise", None, seed=3)
    holdout = decoys.attach(make_meals(n_people=20, seed=9, prefix="B"), "rise", p, salt=1)
    r = engine.added_value(holdout, glad(decoys.LUCKY), n_boot=200)
    assert not r["passed"]


def test_second_sensor_gets_the_same_decoys_per_meal():
    df = make_meals()
    p = decoys.plan(df, "rise", "real", seed=3)
    pair = make_sensor_pair(df)
    a = decoys.attach(pair["libre"], "rise", p)
    b = decoys.attach(pair["dexcom"].iloc[::-1], "rise", p, like=a)  # different row order
    merged = a.merge(b, on="meal_event_id")
    assert np.allclose(merged[f"{decoys.EMPEROR}_x"], merged[f"{decoys.EMPEROR}_y"])
    assert np.allclose(merged[f"{decoys.LUCKY}_x"], merged[f"{decoys.LUCKY}_y"])


def test_emperors_real_plant_is_detectable_and_fake_is_not():
    df = make_meals()
    real = decoys.attach(df, "rise", decoys.plan(df, "rise", "real", 3))
    fake = decoys.attach(df, "rise", decoys.plan(df, "rise", "fake", 3))
    plant = glad(decoys.EMPEROR).model_copy(update={"target": decoys.EMPEROR_TARGET})
    assert engine.added_value(real, plant, n_boot=200)["passed"]
    assert not engine.added_value(fake, plant, n_boot=200)["passed"]
    assert (real["rise"] == df["rise"]).all()  # nobody else's outcome moves


def test_caught_rules():
    assert decoys.caught(decoys.LEAK, "dead")
    assert not decoys.caught(decoys.LEAK, "survivor")
    assert decoys.caught(decoys.EMPEROR, "champion", emperor="real")
    assert decoys.caught(decoys.EMPEROR, "dropped", emperor="fake")
    assert not decoys.caught(decoys.EMPEROR, "dead", emperor="real")
