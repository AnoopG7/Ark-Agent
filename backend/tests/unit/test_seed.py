import pytest
from pydantic import ValidationError

from app.db.seed.loader import SeedData, load_seed
from app.domain import ResourceType, RouteStatus, VehicleType


@pytest.fixture(scope="module")
def seed() -> SeedData:
    return load_seed()


def test_counts_match_case_study(seed: SeedData) -> None:
    assert len(seed.depots) == 3
    assert len(seed.routes) == 6
    assert len(seed.wards) == 12
    assert len(seed.teams) >= 6


def test_preferred_ward7_route_is_blocked(seed: SeedData) -> None:
    ward7 = [r for r in seed.routes if r.ward_id == "W-07"]
    shortest = min(ward7, key=lambda r: r.travel_minutes)
    assert shortest.status is RouteStatus.BLOCKED
    assert any(r.status is not RouteStatus.BLOCKED for r in ward7)


def test_ward9_is_boat_only(seed: SeedData) -> None:
    ward9 = [r for r in seed.routes if r.ward_id == "W-09"]
    assert ward9
    assert all(r.vehicle is VehicleType.BOAT for r in ward9)


def test_medicine_is_scarce_everywhere(seed: SeedData) -> None:
    total = sum(d.item(ResourceType.MEDICINE_KIT).quantity for d in seed.depots)
    assert total < 150


def test_referential_integrity_enforced(seed: SeedData) -> None:
    data = seed.model_dump()
    data["routes"][0]["ward_id"] = "W-99"
    with pytest.raises(ValidationError, match="unknown ward"):
        SeedData.model_validate(data)


def test_duplicate_ids_rejected(seed: SeedData) -> None:
    data = seed.model_dump()
    data["teams"].append(data["teams"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        SeedData.model_validate(data)
