"""The referee: turns engine results into damage, deaths and verdicts. No LLM involved."""

from . import config
from .models import GladiatorState

DEATH_VERDICT = {
    "leak_audit": "LEAKY",
    "shuffle_test": "LUCKY",
    "penalty": "LUCKY",
    "sensor_check": "LUCKY",
    "final_boss": "FALLEN",
}


def apply_result(state: GladiatorState, test: str, result: dict) -> int:
    """Record a result on the gladiator. Returns the damage dealt."""
    state.results[test] = result
    if result.get("untestable"):
        if test == "final_boss":
            state.status, state.verdict = "untestable", "UNTESTABLE"
        elif test == "added_value":
            state.status, state.verdict, state.hp = "dead", "UNTESTABLE", 0
        return 0
    if result["passed"]:
        if test == "final_boss":
            state.status, state.verdict = "champion", "CHAMPION"
        return 0
    damage = config.DAMAGE[test]
    state.hp = max(0, state.hp - damage)
    state.wounds.append(test)
    if state.hp == 0:
        state.status = "fallen" if test == "final_boss" else "dead"
        state.verdict = _death_verdict(test, result)
    return damage


def _death_verdict(test: str, result: dict) -> str:
    if test == "added_value":
        return "REDUNDANT" if result.get("standalone_r", 0) >= config.REDUNDANT_CORR else "NO_EDGE"
    return DEATH_VERDICT[test]


def crown_survivor(state: GladiatorState) -> bool:
    """A gladiator survives the arena only after the Trial, the Inquisitor and the Shuffler."""
    needed = ("added_value", "leak_audit", "shuffle_test")
    if state.alive and all(state.results.get(t, {}).get("passed") for t in needed):
        state.status, state.verdict = "survivor", "SURVIVOR"
        return True
    return False


def reputation_change(state: GladiatorState) -> int:
    """How the Lanista's reputation moves when this gladiator's fate is settled."""
    if not state.backed:
        return 0
    if state.status in ("dead", "fallen"):
        return -config.REPUTATION_LOSS_ON_DEATH
    if state.status == "champion":
        return config.REPUTATION_GAIN_ON_CHAMPION
    return 0
