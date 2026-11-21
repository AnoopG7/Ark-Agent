"""Print the compiled agent graph as Mermaid.

uv run python -m scripts.export_graph
"""

from app.agent.diagram import graph_mermaid

if __name__ == "__main__":
    print(graph_mermaid())
