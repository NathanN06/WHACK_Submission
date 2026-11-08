"""The ledger row. The game screen, the inspector and the decision brief are views of these."""

from typing import Any, Literal

from pydantic import BaseModel


class QuestEvent(BaseModel):
    """One append-only ledger row."""

    run_id: str
    seq: int
    ts: float
    level: int | None = None
    actor: Literal["agent", "judge", "system"]
    action: str
    agent_id: str | None = None
    agent: dict[str, Any] | None = None
    enemy: str | None = None
    ability: str | None = None
    cost: int | None = None
    result: dict[str, Any] | None = None
    passed: bool | None = None
    hp: int | None = None
    hp_delta: int | None = None
    credits: int | None = None
    status: str | None = None
    verdict: str | None = None
    encounter: dict[str, Any] | None = None   # PepEncounterTelemetry
    line: str | None = None                   # what happened, with the numbers
    explain: str | None = None                # the same, in plain English
