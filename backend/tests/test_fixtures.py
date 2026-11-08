from tests.fixtures import make_meals, make_sensor_pair


def test_fixture_has_the_truth_we_rely_on():
    df = make_meals()
    assert df.participant_id.nunique() == 30 and len(df) == 30 * 40
    assert df.groupby("participant_id")["hba1c"].nunique().max() == 1  # person-level
    assert df["rise"].corr(df["carbs"]) > 0.5
    assert df["rise"].corr(df["fiber"]) < 0
    assert df["calories"].corr(df["carbs"]) > 0.5  # the copycat


def test_sensor_pair_shares_meals():
    pair = make_sensor_pair(make_meals(n_people=5, meals=10))
    assert list(pair) == ["libre", "dexcom"]
    assert (pair["libre"].meal_event_id == pair["dexcom"].meal_event_id).all()
