"""The two AI agents. They choose and talk. They never produce a number or a verdict.

- Lanista (the Researcher): trains gladiators (hypotheses), backs or drops them.
- Sceptic (the arena master): picks which opponent to send at each gladiator.

Each has a scripted version (no API, deterministic: tests, demo fallback) and an
LLM version that validates every reply and falls back to the script if the
model returns something unusable.
"""

import json
import os
from typing import Callable, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from . import config
from .models import Gladiator, GladiatorState

Complete = Callable[[str, str], str]  # (system, user) -> text


class Lanista(Protocol):
    def propose(self, day: int, catalog: list[dict], graveyard: list[dict], k: int) -> list[Gladiator]: ...
    def decide(self, state: GladiatorState) -> tuple[bool, str]: ...
    def theory(self, text: str, catalog: list[dict]) -> Gladiator | None: ...


class Sceptic(Protocol):
    def next_attack(self, state: GladiatorState, options: list[str], denarii: int) -> tuple[str | None, str]: ...


# ---------- scripted versions ----------

SYNONYMS = {"fibre": "fiber", "sugars": "sugar", "kcal": "calories", "energy": "calories",
            "time of day": "hour_of_day", "steps": "steps_after", "walk": "steps_after",
            "heart rate": "hr_after", "hba1c": "hba1c"}


# What a keen young researcher would claim about each feature: a direction and a reason.
SCRIPTED_CLAIMS = {
    "carbs": ("positive", "More carbohydrate means more sugar in the blood, so a bigger spike"),
    "fiber": ("negative", "Fibre slows digestion, so fibre-rich meals spike less than their carbs suggest"),
    "protein": ("negative", "Protein triggers insulin and slows the stomach, blunting the spike"),
    "fat": ("negative", "Fat delays stomach emptying, so fatty meals spike later and lower"),
    "sugar": ("positive", "Sugar hits the blood faster than starch, so sugary meals spike harder"),
    "calories": ("positive", "Bigger meals spike more, whatever they are made of"),
    "baseline_glucose": ("negative", "Starting high leaves less room to rise"),
    "hour_of_day": ("either", "The body handles sugar differently at breakfast and dinner"),
    "hours_since_last_meal": ("positive", "A long fast primes a bigger spike at the next meal"),
    "steps_after": ("negative", "A walk after eating burns the sugar off before it peaks"),
    "hr_after": ("negative", "A raised heart rate after eating means activity, which flattens the spike"),
    "hba1c": ("positive", "People with poorer long-term control spike harder at every meal"),
}


class ScriptedLanista:
    def propose(self, day, catalog, graveyard, k):
        today = [f for f in catalog if f["day"] == day][:k]
        out = []
        for f in today:
            direction, claim = SCRIPTED_CLAIMS.get(
                f["name"], ("either", f"{f['description']} changes the rise after a meal"))
            out.append(Gladiator(id="new", claim=claim, add_features=[f["name"]], day=day,
                                 expected_direction=direction, origin="fallback"))
        return out

    def decide(self, state):
        trial = state.results.get("added_value", {})
        if trial.get("passed"):
            return True, f"I back {state.gladiator.add_features[0]}! Fame awaits!"
        return False, "Not worth the denarii."

    def theory(self, text, catalog):
        lowered = text.lower()
        names = {f["name"] for f in catalog}
        hits = [f["name"] for f in catalog if f["name"].replace("_", " ") in lowered]
        hits += [v for k, v in SYNONYMS.items() if k in lowered and v in names]
        hits = [h for h in dict.fromkeys(hits) if h != "carbs"]
        if not hits:
            return None
        return Gladiator(id="new", claim=text.strip()[:140], add_features=hits[:2], origin="crowd")


class ScriptedSceptic:
    ORDER = ("shuffle_test", "sensor_check", "leak_audit")

    def next_attack(self, state, options, denarii):
        trial = state.results.get("added_value", {})
        if trial.get("too_good") and "leak_audit" in options:
            return "leak_audit", "That's too good to be true. Inquisitor, check where it came from."
        for test in self.ORDER:
            if test in options:
                return test, LINES[test]
        return None, "Enough. Let the referee decide."


LINES = {
    "shuffle_test": "Shuffle it. If scrambled data does as well, it's luck.",
    "sensor_check": "Ask the Twins. A real effect shows on both sensors.",
    "leak_audit": "Inquisitor, make sure nothing here peeks at the result.",
}


# ---------- LLM versions ----------

LANISTA_SYSTEM = """You are the Lanista, an over-eager young scientist who trains gladiators.
Each gladiator is a hypothesis about what changes a person's blood-glucose rise after a meal.
You crave glory, but every gladiator you back that dies costs you 20 reputation.
Rules:
- Use only feature names from the catalog you are given. Never invent columns.
- Each gladiator adds one or two features.
- You never compute numbers. If you mention one, it must come from results you were shown.
- Reply with JSON only, no prose around it."""

SCEPTIC_SYSTEM = """You are the Sceptic, a grumpy senior reviewer who runs the arena.
For one gladiator you choose the next opponent, or null to stop:
- leak_audit (The Inquisitor, free): checks no feature is built from the outcome.
  Send it first when a result looks too good to be true.
- shuffle_test (The Shuffler): checks the effect beats shuffled copies of the feature.
- sensor_check (The Twins): checks both glucose sensors agree.
Choose only from the options given. Say one short line in character.
Never invent numbers. Reply with JSON only."""


