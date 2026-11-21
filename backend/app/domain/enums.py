"""Enumerations shared across the relief-operations domain."""

from enum import StrEnum


class ResourceType(StrEnum):
    DRINKING_WATER = "drinking_water"
    FOOD_RATION = "food_ration"
    MEDICINE_KIT = "medicine_kit"
    BOAT = "boat"
    SHELTER_KIT = "shelter_kit"
    BLANKET = "blanket"


class Unit(StrEnum):
    LITRE = "litre"
    PACKET = "packet"
    KIT = "kit"
    UNIT = "unit"
    PIECE = "piece"


RESOURCE_UNITS: dict[ResourceType, Unit] = {
    ResourceType.DRINKING_WATER: Unit.LITRE,
    ResourceType.FOOD_RATION: Unit.PACKET,
    ResourceType.MEDICINE_KIT: Unit.KIT,
    ResourceType.BOAT: Unit.UNIT,
    ResourceType.SHELTER_KIT: Unit.KIT,
    ResourceType.BLANKET: Unit.PIECE,
}
"""The canonical unit each resource is counted in."""


class RouteStatus(StrEnum):
    OPEN = "open"
    SLOW = "slow"
    BLOCKED = "blocked"


class VehicleType(StrEnum):
    TRUCK = "truck"
    BOAT = "boat"
    FOOT = "foot"


class TeamSkill(StrEnum):
    LOGISTICS = "logistics"
    MEDICAL = "medical"
    BOAT_RESCUE = "boat_rescue"
    SHELTER = "shelter"


class TeamStatus(StrEnum):
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    RESTING = "resting"


class TaskStatus(StrEnum):
    DISPATCHED = "dispatched"
    REJECTED = "rejected"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FactKind(StrEnum):
    DECISION = "decision"
    RESERVATION = "reservation"
    ROAD_REPORT = "road_report"
    REJECTION = "rejection"
    NOTE = "note"
