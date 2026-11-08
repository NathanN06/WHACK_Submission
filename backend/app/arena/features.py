"""Feature registry: which columns gladiators may use, and when each is known.

`available` is the truth the Inquisitor (leak audit) uses. Agents only ever see
`public_catalog`, which hides it, so a leak can look innocent until audited.
"""

from dataclasses import dataclass
from typing import Literal

Availability = Literal["before_meal", "after_meal", "outcome"]


@dataclass(frozen=True)
class Feature:
    name: str
    day: int
    available: Availability
    description: str
    participant_level: bool = False


BASE_FEATURES = [
    Feature("carbs", 1, "before_meal", "Carbohydrate in the meal, grams"),
    Feature("fiber", 2, "before_meal", "Fibre in the meal, grams"),
    Feature("protein", 2, "before_meal", "Protein in the meal, grams"),
    Feature("fat", 2, "before_meal", "Fat in the meal, grams"),
    Feature("sugar", 2, "before_meal", "Sugar in the meal, grams"),
    Feature("calories", 2, "before_meal", "Energy in the meal, kcal"),
    Feature("baseline_glucose", 2, "before_meal", "Glucose just before eating, mg/dL"),
    Feature("hour_of_day", 3, "before_meal", "Hour the meal started, 0-23"),
    Feature("hours_since_last_meal", 3, "before_meal", "Hours since the previous meal"),
    Feature("steps_after", 3, "after_meal", "Steps in the 2 hours after eating"),
    Feature("hr_after", 3, "after_meal", "Mean heart rate in the 2 hours after eating"),
    Feature("hba1c", 3, "before_meal", "The person's HbA1c, %", participant_level=True),
]


def default_registry() -> dict[str, Feature]:
    return {f.name: f for f in BASE_FEATURES}


def register(registry: dict[str, Feature], feature: Feature) -> dict[str, Feature]:
    """Return a new registry with one more feature (registries are per run)."""
    out = dict(registry)
    out[feature.name] = feature
    return out


def public_catalog(registry: dict[str, Feature], day: int, columns: set[str]) -> list[dict]:
    """What the agents see: features unlocked by `day` that exist in the data. No availability."""
    return [
        {"name": f.name, "day": f.day, "description": f.description}
        for f in registry.values()
        if f.day <= day and f.name in columns
    ]
