from app.arena import referee
from app.arena.models import Gladiator, GladiatorState


def state(backed=True):
    g = Gladiator(id="H1", claim="fibre helps", add_features=["fiber"])
    return GladiatorState(gladiator=g, backed=backed, status="arena")


def test_failed_trial_is_redundant_or_no_edge():
    s = state()
    referee.apply_result(s, "added_value", {"passed": False, "standalone_r": 0.4})
    assert (s.hp, s.status, s.verdict) == (0, "dead", "REDUNDANT")
    s = state()
    referee.apply_result(s, "added_value", {"passed": False, "standalone_r": 0.02})
    assert s.verdict == "NO_EDGE"


def test_inquisitor_kills_as_leaky():
    s = state()
    assert referee.apply_result(s, "leak_audit", {"passed": False, "leaky": ["x"]}) == 100
    assert s.verdict == "LEAKY"


def test_twins_wound_but_do_not_kill():
    s = state()
    referee.apply_result(s, "sensor_check", {"passed": False})
    assert s.hp == 50 and s.status == "arena" and s.wounds == ["sensor_check"]
    referee.apply_result(s, "sensor_check", {"passed": False})
    assert s.hp == 0 and s.verdict == "LUCKY"


def test_survivor_needs_trial_inquisitor_and_shuffler():
    s = state()
    referee.apply_result(s, "added_value", {"passed": True})
    referee.apply_result(s, "shuffle_test", {"passed": True})
    assert not referee.crown_survivor(s)
    referee.apply_result(s, "leak_audit", {"passed": True})
    assert referee.crown_survivor(s) and s.verdict == "SURVIVOR"


def test_champion_and_fallen():
    s = state()
    referee.apply_result(s, "final_boss", {"passed": True})
    assert s.verdict == "CHAMPION" and referee.reputation_change(s) == 15
    s = state()
    referee.apply_result(s, "final_boss", {"passed": False})
    assert s.verdict == "FALLEN" and referee.reputation_change(s) == -20


def test_unbacked_deaths_cost_nothing():
    s = state(backed=False)
    referee.apply_result(s, "shuffle_test", {"passed": False})
    assert referee.reputation_change(s) == 0


def test_untestable_in_holdout_is_not_a_death():
    s = state()
    referee.apply_result(s, "final_boss", {"passed": False, "untestable": True})
    assert s.status == "untestable" and s.hp == 100
