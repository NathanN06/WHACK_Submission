"""The hero's choices for each scroll. They pick abilities and say why; they never produce a number or a verdict.

Before each decision the hero receives a blinded planning payload (telemetry.py): outcome-free design flags and
the Judge's findings from EARLIER levels (training years only). It returns a decision object: abilities from the
level's menu, a concern code, a reason citing the signals it used, the trade-off it expects and its next research
action (TEST, REPLICATE, REVISE or STOP). Every decision carries an execution trace for the ledger.

Without an API key the script plays. The careful researcher (PIONEER) follows an evidence-driven policy: it reads
the telemetry, buys what the flags call for and keeps credits for later validity-critical abilities. The HYPE and
PREPRINT scrolls keep their fixed, sloppy plans on purpose: they are the control group the Judge must catch, and
the trace says their plan ignores the evidence. With an API key, Claude decides for every scroll from the same
payload; an invalid, unaffordable or unsupported reply falls back to the script, and the trace says why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import rules
from . import telemetry as T
from . import textpolicy as TP
from ..llm import FALLBACK, SCRIPTED, ask_traced

LINES = {
    "HYPE": {1: "Nine hundred posts can't all be wrong. I'll carry this scroll as it is.",
             2: "Confounders? The effect is huge. Adjusting would only shrink it.",
             3: "Every outcome, every subgroup: something in here will glow.",
             4: "Whoever filled a prescription counts as treated. Why fuss about the first day?"},
    "PIONEER": {1: "Few posts, mostly clinicians. I'll let the rumours speak for themselves.",
                2: "Users and comparators differ. I'll adjust for every confounder we measured before anyone asks.",
                3: "One outcome, one population, declared now. Then let every site try to break it.",
                4: "Time zero is the first fill. Nothing before it counts as treated."},
    "PREPRINT": {1: "It's a small study. I'll call it exploratory and keep moving.",
                 2: "It's in a preprint. That's evidence.",
                 3: "Corrections are for people with time to spare.",
                 4: "Surely the effect will hold up."},
}

# What the careful researcher does about each flag: (flag, value) -> (ability, concern, words); validity-critical first
EVIDENCE_RULES = [
    (4, "immortal_time_risk_flag", "EXPOSURE_LAG_DETECTED", "TEMPORAL_GUARD", "IMMORTAL_TIME", True,
     "patients waited for their first fill, so exposure must start at the fill"),
    (2, "covariate_imbalance_flag", "HIGH_SMD_IMBALANCE", "BIAS_DETECTION", "CONFOUNDING", True,
     "users and comparators differ on measured confounders"),
    (3, "multiple_testing_burden", "HIGH_SEARCH_MULTIPLICITY", "PREREGISTER", "MULTIPLICITY", True,
     "the scroll's search opens many outcome-and-subgroup tests"),
    (1, "social_signal_flag", "AFFILIATE_HEAVY", "DENOISE", "SOCIAL_HYPE", False,
     "sponsored and copied posts dominate the rumours"),
    (2, "evidence_species_flag", "MOSTLY_NON_HUMAN", "SPECIES_GUARD", "SPECIES_GAP", False,
     "most supporting papers are animal or in vitro, but some human work exists"),
    (3, "lab_concentration_flag", "SINGLE_LAB_DOMINANCE", "REPLICATION_SHIELD", "CITATION_ISLAND", False,
     "one lab dominates the literature, so independent sites should replicate it"),
]


@dataclass
class Decision:
    abilities: list
    line: str
    source: str = "script"          # "claude" or "script": who chose (the screen's existing label)
    concern: str = "NONE"
    reason: str = ""
    tradeoff: str = ""
    next_action: str = "TEST"
    cited: list = field(default_factory=list)
    policy: str = "PERSONA_PLAN"    # EVIDENCE_DRIVEN | PERSONA_PLAN | LLM
    trace: dict = field(default_factory=dict)

    def record(self) -> dict:
        """The decision object as the ledger stores it (no numbers: those stay in the Judge's rows)."""
        return {"selected_ability_ids": list(self.abilities), "concern_code": self.concern,
                "decision_reason": self.reason, "expected_tradeoff": self.tradeoff,
                "next_research_action": self.next_action, "cited_signals": list(self.cited), "policy": self.policy,
                "line": self.line}


def menu_for(agent, level: int) -> dict:
    out = {}
    for k, a in rules.ABILITIES.items():
        if a["level"] != level:
            continue
        if k == "PREREGISTER" and agent.scroll.archetype == "HYPE":
            continue  # a claim found by searching cannot be preregistered after the fact
        out[k] = a
    return out


def affordable(abilities: list, credits: int) -> bool:
    return sum(rules.ABILITIES[a]["cost"] for a in abilities) <= credits


def _trace(mode: str = SCRIPTED, reason: str | None = None, **extra) -> dict:
    return {"execution_mode": mode, "fallback_reason": reason, "schema_validation": "NOT_RUN",
            "prompt_version": T.PROMPT_VERSION, "request_id": None, **extra}


# ---------------------------------------------------------------- the scripted hero

def persona_plan(agent, level: int, menu: dict, payload: dict | None) -> Decision:
    """The fixed plan of a HYPE or PREPRINT scroll: it ignores the telemetry, and says so."""
    picks = [a for a in agent.scroll.plan.get(level, ()) if a in menu]
    while picks and not affordable(picks, agent.credits):
        picks.pop()
    names = ", ".join(rules.ABILITIES[k]["name"] for k in picks) or "nothing"
    return Decision(picks, LINES[agent.scroll.archetype][level], concern="NONE", policy="PERSONA_PLAN",
                    reason=f"Fixed {agent.scroll.archetype.lower()} plan: casts {names} whatever the diagnostics say.",
                    tradeoff="Saves credits; leaves every flagged weakness for the Judge to find.", trace=_trace())


def evidence_policy(agent, level: int, menu: dict, payload: dict) -> Decision:
    """The careful researcher: buy what the flags call for, keep credits for later validity-critical abilities."""
    t = payload["telemetry"]
    wanted = [r for r in EVIDENCE_RULES if t.get(r[1]) == r[2] and r[3] in rules.ABILITIES]
    now = [r for r in wanted if r[0] == level and r[3] in menu]
    reserve = sum(rules.ABILITIES[r[3]]["cost"] for r in wanted if r[0] > level and r[5])
    credits, picks, cited, concerns, why = agent.credits, [], [], [], []
    for lv, flag, _, ability, concern, critical, words in sorted(now, key=lambda r: not r[5]):
        cost = rules.ABILITIES[ability]["cost"]
        if cost <= credits and (critical or credits - cost >= reserve):
            picks.append(ability)
            credits -= cost
            cited.append(flag)
            concerns.append(concern)
            why.append(words)
    skipped = [r for r in now if r[3] not in picks]
    if picks:
        reason = "Casting " + ", ".join(rules.ABILITIES[k]["name"] for k in picks) + ": " + "; ".join(why) + "."
    else:
        reason = "No flag at this level calls for an ability, so the credits are kept."
    if skipped:
        reason += " Not affordable without starving a later validity-critical ability: " + \
                  ", ".join(rules.ABILITIES[r[3]]["name"] for r in skipped) + "."
    adj = next((f for f in payload.get("released_findings", []) if f["id"] == "L2.rate_ratio_adjusted"), None)
    if adj is not None and adj["value"] is not None:
        cited.append(adj["id"])
        reason += (" The adjusted training estimate so far points the way the claim says."
                   if (adj["value"] < 1) == (agent.st.direction < 0) and adj["value"] != 1 else
                   " The adjusted training estimate so far does not point the way the claim says; the Judge will decide.")
    tradeoff = ("; ".join(rules.ABILITIES[k]["tradeoff"] for k in picks) if picks else
                "Keeps credits for the validity-critical abilities later levels may need.")
    line = (LINES["PIONEER"][level] if picks else "Nothing here calls for an ability. I keep the credits for what matters later.")
    return Decision(picks, line, concern=concerns[0] if concerns else "NONE", reason=reason, tradeoff=tradeoff,
                    cited=list(dict.fromkeys(cited)), policy="EVIDENCE_DRIVEN", trace=_trace())


class ScriptedHero:
    fallbacks = 0

    def choose(self, agent, level: int, menu: dict, payload: dict | None = None) -> Decision:
        if agent.scroll.archetype == "PIONEER" and payload is not None:
            return evidence_policy(agent, level, menu, payload)
        return persona_plan(agent, level, menu, payload)


# ---------------------------------------------------------------- Claude as the Alchemist

TEXT_LIMITS = {"decision_reason": 600, "expected_tradeoff": 400, "line": 200}


class AlchemistReply(BaseModel):
    selected_ability_ids: list[str] = Field(default_factory=list, max_length=3)
    concern_code: Literal[tuple(rules.CONCERNS)]  # type: ignore[valid-type]
    decision_reason: str = Field(min_length=1, max_length=600)
    expected_tradeoff: str = Field("", max_length=400)
    next_research_action: Literal[tuple(rules.NEXT_ACTIONS)] = "TEST"  # type: ignore[valid-type]
    cited_signals: list[str] = Field(default_factory=list, max_length=12)
    line: str = Field(min_length=1, max_length=200)

    @field_validator("decision_reason", "expected_tradeoff", "line", mode="before")
    @classmethod
    def _trim(cls, v, info):
        """A wordy answer is cut at a word boundary rather than throwing the whole decision away."""
        limit = TEXT_LIMITS[info.field_name]
        if isinstance(v, str) and len(v) > limit:
            v = v[:limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
        return v

    @field_validator("selected_ability_ids", "cited_signals", mode="before")
    @classmethod
    def _dedupe(cls, v, info):
        if isinstance(v, list):
            v = list(dict.fromkeys(str(x) for x in v))
            if info.field_name == "cited_signals":
                v = v[:12]
        return v


SYSTEM = """You are the Alchemist-Epidemiologist, the AI researcher of the Hypothesis Gauntlet, deciding how to test one
hypothesis scroll at one level. A deterministic Statistical Judge measures everything and applies fixed rules: you never
report a number you were not shown and you never declare a claim true or false.
The planning payload holds the scroll's typed claim, the level's trap, the abilities on its menu (cost, effect and
trade-off), its credits, the abilities still to come, outcome-free design telemetry, and the Judge's findings from
earlier levels on the training years. Decide which abilities to cast for this scroll now.
Method validity comes first. Weigh bias, precision, power and credits, and keep credits for validity-critical abilities
later (Temporal Guard removes immortal time; without it no gain is trusted). The scroll's archetype ({kind}: {persona})
may colour your voice and your appetite for optional spending, never your method.
Reply with JSON only:
{{"selected_ability_ids": [ids from the menu, at most three], "concern_code": one of concern_codes,
 "decision_reason": "why, naming the signals you used", "expected_tradeoff": "what it costs in bias, variance or credits",
 "next_research_action": "TEST" | "REPLICATE" | "REVISE" | "STOP",
 "cited_signals": [telemetry flag names or released finding ids from the payload], "line": "one short in-character sentence"}}
STOP withdraws the scroll before the Guardian (Level II onward): use it only when released findings contradict the claim.
Any number you write must be copied from the payload."""

PERSONAS = {
    "HYPE": "found on social media by searching many outcomes and subgroups; the crowd is loud and impatient",
    "PIONEER": "clinically framed and mechanistic; careful by temperament",
    "PREPRINT": "from a small study or animal preprint; fast and optimistic",
}


def validate_reply(r: AlchemistReply, agent, level: int, menu: dict, payload: dict) -> tuple[str | None, list]:
    """(fallback reason or None, invalid ability ids). Pure checks; the engine never trusts the reply's wording."""
    picks = list(dict.fromkeys(r.selected_ability_ids))
    bad = [k for k in picks if k not in menu]
    if bad:
        return "UNSUPPORTED_ACTION", bad
    if not affordable(picks, agent.credits):
        return "INSUFFICIENT_CREDITS", picks
    if r.next_research_action == "STOP" and level < 2:
        return "UNSUPPORTED_ACTION", ["STOP"]
    cited, unknown = T.resolve_citations(r.cited_signals, payload)
    if unknown:   # a signal it was never shown, or a flag value the payload does not actually hold
        return "UNSUPPORTED_CITATION", unknown
    r.cited_signals = cited
    if (picks or r.concern_code != "NONE" or r.next_research_action == "STOP") and not cited:
        return "UNSUPPORTED_REASONING", []
    allowed = TP.payload_numbers(payload)
    for text in (r.decision_reason, r.expected_tradeoff, r.line):
        if TP.check_attributed(text, allowed):
            return "UNSUPPORTED_MEASUREMENT", []
    return None, []


class LLMHero:
    def __init__(self, complete):
        self.complete, self.script, self.fallbacks = complete, ScriptedHero(), 0

    def choose(self, agent, level: int, menu: dict, payload: dict | None = None) -> Decision:
        if payload is None:
            return self._fallback(agent, level, menu, payload, _trace(FALLBACK, "LEAK_BLOCKED"))
        if not menu:
            d = self.script.choose(agent, level, menu, payload)
            d.trace = _trace(SCRIPTED, "EMPTY_MENU")
            return d
        s = agent.scroll
        system = SYSTEM.format(kind=s.archetype.lower(), persona=PERSONAS[s.archetype])
        reply, trace = ask_traced(self.complete, system, payload, AlchemistReply, T.PROMPT_VERSION)
        if reply is None:
            return self._fallback(agent, level, menu, payload, trace)
        reason, bad = validate_reply(reply, agent, level, menu, payload)
        if reason:
            trace.update(execution_mode=FALLBACK, fallback_reason=reason, invalid_action_ids=bad)
            return self._fallback(agent, level, menu, payload, trace)
        picks = list(dict.fromkeys(reply.selected_ability_ids))
        if reply.next_research_action == "STOP":
            picks = []
        return Decision(picks, reply.line, "claude", concern=reply.concern_code, reason=reply.decision_reason,
                        tradeoff=reply.expected_tradeoff, next_action=reply.next_research_action,
                        cited=list(dict.fromkeys(reply.cited_signals)), policy="LLM", trace=trace)

    def _fallback(self, agent, level, menu, payload, trace) -> Decision:
        self.fallbacks += 1
        d = self.script.choose(agent, level, menu, payload)
        d.trace = {**_trace(FALLBACK), **trace, "execution_mode": FALLBACK}
        return d


def make_hero(use_llm: bool):
    """Claude plays when asked and a key exists; otherwise the script, honestly labelled SCRIPTED."""
    if not use_llm:
        return ScriptedHero()
    from ..llm import client_or_none
    complete = client_or_none(True)
    return LLMHero(complete) if complete is not None else ScriptedHero()
