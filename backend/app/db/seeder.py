"""Idempotent loading of the seed dataset into Postgres."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import DepotRow, RouteRow, StockItemRow, TeamRow, TeamSkillRow, WardRow
from app.db.seed.loader import SeedData

OPS_TABLES = (
    "stock_reservations",
    "dispatch_tasks",
    "team_skills",
    "teams",
    "routes",
    "stock_items",
    "depots",
    "wards",
)


def seed_database(session: Session, seed: SeedData, *, force: bool = False) -> bool:
    """Load ``seed`` into the operational tables.

    Without ``force`` this is a no-op when data already exists, so it is safe on every startup.
    With ``force`` all operational tables (and task numbering) are reset first. The RAG index is
    never touched. Returns True if data was written.
    """
    if not force and session.scalar(select(DepotRow.id).limit(1)) is not None:
        return False
    session.execute(text(f"TRUNCATE {', '.join(OPS_TABLES)} RESTART IDENTITY CASCADE"))
    session.add_all(WardRow(**w.model_dump()) for w in seed.wards)
    for depot in seed.depots:
        session.add(
            DepotRow(
                id=depot.id,
                name=depot.name,
                zone=depot.zone,
                stock=[
                    StockItemRow(
                        resource=i.resource, unit=i.unit, quantity=i.quantity, reserved=i.reserved
                    )
                    for i in depot.stock
                ],
            )
        )
    session.flush()
    session.add_all(RouteRow(**r.model_dump()) for r in seed.routes)
    for team in seed.teams:
        data = team.model_dump(exclude={"skills"})
        session.add(TeamRow(**data, skills=[TeamSkillRow(skill=s) for s in team.skills]))
    session.flush()
    return True