class _Proposal(BaseModel):
    claim: str
    add_features: list[str] = Field(min_length=1)
    expected_direction: Literal["positive", "negative", "either"] = "either"


class _Proposals(BaseModel):
    gladiators: list[_Proposal]


class _Decision(BaseModel):
    back: bool
    line: str


class _Attack(BaseModel):
    test: str | None
    line: str


def _extract_json(text: str) -> str:
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in reply")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1]


def ask(complete: Complete, system: str, payload: dict, schema: type[BaseModel]):
    """Call the model, validate against `schema`, retry once with the error. None on failure."""
    user = json.dumps(payload, default=str)
    for _ in range(2):
        try:
            return schema.model_validate_json(_extract_json(complete(system, user)))
        except (ValidationError, ValueError) as e:
            user = json.dumps({**payload, "your_last_reply_was_invalid": str(e)[:300]}, default=str)
        except Exception:  # network or API error: give up and let the script take over
            return None
    return None


def _round(d: dict) -> dict:
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}


class LLMLanista:
    def __init__(self, complete: Complete):
        self.complete = complete
        self.fallback = ScriptedLanista()
        self.fallbacks = 0  # times the script had to answer for Claude

    def propose(self, day, catalog, graveyard, k):
        reply = ask(self.complete, LANISTA_SYSTEM, {
            "day": config.DAY_NAMES.get(day, day),
            "catalog": catalog,
            "unlocked_today": [f["name"] for f in catalog if f["day"] == day],
            "graveyard": graveyard[-15:],
            "task": f"Propose up to {k} gladiators. Each must use at least one feature unlocked today. "
                    'Reply as {"gladiators": [{"claim": str, "add_features": [str], '
                    '"expected_direction": "positive"|"negative"|"either"}]}',
        }, _Proposals)
        if reply is None:
            self.fallbacks += 1
            return self.fallback.propose(day, catalog, graveyard, k)
        return [Gladiator(id="new", claim=p.claim, add_features=p.add_features,
                          expected_direction=p.expected_direction, day=day) for p in reply.gladiators[:k]]

    def decide(self, state):
        reply = ask(self.complete, LANISTA_SYSTEM, {
            "gladiator": state.gladiator.claim,
            "trial_result": _round(state.results.get("added_value", {})),
            "task": 'Back it (stake 20 reputation) or drop it (free)? Reply as {"back": bool, "line": str}',
        }, _Decision)
        if reply is None:
            self.fallbacks += 1
            return self.fallback.decide(state)
        return reply.back, reply.line

    def theory(self, text, catalog):
        reply = ask(self.complete, LANISTA_SYSTEM, {
            "crowd_says": text,
            "catalog": catalog,
            "task": 'Turn this into one gladiator, or {"gladiators": []} if no feature fits. '
                    'Reply as {"gladiators": [{"claim": str, "add_features": [str]}]}',
        }, _Proposals)
        if reply is None:
            self.fallbacks += 1
            return self.fallback.theory(text, catalog)
        if not reply.gladiators:
            return None
        p = reply.gladiators[0]
        return Gladiator(id="new", claim=p.claim, add_features=p.add_features, origin="crowd")


class LLMSceptic:
    def __init__(self, complete: Complete):
        self.complete = complete
        self.fallback = ScriptedSceptic()
        self.fallbacks = 0

    def next_attack(self, state, options, denarii):
        reply = ask(self.complete, SCEPTIC_SYSTEM, {
            "gladiator": state.gladiator.claim,
            "results_so_far": {t: _round(r) for t, r in state.results.items()},
            "options": options,
            "denarii_left": denarii,
            "costs": {t: config.COST[t] for t in options},
            "task": 'Reply as {"test": one of the options or null, "line": str}',
        }, _Attack)
        if reply is None or (reply.test is not None and reply.test not in options):
            self.fallbacks += 1
            return self.fallback.next_attack(state, options, denarii)
        return reply.test, reply.line


def anthropic_complete(model: str | None = None, temperature: float | None = None) -> Complete:
    """A Complete function backed by the Anthropic API. Needs ANTHROPIC_API_KEY."""
    import anthropic

    client = anthropic.Anthropic()
    model = model or os.environ.get("ARENA_MODEL", "claude-sonnet-5-5")

    def complete(system: str, user: str) -> str:
        extra = {} if temperature is None else {"temperature": temperature}
        msg = client.messages.create(model=model, max_tokens=1500, system=system,
                                     messages=[{"role": "user", "content": user}], **extra)
        return "".join(block.text for block in msg.content if block.type == "text")

    return complete


def load_env_key(path: str | os.PathLike = ".env") -> None:
    """Put ANTHROPIC_API_KEY from a .env file into the environment, unless it is already set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return
    for line in lines:
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == "ANTHROPIC_API_KEY":
            os.environ["ANTHROPIC_API_KEY"] = value.strip().strip('"').strip("'")
            return


def make_agents(use_llm: bool) -> tuple[Lanista, Sceptic]:
    load_env_key(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    if not use_llm:
        return ScriptedLanista(), ScriptedSceptic()
    return (LLMLanista(anthropic_complete(temperature=0.7)),
            LLMSceptic(anthropic_complete(temperature=0.2)))
