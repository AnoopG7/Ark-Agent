"""Demo: long-term memory survives a process restart (shift handover).

Runs shift 1 and shift 2 as two separate Python processes against Postgres:

    uv run python -m scripts.demo_memory_persistence
"""

import subprocess
import sys

from app.api.container import production_container
from app.core.config import get_settings
from scripts._demo import ask, decide, new_thread


def shift_one() -> None:
    with production_container(get_settings()) as c:
        c.repo.reset()
        print(f"Cleared {c.facts.clear()} remembered facts and reset demo data.")
        thread = new_thread("night-shift")
        ask(c, thread, "Ward 7 needs drinking water for 300 people by evening.")
        if c.graph.get_state({"configurable": {"thread_id": thread}}).interrupts:
            decide(c, thread, "approve", "Approved by night shift")
        print("\nFacts written to Postgres by shift 1:")
        for f in c.facts.list(ward_id="W-07"):
            print(f"  ({f.kind}) {f.content}")


def shift_two() -> None:
    with production_container(get_settings()) as c:
        print("Facts read back from Postgres in a brand-new process:")
        for f in c.facts.list(ward_id="W-07"):
            print(f"  ({f.kind}) {f.content}")
        ask(
            c,
            new_thread("morning-shift"),
            "Morning shift here. Has Ward 7 already been sent drinking water?",
        )


def main() -> None:
    if len(sys.argv) > 1:
        {"1": shift_one, "2": shift_two}[sys.argv[1]]()
        return
    for shift in ("1", "2"):
        print(f"\n===== SHIFT {shift} (process started) =====")
        subprocess.run([sys.executable, "-m", "scripts.demo_memory_persistence", shift], check=True)
        print(f"===== SHIFT {shift} (process exited) =====")


if __name__ == "__main__":
    main()
