"""Markdown rendering of scenario traces and the results summary."""

import json
from typing import Any


def _short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def trace_markdown(run: dict[str, Any]) -> str:
    sc, out, m = run["scenario"], run["outcome"], run["metrics"]
    lines = [
        f"# {sc['id']}: {sc['title']}",
        "",
        sc["purpose"],
        "",
        f"**Result:** {'PASS' if out['passed'] else 'FAIL'}, final status "
        f"`{out['final_status']}`, "
        f"{m['steps_total']} reasoning steps, {m['tool_calls']} tool calls, "
        f"{m['latency_s']} s, {m['tokens_in']} in / {m['tokens_out']} out tokens",
        "",
        "| Check | Result |",
        "|-------|--------|",
        *[f"| {k} | {'✅' if v else '❌'} |" for k, v in out["checks"].items()],
        "",
    ]
    if out["deviations"]:
        lines += ["**Deviations from script:**", *[f"- {d}" for d in out["deviations"]], ""]
    if out["error"]:
        lines += [f"**Error:** `{out['error']}`", ""]
    lines += ["## Trace", ""]
    for e in run["trace"]:
        t, d = e["type"], e.get("data", {})
        if t.startswith("coordinator_"):
            kind = t.removeprefix("coordinator_")
            label = {
                "message": "Coordinator",
                "approve": "Coordinator APPROVES",
                "reject": "Coordinator REJECTS",
                "revise": "Coordinator REVISES",
            }[kind]
            lines += ["", f"**{label}:** {d.get('text') or '(no note)'}", ""]
        elif t == "new_shift":
            lines += [
                "",
                "---",
                "",
                "*New shift: fresh thread, short-term memory empty, long-term memory kept.*",
                "",
            ]
        elif t == "thought":
            lines.append(f"- **[{e['step']}] Thought:** {_short(d['text'], 300)}")
        elif t == "tool_call":
            lines.append(f"- **[{e['step']}] Act:** `{d['name']}` {_short(d['args'])}")
        elif t == "tool_result":
            body = d.get("data") if d.get("ok") else d.get("error")
            lines.append(
                f"  - **Observe** ({'ok' if d.get('ok') else 'error'}): {_short(body, 220)}"
            )
        elif t == "interrupt":
            plan = d.get("plan", {})
            legs = ", ".join(
                f"{a['quantity']} from {a['depot_id']} via {a['route_id']}"
                for a in plan.get("allocations", [])
            )
            lines.append(
                f"- **[{e['step']}] ⏸ Approval requested:** {plan.get('ward_id')} "
                f"{plan.get('resource')} for {plan.get('people')} people: {legs}; team "
                f"{plan.get('team_id')}, ETA {plan.get('eta_minutes')} min"
            )
        elif t == "answer":
            lines.append(f"- **Answer:** {d['text']}")
    return "\n".join(lines) + "\n"


def summary_markdown(runs: list[dict[str, Any]], model: str) -> str:
    lines = [
        "# Evaluation results (generated)",
        "",
        f"Model: `{model}` on Groq · embeddings: local `bge-small-en-v1.5` · max steps 8 "
        "unless the scenario overrides it. Regenerate with "
        "`cd backend && uv run python -m scripts.run_eval`.",
        "",
        "| ID | Scenario | Result | Status | Steps | Tool calls | Unnecessary | "
        "Proposals (invalid) | Approval respected | Plans valid | Latency s | Tokens |",
        "|----|----------|--------|--------|------:|-----------:|------------:|"
        "--------------------|--------------------|-------------|----------:|-------:|",
    ]
    for r in runs:
        sc, out, m = r["scenario"], r["outcome"], r["metrics"]
        valid = m["dispatched_plans_valid_against_seed"]
        lines.append(
            f"| [{sc['id']}](traces/{sc['id']}.md) | {sc['title']} | "
            f"{'PASS' if out['passed'] else 'FAIL'} | `{out['final_status']}` | "
            f"{m['steps_total']} | {m['tool_calls']} | {len(m['unnecessary_tool_calls'])} | "
            f"{m['dispatch_proposals']} ({len(m['invalid_proposals'])}) | "
            f"{'yes' if m['approval_respected'] else 'NO'} | "
            f"{f'{sum(valid)}/{len(valid)}' if valid else '-'} | {m['latency_s']} | "
            f"{m['tokens_in'] + m['tokens_out']} |"
        )
    total = len(runs)
    passed = sum(r["outcome"]["passed"] for r in runs)
    calls = sum(r["metrics"]["tool_calls"] for r in runs)
    unnecessary = sum(len(r["metrics"]["unnecessary_tool_calls"]) for r in runs)
    proposals = sum(r["metrics"]["dispatch_proposals"] for r in runs)
    invalid = sum(len(r["metrics"]["invalid_proposals"]) for r in runs)
    lines += [
        "",
        f"**Totals:** {passed}/{total} scenarios passed · {calls} tool calls, {unnecessary} "
        f"unnecessary ({unnecessary / calls:.0%}) · {proposals} dispatch proposals, {invalid} "
        "stopped by the plan validator before reaching the coordinator."
        if calls and proposals
        else f"**Totals:** {passed}/{total} scenarios passed.",
        "",
    ]
    failures = [
        (r["scenario"]["id"], k) for r in runs for k, v in r["outcome"]["checks"].items() if not v
    ]
    if failures:
        lines += ["**Failed checks:**", *[f"- {sid}: {k}" for sid, k in failures], ""]
    invalid_list = [
        (r["scenario"]["id"], e) for r in runs for e in r["metrics"]["invalid_proposals"]
    ]
    if invalid_list:
        lines += [
            "**Proposals stopped by the validator:**",
            *[f"- {sid}: {_short(e, 300)}" for sid, e in invalid_list],
            "",
        ]
    return "\n".join(lines)
