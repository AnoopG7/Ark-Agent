"""Run the evaluation scenarios against Groq and write traces + results.

uv run python -m scripts.run_eval            # all scenarios
uv run python -m scripts.run_eval S2 S5      # selected scenarios
"""

import argparse
import json
import time

from app.agent.llm import build_chat_model
from app.core.config import REPO_ROOT, get_settings
from app.evaluation.report import summary_markdown, trace_markdown
from app.evaluation.runner import ScenarioRunner, to_json
from app.evaluation.scenarios import SCENARIOS
from app.rag.embeddings import FastEmbedEmbedder
from app.rag.ingest import sync_knowledge
from app.rag.memory_index import InMemoryVectorIndex
from app.rag.retriever import Retriever

DOCS = REPO_ROOT / "docs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Scenario ids (default: all)")
    parser.add_argument("--pause", type=float, default=20.0, help="Seconds between scenarios")
    args = parser.parse_args()

    settings = get_settings()
    embedder = FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
    )
    index = InMemoryVectorIndex()
    sync_knowledge(settings.knowledge_dir, embedder, index)
    runner = ScenarioRunner(
        build_chat_model(settings),
        Retriever(embedder, index, settings.rag_top_k, settings.rag_min_score),
        settings.max_steps,
    )

    selected = [s for s in SCENARIOS if not args.ids or s.id in args.ids]
    traces_dir = DOCS / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    for i, scenario in enumerate(selected):
        if i:
            time.sleep(args.pause)  # stay under Groq free-tier tokens-per-minute limits
        print(f"{scenario.id} {scenario.title} ...", flush=True)
        run = to_json(runner.run(scenario))
        (traces_dir / f"{scenario.id}.json").write_text(
            json.dumps(run, indent=2, ensure_ascii=False, default=str) + "\n"
        )
        (traces_dir / f"{scenario.id}.md").write_text(trace_markdown(run))
        o, m = run["outcome"], run["metrics"]
        print(
            f"   {'PASS' if o['passed'] else 'FAIL'} status={o['final_status']} "
            f"steps={m['steps_total']} calls={m['tool_calls']} "
            f"unnecessary={len(m['unnecessary_tool_calls'])} error={o['error']}"
        )

    runs = [json.loads(p.read_text()) for p in sorted(traces_dir.glob("S*.json"))]
    (DOCS / "evaluation-results.md").write_text(summary_markdown(runs, settings.groq_model))
    print(f"Wrote {DOCS / 'evaluation-results.md'}")


if __name__ == "__main__":
    main()
