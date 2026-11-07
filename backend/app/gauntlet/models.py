"""Data shapes for the gauntlet: one hypothesis agent, and one ledger row."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..arena.models import Gladiator
from . import rules


class QuestEvent(BaseModel):
    """One append-only ledger row. The game screen is a view of these."""

    run_id: str
    seq: int
    ts: float
    level: int | None = None
    actor: Literal["researcher", "skeptic", "judge", "agent", "system"]
    action: str
    agent_id: str | None = None
    agent: dict[str, Any] | None = None
    enemy: str | None = None
    ability: str | None = None
    test: str | None = None
    cost: int | None = None
    result: dict[str, Any] | None = None
    passed: bool | None = None
    hp: int | None = None
    hp_delta: int | None = None
    credits: int | None = None
    status: str | None = None
    verdict: str | None = None
    encounter: dict[str, Any] | None = None  # the structured record of one fight (spec section 12)
    line: str | None = None      # what happened, with the numbers
    explain: str | None = None   # the same, in plain English


class Hero(BaseModel):
    """One hypothesis agent walking the gauntlet."""

    id: str
    name: str
    cls: str
    gladiator: Gladiator
    hp: int = rules.STARTING_HP
    credits: int = rules.STARTING_CREDITS
    status: Literal["questing", "fallen", "untestable", "unproven"] = "questing"
    verdict: str | None = None
    levels_cleared: int = 0
    spent: int = 0
    attempted: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    conceded: int = 0
    redundant: int = 0
    revised: bool = False
    prereg_hash: str | None = None
    results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    encounter_ids: dict[str, str] = Field(default_factory=dict)  # test -> encounter id, for citations
    hp_by_level: dict[int, int] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def questing(self) -> bool:
        return self.status == "questing"

    def public(self) -> dict[str, Any]:
        """What the screen may show. Origin stays hidden until the finale reveals decoys."""
        g = self.gladiator
        return {"id": self.id, "name": self.name, "cls": self.cls, "claim": g.claim,
                "features": g.add_features, "baseline": g.baseline_features,
                "direction": g.expected_direction, "hp": self.hp, "credits": self.credits}

    def card(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "hp": self.hp, "credits": self.credits,
                "spent": self.spent, "attempted": self.attempted, "passed": self.passed_checks,
                "failed": self.failed_checks, "conceded": self.conceded, "redundant": self.redundant,
                "status": self.status, "verdict": self.verdict}
