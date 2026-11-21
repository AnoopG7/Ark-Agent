"""Demo: the human-in-the-loop checkpoint pauses the run and resumes on a decision.

uv run python -m scripts.demo_approval            # approve
uv run python -m scripts.demo_approval reject     # reject
uv run python -m scripts.demo_approval revise "Use the Harbour depot"
"""

import sys

from app.api.container import production_container
from app.core.config import get_settings
from scripts._demo import ask, decide, new_thread


def main() -> None:
    decision = sys.argv[1] if len(sys.argv) > 1 else "approve"
    note = sys.argv[2] if len(sys.argv) > 2 else ""
    with production_container(get_settings()) as c:
        c.repo.reset()
        thread = new_thread("demo-approval")
        print(f"Thread {thread}; demo data reset. Tasks before: {len(c.repo.list_tasks())}")

        ask(c, thread, "Ward 7 needs drinking water for 300 people by evening.")
        snapshot = c.graph.get_state({"configurable": {"thread_id": thread}})
        print(
            f"\nGraph is paused at node(s) {snapshot.next}; "
            f"tasks so far: {len(c.repo.list_tasks())}"
        )
        if not snapshot.interrupts:
            print("The agent did not propose a dispatch this time; nothing to approve.")
            return

        decide(c, thread, decision, note)
        print("\nTasks after decision:")
        for t in c.repo.list_tasks():
            print(
                f"  {t.id} {t.status} {t.plan.ward_id} {t.plan.total_allocated} "
                f"{t.plan.resource} team {t.plan.team_id}"
            )
        water = {s.depot_id: (s.reserved, s.available) for s in c.repo.get_stock("drinking_water")}
        print(f"Water reserved/available per depot: {water}")


if __name__ == "__main__":
    main()
