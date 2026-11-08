import pytest
from pydantic import ValidationError

from app.arena import config
from app.arena.models import Event, Gladiator, GladiatorState


def test_gladiator_needs_at_least_one_feature():
    with pytest.raises(ValidationError):
        Gladiator(id="G1", claim="nothing", add_features=[])


def test_new_gladiator_waits_in_the_tunnel_at_full_hp():
    s = GladiatorState(gladiator=Gladiator(id="G1", claim="fibre helps", add_features=["fiber"]))
    assert (s.hp, s.status, s.alive) == (config.STARTING_HP, "tunnel", True)
    assert s.gladiator.baseline_features == ["carbs"]


def test_event_rejects_unknown_actor():
    with pytest.raises(ValidationError):
        Event(run_id="r", seq=1, ts=0.0, actor="spectator", action="cheer")
