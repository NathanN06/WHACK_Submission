"""The Skeptic: after the Citadel and before the Bridge's final lock, it proposes one falsification test per surviving
claim, chosen from the Research Challenge Registry (challenges.py) and nothing else.

It sees each claim's typed form, the findings the Judge already released and the design the claim will be locked
with; it never sees the sealed vault. It outputs a structured challenge (challenge type, reason, the registered test,
whether the data can answer it, the leakage risk, a short critique). The registry decides whether the test is lawful
and runs it on the training years only. The Skeptic cannot change a number, an HP or a verdict: its results are
robustness checks that the Bridge's self-assessment and the report disclose.

Offline, a scripted Skeptic picks the test from the released state. With an API key, Claude may choose, in ONE call
for the whole quest; an invalid choice falls back to the script and the trace says why.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import challenges as C
from . import textpolicy as TP
from ..llm import FALLBACK, SCRIPTED, ask_traced

PROMPT_VERSION = "skeptic-1"
TESTS = tuple(C.TESTS)


class Challenge(BaseModel):
    scroll_id: str
    challenge_type: Literal[TESTS]  # type: ignore[valid-type]
    reason: str = Field(min_length=1, max_length=300)
    suggested_allowlisted_test_id: str
    can_test_with_available_data: bool = True
    risk_of_data_leakage: Literal["NONE", "LOW", "HIGH"] = "NONE"
    critique: str = Field("", max_length=300)


class Reply(BaseModel):
    challenges: list[Challenge] = Field(default_factory=list, max_length=6)


SYSTEM = """You are the Skeptic of the Hypothesis Gauntlet. For each surviving claim, propose the ONE registered test most
likely to falsify it, from this registry (id: what it tests): {registry}.
You see each claim's typed form and the Judge's released findings. You never compute or report numbers and never declare
a claim true or false. Prefer a test that probes a weakness the earlier levels did not already settle.
Reply with JSON only: {{"challenges": [{{"scroll_id": ..., "challenge_type": registry id, "reason": "...",
"suggested_allowlisted_test_id": the same registry id, "can_test_with_available_data": true|false,
"risk_of_data_leakage": "NONE"|"LOW"|"HIGH", "critique": "one sentence"}}]}}"""


def scripted_choice(a) -> dict:
    """Deterministic: the weakness the released state leaves most open, among tests the levels did not already run."""
    m3 = a.m.get(3) or {}
    het = (m3.get("heterogeneity") or {}).get("p", 1.0)
    if a.st.K > 1:
        kind, reason = "chance", "the scroll searched many outcome-and-subgroup combinations, so a permutation test checks luck"
    elif het < 0.10:
        kind, reason = "regional", "the EHR sites disagree more than chance suggests"
    elif not a.st.adjusted:
        kind, reason = "confounder", "the claim was never adjusted for the measured confounders"
    elif len(m3.get("replicating", [])) < 3:
        kind, reason = "replication", "few sites replicate it, so the later training years must show it on their own"
    else:
        kind, reason = "seasonal", "nothing obvious is left open, so check the calendar does not explain it"
    return {"scroll_id": a.id, "challenge_type": kind, "reason": f"Scripted Skeptic: {reason}.",
            "suggested_allowlisted_test_id": kind, "can_test_with_available_data": True,
            "risk_of_data_leakage": "NONE", "critique": C.ARCHETYPES[kind]["question"]}


def _brief(a) -> dict:
    m3 = a.m.get(3) or {}
    return {"scroll_id": a.id, "claim": a.claim, "outcome": a.st.outcome, "subgroup": a.st.subgroup,
            "direction": "lowers" if a.st.direction < 0 else "raises", "design": a.st.design,
            "adjusted": a.st.adjusted, "search_k": a.st.K,
            "released": {"sites_replicating": len(m3.get("replicating", [])), "sites": len(m3.get("sites", [])),
                         "completed_rcts": m3.get("n_rct")}}


def choose(scrolls: list, complete=None) -> tuple[list[dict], dict]:
    """One challenge per scroll and the execution trace. Claude's choices are validated; the script fills gaps."""
    scripted = {a.id: scripted_choice(a) for a in scrolls}
    if complete is None or not scrolls:
        return list(scripted.values()), {"execution_mode": SCRIPTED, "fallback_reason": "NO_API_KEY" if complete is None
                                         else None, "prompt_version": PROMPT_VERSION}
    registry = "; ".join(f"{k}: {v['question']}" for k, v in C.ARCHETYPES.items())
    reply, trace = ask_traced(complete, SYSTEM.format(registry=registry), {"claims": [_brief(a) for a in scrolls]},
                              Reply, PROMPT_VERSION)
    got = {}
    for ch in (reply.challenges if reply else []):
        ok = (ch.scroll_id in scripted and ch.suggested_allowlisted_test_id == ch.challenge_type
              and not TP.measurement_assertions(ch.reason + " " + ch.critique)
              and not TP.check_attributed(ch.reason + " " + ch.critique, []))
        if ok and ch.scroll_id not in got:
            got[ch.scroll_id] = {**ch.model_dump(), "source": "claude"}
    if reply is not None and len(got) < len(scrolls):
        trace = {**trace, "execution_mode": FALLBACK if not got else trace["execution_mode"],
                 "fallback_reason": "SCHEMA_OR_POLICY_REJECTED" if len(got) < len(scrolls) else None,
                 "filled_by_script": [a.id for a in scrolls if a.id not in got]}
    return [got.get(a.id) or {**scripted[a.id], "source": "script"} for a in scrolls], trace
