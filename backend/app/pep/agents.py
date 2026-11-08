"""The hero's choices for each scroll. They pick abilities; they never produce a number.

Scripted plans by default. With an API key, Claude plays the Alchemist thinking aloud about one scroll
at a time, choosing abilities from the level's menu as structured JSON; an invalid or unaffordable
choice falls back to the script.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from . import rules

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


@dataclass
class Decision:
    abilities: list
    line: str
    source: str = "script"


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


class ScriptedHero:
    fallbacks = 0

    def choose(self, agent, level: int, menu: dict, brief: dict) -> Decision:
        picks = [a for a in agent.scroll.plan.get(level, ()) if a in menu]
        while picks and not affordable(picks, agent.credits):
            picks.pop()
        return Decision(picks, LINES[agent.scroll.archetype][level])


class _Choice(BaseModel):
    abilities: list[str] = Field(default_factory=list, max_length=3)
    line: str = Field(min_length=1, max_length=200)


SYSTEM = """You are the Alchemist-Epidemiologist, an autonomous AI researcher in the Hypothesis Gauntlet.
You are deciding how to defend one hypothesis scroll: "{title}": {claim}
This scroll is a {kind}; think aloud in that spirit: {persona}
Each level you may cast abilities from the menu for this scroll, paying from its own research credits.
You never report numbers: a deterministic Statistical Judge measures everything and applies fixed damage rules.
Reply with JSON only: {{"abilities": [ability ids from the menu], "line": "one short sentence, thinking aloud, no numbers"}}.
Total cost must not exceed the scroll's credits. An empty list is allowed."""

PERSONAS = {
    "HYPE": "found on social media; you are tempted to trust the crowd and dislike spending on caution.",
    "PIONEER": "clinically framed; you are careful and buy rigour where the evidence is vulnerable.",
    "PREPRINT": "from a small study or animal preprint; you are fast, optimistic and spend little.",
}


class LLMHero:
    def __init__(self, complete):
        self.complete, self.script, self.fallbacks = complete, ScriptedHero(), 0

    def choose(self, agent, level: int, menu: dict, brief: dict) -> Decision:
        if not menu:
            return self.script.choose(agent, level, menu, brief)
        from ..arena.agents import ask
        s = agent.scroll
        system = SYSTEM.format(title=s.title, claim=s.claim, kind=s.archetype.lower(), persona=PERSONAS[s.archetype])
        reply = ask(self.complete, system, {
            **brief, "credits": agent.credits, "hp": agent.hp,
            "menu": {k: {"name": a["name"], "cost": a["cost"], "effect": a["effect"]} for k, a in menu.items()},
        }, _Choice)
        if reply is None or any(a not in menu for a in reply.abilities) \
                or not affordable(list(dict.fromkeys(reply.abilities)), agent.credits) \
                or any(ch.isdigit() for ch in reply.line):
            self.fallbacks += 1
            return self.script.choose(agent, level, menu, brief)
        return Decision(list(dict.fromkeys(reply.abilities)), reply.line, "claude")


def make_hero(use_llm: bool):
    if not use_llm:
        return ScriptedHero()
    from ..arena.agents import ENV_FILE, anthropic_complete, load_env_key
    load_env_key(ENV_FILE)
    return LLMHero(anthropic_complete())
