"""Load and cross-validate the Driftwood Bay seed dataset shipped with the backend."""

import json
from functools import cache
from pathlib import Path
from typing import Self

from pydantic import model_validator

from app.domain import Depot, Route, Team, Ward
from app.domain.base import DomainModel

SEED_DIR = Path(__file__).resolve().parent


class SeedData(DomainModel):
    """The full initial state of the operation, validated for referential integrity."""

    wards: list[Ward]
    depots: list[Depot]
    routes: list[Route]
    teams: list[Team]

    @model_validator(mode="after")
    def _integrity(self) -> Self:
        for name, items in (
            ("ward", self.wards),
            ("depot", self.depots),
            ("route", self.routes),
            ("team", self.teams),
        ):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {name} id")
        ward_ids = {w.id for w in self.wards}
        depot_ids = {d.id for d in self.depots}
        for r in self.routes:
            if r.ward_id not in ward_ids:
                raise ValueError(f"route {r.id} references unknown ward {r.ward_id}")
            if r.depot_id not in depot_ids:
                raise ValueError(f"route {r.id} references unknown depot {r.depot_id}")
        for t in self.teams:
            if t.base_depot not in depot_ids:
                raise ValueError(f"team {t.id} references unknown depot {t.base_depot}")
        return self


def _read(name: str, directory: Path) -> list[dict]:
    return json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))


def load_seed(directory: Path = SEED_DIR) -> SeedData:
    """Read the four seed files from ``directory`` and validate them as one dataset."""
    return SeedData(
        wards=_read("wards", directory),
        depots=_read("depots", directory),
        routes=_read("routes", directory),
        teams=_read("teams", directory),
    )


@cache
def default_seed() -> SeedData:
    """The packaged seed, parsed once per process. Callers must copy before mutating."""
    return load_seed()
