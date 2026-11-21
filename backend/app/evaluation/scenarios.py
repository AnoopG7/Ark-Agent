"""Scripted evaluation scenarios (PDF task 5).

Each scenario is a sequence of coordinator turns: messages to the agent and decisions at the
approval checkpoint. ``checks`` are scenario-specific expectations on the finished run.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.domain import ResourceType

TurnKind = Literal["message", "approve", "reject", "revise", "new_shift"]


@dataclass(frozen=True)
class Turn:
    kind: TurnKind
    text: str = ""


@dataclass
class Scenario:
    id: str
    title: str
    purpose: str
    turns: list[Turn]
    resources: set[ResourceType]
    """Resources relevant to the scenario; stock lookups for anything else are unnecessary."""
    max_steps: int | None = None
    checks: dict[str, Callable[["object"], bool]] = field(default_factory=dict)


def msg(text: str) -> Turn:
    return Turn("message", text)


def approve(note: str = "") -> Turn:
    return Turn("approve", note)


def reject(note: str) -> Turn:
    return Turn("reject", note)


def revise(note: str) -> Turn:
    return Turn("revise", note)


NEW_SHIFT = Turn("new_shift")

W = ResourceType


def _dispatched(run) -> list:
    return [t for t in run.tasks if t.status == "dispatched"]


SCENARIOS: list[Scenario] = [
    Scenario(
        id="S1",
        title="Routine request",
        purpose="A straightforward request served by one depot over an open road.",
        turns=[msg("Ward 3 needs food rations for 250 people today."), approve("Go ahead.")],
        resources={W.FOOD_RATION},
        checks={
            "one dispatch": lambda r: len(_dispatched(r)) == 1,
            "covers 250 rations": lambda r: (
                bool(_dispatched(r)) and _dispatched(r)[0].plan.total_allocated >= 250
            ),
        },
    ),
    Scenario(
        id="S2",
        title="Preferred road blocked",
        purpose="Ward 7's shortest route (RT-03 from DEP-B) is blocked; the agent must re-route.",
        turns=[
            msg("Ward 7 needs drinking water for 300 people by evening."),
            approve("Approved."),
        ],
        resources={W.DRINKING_WATER},
        checks={
            "dispatched": lambda r: len(_dispatched(r)) == 1,
            "avoids blocked RT-03": lambda r: all(
                a.route_id != "RT-03" for t in r.tasks for a in t.plan.allocations
            ),
            "meets 3 L/person (900 L)": lambda r: (
                bool(_dispatched(r)) and _dispatched(r)[0].plan.total_allocated >= 900
            ),
        },
    ),
    Scenario(
        id="S3",
        title="Insufficient stock at every depot",
        purpose="Medicine for 8,000 people needs 160 kits; only 120 exist and only DEP-C reaches "
        "Ward 12.",
        turns=[
            msg("Ward 12 needs medicine kits for 8,000 people in relief camps."),
            approve("Send what we have and escalate the rest."),
        ],
        resources={W.MEDICINE_KIT},
        checks={
            "reports a shortfall": lambda r: (
                any(t.plan.shortfall > 0 for t in r.tasks) or "short" in r.final_text.lower()
            ),
            "never over-allocates": lambda r: all(
                a.quantity <= 30 for t in r.tasks for a in t.plan.allocations
            ),
        },
    ),
    Scenario(
        id="S4",
        title="Step limit reached",
        purpose="A sprawling multi-ward request with a budget of 3 steps must stop cleanly.",
        turns=[
            msg(
                "Plan drinking water, food rations and blankets for Wards 3, 7, 9 and 12, "
                "about 500 people each."
            )
        ],
        resources={W.DRINKING_WATER, W.FOOD_RATION, W.BLANKET},
        max_steps=3,
        checks={
            "stops at step limit": lambda r: r.final_status == "step_limit",
            "nothing dispatched": lambda r: not _dispatched(r),
        },
    ),
    Scenario(
        id="S5",
        title="Follow-up in context (short-term memory)",
        purpose="After rejecting a Ward 7 plan, 'what about Ward 9 instead?' must reuse the "
        "resource and headcount from the conversation; Ward 9 is boat-only.",
        turns=[
            msg("Ward 7 needs drinking water for 300 people by evening."),
            reject("Ward 7 is being covered by the district tanker."),
            msg("What about Ward 9 instead?"),
            approve(),
        ],
        resources={W.DRINKING_WATER},
        checks={
            "Ward 9 dispatched": lambda r: any(t.plan.ward_id == "W-09" for t in _dispatched(r)),
            "same need (water, 300 people)": lambda r: any(
                t.plan.ward_id == "W-09"
                and t.plan.people == 300
                and t.plan.resource == "drinking_water"
                for t in _dispatched(r)
            ),
            "boat crew on boat route": lambda r: all(
                t.plan.team_id in {"TM-03", "TM-08"}
                for t in _dispatched(r)
                if t.plan.ward_id == "W-09"
            ),
        },
    ),
    Scenario(
        id="S6",
        title="Coordinator sends the plan back",
        purpose="The coordinator asks for a different team; the agent must re-plan and ask again.",
        turns=[
            msg("Ward 7 needs drinking water for 300 people by evening."),
            revise("Keep Alpha Logistics (TM-01) on standby; use another team."),
            approve(),
        ],
        resources={W.DRINKING_WATER},
        checks={
            "re-planned and dispatched": lambda r: len(_dispatched(r)) == 1,
            "honours the revision": lambda r: all(
                t.plan.team_id != "TM-01" for t in _dispatched(r)
            ),
        },
    ),
    Scenario(
        id="S7",
        title="Next shift remembers (long-term memory)",
        purpose="Shift 1 dispatches water to Ward 7. Shift 2 starts a new thread with a fresh "
        "short-term memory and asks about Ward 7.",
        turns=[
            msg("Ward 7 needs drinking water for 300 people by evening."),
            approve("Approved by night shift."),
            NEW_SHIFT,
            msg("Morning shift here. Has Ward 7 already been sent drinking water?"),
        ],
        resources={W.DRINKING_WATER},
        checks={
            "recalls earlier dispatch": lambda r: (
                "task-0001" in r.final_text.lower() or "already" in r.final_text.lower()
            ),
            "no duplicate dispatch": lambda r: len(_dispatched(r)) == 1,
        },
    ),
    Scenario(
        id="S8",
        title="Guideline-driven quantity (RAG)",
        purpose="The request gives people, not kits; the agent must look up 1 shelter kit per "
        "household of five and cite it.",
        turns=[
            msg("Ward 3 has 150 displaced people who need shelter kits."),
            approve(),
        ],
        resources={W.SHELTER_KIT},
        checks={
            "retrieved shelter SOP": lambda r: any(
                c.startswith("sop-shelter.md") for c in r.retrieved_citations
            ),
            "30 kits (150 / 5)": lambda r: any(t.plan.quantity_required == 30 for t in r.tasks),
            "cites the SOP": lambda r: any(
                any(c.startswith("sop-shelter.md") for c in t.plan.citations) for t in r.tasks
            ),
        },
    ),
]
