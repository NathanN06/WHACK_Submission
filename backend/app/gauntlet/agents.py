"""The gauntlet's AI roles. They choose and talk; they never produce a number or a verdict.

- Researcher: proposes the hypotheses (reusing the arena's Lanista), decides whether a
  hero spends credits to defend a challenge, and may revise a claim the data contradicts.
- Skeptic: picks which optional challenges to send at each hero, per level.
- The Statistical Judge is not an agent: it is campaign.py + checks.py + the arena engine.

Each role has a scripted version (deterministic: tests, demo, no API key) and a Claude
version that validates every reply and falls back to the script when the reply is unusable.
"""

from pydantic import BaseModel

from ..arena.agents import ask, make_agents
from . import rules
from .models import Hero

# ---------- scripted ----------


class ScriptedResearcher:
    def __init__(self, lanista=None):
        self.lanista = lanista or make_agents(False)[0]

    @property
    def fallbacks(self) -> int:
        return getattr(self.lanista, "fallbacks", 0)

    def propose(self, catalog: list[dict], k: int):
        """The Lanista's ideas for every evidence day, interleaved so the party is varied."""
        by_day = [self.lanista.propose(day, [f for f in catalog if f["day"] <= day], [], k)
                  for day in sorted({f["day"] for f in catalog})]
        out = []
        while any(by_day) and len(out) < k:
            for ideas in by_day:
                if ideas and len(out) < k:
                    out.append(ideas.pop(0))
        return out

    def defend(self, hero: Hero, key: str, reserve: int) -> tuple[bool, str]:
        """Spend credits on this challenge only if the mandatory tests ahead stay affordable."""
        enc = rules.ENCOUNTERS[key]
        trial = hero.results.get("added_value")
        if trial is not None and not trial.get("passed") and enc["level"] >= 3:
            return False, "No edge to protect. Not worth the credits."
        if hero.credits - enc["cost"] >= reserve:
            return True, "Worth the credits. I'll check it properly."
        return False, "I must save my credits for the trials ahead."

    def revise(self, hero: Hero, direction: dict, reserve: int) -> tuple[bool, str]:
        if direction.get("contradicted") and hero.credits - rules.REVISE_COST >= reserve:
            return True, "The data points the other way. I revise my hypothesis."
        return False, ""


ORDER = {
    1: ("bat", "wisp"),
    2: ("skeleton", "phantom", "spider"),
    3: ("wraith", "chimera_selection"),
}


class ScriptedSkeptic:
    def challenges(self, hero: Hero, level: int, options: list[str]) -> tuple[list[str], str]:
        trial = hero.results.get("added_value", {})
        order = list(ORDER.get(level, ()))
        if level == 2:
            order = ["spider", "phantom", "skeleton"] if trial.get("too_good") else (
                ["skeleton", "phantom", "spider"] if trial.get("passed") else ["phantom", "skeleton", "spider"])
        if level == 3 and not trial.get("passed"):
            return [], "It never beat the baseline. Nothing to replicate."
        picks = [k for k in order if k in options][: rules.SKEPTIC_CHALLENGES_PER_LEVEL]
        if not picks:
            return [], "I have no further questions."
        return picks, " and ".join(rules.ENCOUNTERS[k].get("head") or rules.ENCOUNTERS[k]["name"]
                                   for k in picks) + ", test this claim."


# ---------- Claude ----------

SKEPTIC_SYSTEM = """You are the Skeptic in the Hypothesis Gauntlet, a sharp senior reviewer.
Each hero defends one hypothesis about what changes a person's blood-glucose rise after a meal.
For one hero and one level, choose up to {n} optional challenges from the options, most useful first.
Prefer challenges that could expose a weakness given the results so far. Do not waste challenges
on a claim already refuted. Never invent numbers. Reply with JSON only:
{{"challenges": [option keys], "line": "one short line in character"}}"""

RESEARCHER_SYSTEM = """You are the Researcher guiding a hero through the Hypothesis Gauntlet.
Credits are scarce. Decide whether to pay to defend an optional challenge (run the test) or
concede it (lose 5 HP, the claim stays unverified). Mandatory tests ahead must stay affordable.
Never invent numbers. Reply with JSON only: {"defend": bool, "line": "one short line"}"""


class _Challenges(BaseModel):
    challenges: list[str]
    line: str


class _Defend(BaseModel):
    defend: bool
    line: str


def _brief(hero: Hero) -> dict:
    return {"claim": hero.gladiator.claim, "features": hero.gladiator.add_features, "hp": hero.hp,
            "credits": hero.credits,
            "results_so_far": {k: {kk: (round(v, 3) if isinstance(v, float) else v)
                                   for kk, v in r.items() if not isinstance(v, (dict, list))}
                               for k, r in hero.results.items()}}


class LLMSkeptic:
    def __init__(self, complete):
        self.complete, self.fallback, self.fallbacks = complete, ScriptedSkeptic(), 0

    def challenges(self, hero, level, options):
        if not options:
            return [], "I have no further questions."
        reply = ask(self.complete, SKEPTIC_SYSTEM.format(n=rules.SKEPTIC_CHALLENGES_PER_LEVEL), {
            "level": rules.LEVELS[level]["name"], "hero": _brief(hero),
            "options": {k: {"enemy": rules.ENCOUNTERS[k].get("head") or rules.ENCOUNTERS[k]["name"],
                            "checks": rules.ENCOUNTERS[k]["test"], "cost_to_hero": rules.ENCOUNTERS[k]["cost"]}
                        for k in options},
        }, _Challenges)
        if reply is None or any(c not in options for c in reply.challenges):
            self.fallbacks += 1
            return self.fallback.challenges(hero, level, options)
        return list(dict.fromkeys(reply.challenges))[: rules.SKEPTIC_CHALLENGES_PER_LEVEL], reply.line


class LLMResearcher(ScriptedResearcher):
    def __init__(self, lanista, complete):
        super().__init__(lanista)
        self.complete, self._fallbacks = complete, 0

    @property
    def fallbacks(self) -> int:
        return self._fallbacks + getattr(self.lanista, "fallbacks", 0)

    def defend(self, hero, key, reserve):
        enc = rules.ENCOUNTERS[key]
        if hero.credits - enc["cost"] < reserve:  # a hard rule, not a choice
            return False, "I must save my credits for the trials ahead."
        reply = ask(self.complete, RESEARCHER_SYSTEM, {
            "hero": _brief(hero), "challenge": enc.get("head") or enc["name"], "attack": enc["attack"],
            "test": enc["test"], "cost": enc["cost"], "credits_needed_for_mandatory_tests_ahead": reserve,
        }, _Defend)
        if reply is None:
            self._fallbacks += 1
            return super().defend(hero, key, reserve)
        return reply.defend, reply.line


def make_roles(use_llm: bool):
    lanista, _ = make_agents(use_llm)
    if not use_llm:
        return ScriptedResearcher(lanista), ScriptedSkeptic()
    from ..arena.agents import anthropic_complete
    return LLMResearcher(lanista, anthropic_complete()), LLMSkeptic(anthropic_complete())
