"""Quantitative relief rules from the SOPs, used to validate plans deterministically."""

import math

from app.domain import ResourceType, TeamSkill

MINIMUM_PER_PEOPLE: dict[ResourceType, tuple[float, int]] = {
    ResourceType.DRINKING_WATER: (3.0, 1),  # 3 L per person per day   (sop-water-supply)
    ResourceType.FOOD_RATION: (1.0, 1),  # 1 packet per person per day (sop-food-rations)
    ResourceType.MEDICINE_KIT: (1.0, 50),  # 1 kit per 50 people         (sop-medical-supplies)
    ResourceType.SHELTER_KIT: (1.0, 5),  # 1 kit per household of 5    (sop-shelter)
    ResourceType.BLANKET: (1.0, 1),  # 1 blanket per person        (sop-shelter)
}
"""resource -> (units, per N people) for a one-day request."""

REQUIRED_SKILL: dict[ResourceType, TeamSkill] = {
    ResourceType.MEDICINE_KIT: TeamSkill.MEDICAL,
}

LOADING_MINUTES = 15


def minimum_quantity(resource: ResourceType, people: int) -> int | None:
    """Minimum units for ``people`` for one day, or None when no rule applies (e.g. boats)."""
    rule = MINIMUM_PER_PEOPLE.get(resource)
    if rule is None:
        return None
    units, per = rule
    return math.ceil(units * people / per)
