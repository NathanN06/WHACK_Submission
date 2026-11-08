"""Shared data shapes. These are the contract between engine, agents, API and UI."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from . import config

Origin = Literal["researcher", "decoy", "emperor", "crowd", "fallback"]
Status = Literal["tunnel", "arena", "dead", "dropped", "unproven", "survivor",
                 "champion", "fallen", "untestable"]


class Gladiator(BaseModel):
    """One hypothesis: adding these features predicts the target better than the baseline."""

    id: str
    claim: str
    target: str = "rise"
    add_features: list[str] = Field(min_length=1)
    baseline_features: list[str] = Field(default_factory=lambda: ["carbs"])
    expected_direction: Literal["positive", "negative", "either"] = "either"
    day: int = 1
    origin: Origin = "researcher"


class GladiatorState(BaseModel):
    gladiator: Gladiator
    hp: int = config.STARTING_HP
    backed: bool = False
    status: Status = "tunnel"
    verdict: str | None = None
    wounds: list[str] = Field(default_factory=list)
    results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    prereg_hash: str | None = None

    @property
    def alive(self) -> bool:
        return self.status in ("tunnel", "arena", "survivor")


class Event(BaseModel):
    """One append-only ledger row. The UI is a view of these."""

    run_id: str
    seq: int
    ts: float
    day: int | None = None
    actor: Literal["lanista", "sceptic", "engine", "emperor", "crowd", "system"]
    action: str
    gladiator_id: str | None = None
    gladiator: dict[str, Any] | None = None
    test: str | None = None
    result: dict[str, Any] | None = None
    passed: bool | None = None
    hp: int | None = None
    status: str | None = None
    verdict: str | None = None
    reputation: int | None = None
    denarii: int | None = None
    line: str | None = None
