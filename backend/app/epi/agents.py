"""The four AI epidemiologists. They choose which abilities to cast; they never produce a number.

Scripted agents follow each archetype's plan (campaigns.py). With an API key, Claude plays each
archetype in character, choosing abilities from the level's menu as structured JSON; an invalid
or unaffordable choice falls back to the script.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from . import rules

LINES = {
    "HYPE": {1: "More data beats theory. Every term, every lag: the fit speaks for itself.",
             2: "Seasonality? My R-squared says otherwise.",
             3: "One hundred and forty-seven lags tried, and look how well the best ones fit!",
             4: "The finalized numbers are the real numbers. Why wait for vintages?"},
    "PIONEER": {1: "Shedding precedes symptoms. I'll keep the signal clean before anything else.",
                2: "I'll put the confounder in the model before anyone has to ask.",
                3: "I declared my lag window before looking. Lock it, and shrink the weights.",
                4: "I'll forecast with the data as it stood on the day, delays and all."},
    "PREPRINT": {1: "Twenty-eight patients, a striking curve. Let's call it exploratory and move fast.",
                 2: "It's in a preprint. That's evidence.",
                 3: "Three weeks of lead time is too good to waste on corrections.",
                 4: "Surely the effect will hold up."},
    "SKEPTIC": {1: "I use no outside signal. Rumours can't hurt a model that ignores them.",
                2: "Admissions alone. Nothing to confound.",
                3: "AR(4) plus a seasonal harmonic, written down before any data. Preregistered.",
                4: "I am the bar. Beat me on the data you would have had."},
}


@dataclass
class Decision:
    abilities: list
    line: str
    source: str = "script"


def menu_for(agent, level: int) -> dict:
    """The abilities this agent may cast this level (affordability is checked separately)."""
    out = {}
    for k, a in rules.ABILITIES.items():
        if a["level"] != level:
            continue
        has_streams = bool(agent.spec.feats)
        if k in ("MEDIA_DENOISE", "BIAS_DETECTION", "REPLICATION_SHIELD", "TEMPORAL_GUARD", "ABLATION_STRIKE",
                 "FACT_CHECK", "EXPLORATORY_CLAIM") and not has_streams:
            continue
        if k == "PREREGISTER" and agent.binding.claimed_lag is None and agent.archetype != "SKEPTIC":
            continue  # a lag picked by searching cannot be preregistered after the fact
        out[k] = a
    return out


def affordable(abilities: list, credits: int) -> bool:
    return sum(rules.ABILITIES[a]["cost"] for a in abilities) <= credits


class ScriptedEpidemiologist:
    fallbacks = 0

    def choose(self, agent, level: int, menu: dict, brief: dict) -> Decision:
        picks = [a for a in agent.binding.plan.get(level, ()) if a in menu]
        while picks and not affordable(picks, agent.credits):
            picks.pop()
        return Decision(picks, LINES[agent.archetype][level])


class _Choice(BaseModel):
    abilities: list[str] = Field(default_factory=list, max_length=3)
    line: str = Field(min_length=1, max_length=200)


SYSTEM = """You are {name}, {title} ("{nickname}"), an AI epidemiologist in the Hypothesis Gauntlet.
Your hypothesis: {claim}
Stay in character: {persona}
Each level you may cast abilities from the menu, paying research credits. You never report numbers:
a deterministic Statistical Judge measures everything and applies fixed damage rules.
Reply with JSON only: {{"abilities": [ability ids from the menu], "line": "one short in-character sentence"}}.
Total cost must not exceed your credits. An empty list is allowed."""

PERSONAS = {
    "HYPE": "you trust big data and in-sample fit, and dislike spending credits on caution.",
    "PIONEER": "you are mechanistic and careful; you buy rigour where the evidence is vulnerable.",
    "PREPRINT": "you are fast and optimistic, and spend little.",
    "SKEPTIC": "you defend the autoregressive baseline and doubt every outside signal.",
}


class LLMEpidemiologist:
    def __init__(self, complete):
        self.complete, self.script, self.fallbacks = complete, ScriptedEpidemiologist(), 0

    def choose(self, agent, level: int, menu: dict, brief: dict) -> Decision:
        if not menu:
            return self.script.choose(agent, level, menu, brief)
        from ..arena.agents import ask
        from .campaigns import ARCHETYPES
        arch = ARCHETYPES[agent.archetype]
        system = SYSTEM.format(name=agent.name, title=arch["title"], nickname=arch["nickname"],
                               claim=agent.binding.claim, persona=PERSONAS[agent.archetype])
        reply = ask(self.complete, system, {
            **brief, "credits": agent.credits, "hp": agent.hp,
            "menu": {k: {"name": a["name"], "cost": a["cost"], "effect": a["effect"]} for k, a in menu.items()},
        }, _Choice)
        if reply is None or any(a not in menu for a in reply.abilities) \
                or not affordable(list(dict.fromkeys(reply.abilities)), agent.credits):
            self.fallbacks += 1
            return self.script.choose(agent, level, menu, brief)
        return Decision(list(dict.fromkeys(reply.abilities)), reply.line, "claude")


def make_epidemiologist(use_llm: bool):
    if not use_llm:
        return ScriptedEpidemiologist()
    from ..arena.agents import anthropic_complete, load_env_key, ENV_FILE
    load_env_key(ENV_FILE)
    return LLMEpidemiologist(anthropic_complete())
