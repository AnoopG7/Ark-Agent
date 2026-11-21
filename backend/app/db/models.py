"""SQLAlchemy ORM tables for operational data and the RAG guideline index."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, pg_enum
from app.domain import (
    ResourceType,
    RouteStatus,
    TaskStatus,
    TeamSkill,
    TeamStatus,
    Unit,
    VehicleType,
)

EMBEDDING_DIM = 384

resource_enum = pg_enum(ResourceType, "resource_type")


class WardRow(Base):
    __tablename__ = "wards"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    population: Mapped[int] = mapped_column(Integer)
    zone: Mapped[str] = mapped_column(String(200))

    __table_args__ = (CheckConstraint("population > 0", name="population_positive"),)


class DepotRow(Base):
    __tablename__ = "depots"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    zone: Mapped[str] = mapped_column(String(200))

    stock: Mapped[list["StockItemRow"]] = relationship(
        back_populates="depot", order_by="StockItemRow.id", cascade="all, delete-orphan"
    )


class StockItemRow(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    depot_id: Mapped[str] = mapped_column(ForeignKey("depots.id", ondelete="CASCADE"))
    resource: Mapped[ResourceType] = mapped_column(resource_enum)
    unit: Mapped[Unit] = mapped_column(pg_enum(Unit, "unit"))
    quantity: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)

    depot: Mapped[DepotRow] = relationship(back_populates="stock")

    __table_args__ = (
        UniqueConstraint("depot_id", "resource", name="uq_stock_items_depot_resource"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("reserved <= quantity", name="reserved_within_quantity"),
    )


class RouteRow(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    depot_id: Mapped[str] = mapped_column(ForeignKey("depots.id"))
    ward_id: Mapped[str] = mapped_column(ForeignKey("wards.id"))
    status: Mapped[RouteStatus] = mapped_column(pg_enum(RouteStatus, "route_status"))
    travel_minutes: Mapped[int] = mapped_column(Integer)
    vehicle: Mapped[VehicleType] = mapped_column(pg_enum(VehicleType, "vehicle_type"))
    note: Mapped[str] = mapped_column(String(300), default="")

    __table_args__ = (
        CheckConstraint("travel_minutes > 0", name="travel_minutes_positive"),
        Index("ix_routes_ward_id", "ward_id"),
    )


class TeamRow(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[TeamStatus] = mapped_column(pg_enum(TeamStatus, "team_status"))
    base_depot: Mapped[str] = mapped_column(ForeignKey("depots.id"))
    vehicle: Mapped[VehicleType] = mapped_column(pg_enum(VehicleType, "vehicle_type"))

    skills: Mapped[list["TeamSkillRow"]] = relationship(
        cascade="all, delete-orphan", order_by="TeamSkillRow.skill", lazy="selectin"
    )

    __table_args__ = (CheckConstraint("size BETWEEN 1 AND 50", name="size_range"),)


class TeamSkillRow(Base):
    __tablename__ = "team_skills"

    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    skill: Mapped[TeamSkill] = mapped_column(pg_enum(TeamSkill, "team_skill"), primary_key=True)


class DispatchTaskRow(Base):
    __tablename__ = "dispatch_tasks"

    seq: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str | None] = mapped_column(String(16), unique=True)
    status: Mapped[TaskStatus] = mapped_column(pg_enum(TaskStatus, "task_status"))
    ward_id: Mapped[str] = mapped_column(ForeignKey("wards.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    resource: Mapped[ResourceType] = mapped_column(resource_enum)
    plan: Mapped[dict] = mapped_column(JSONB)
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    thread_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reservations: Mapped[list["StockReservationRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class StockReservationRow(Base):
    """Audit of stock reserved by a dispatched task (one row per allocation)."""

    __tablename__ = "stock_reservations"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    task_seq: Mapped[int] = mapped_column(ForeignKey("dispatch_tasks.seq", ondelete="CASCADE"))
    depot_id: Mapped[str] = mapped_column(ForeignKey("depots.id"))
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"))
    resource: Mapped[ResourceType] = mapped_column(resource_enum)
    quantity: Mapped[int] = mapped_column(Integer)

    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)


class GuidelineChunkRow(Base):
    """A chunk of the relief SOP knowledge base with its embedding (RAG)."""

    __tablename__ = "guideline_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(200))
    section: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_guideline_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_guideline_chunks_source", "source"),
    )
