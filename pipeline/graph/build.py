"""Assemble the per-lead StateGraph.

START → scrape_site → embed_chunks → research_brief → write_sequence → run_evals → END
            (after every node) state.error set ──→ dead_letter → END

Uses the langgraph>=1.2 StateGraph Graph API (NOT langgraph.prebuilt, which is
deprecated). A shared conditional router diverts to dead_letter the moment any
node reports an error.
"""

from __future__ import annotations

import functools

from langgraph.graph import END, START, StateGraph

from pipeline.graph.nodes.deadletter import dead_letter_node
from pipeline.graph.nodes.embed import embed_chunks_node
from pipeline.graph.nodes.evaluate import run_evals_node
from pipeline.graph.nodes.research import research_brief_node
from pipeline.graph.nodes.scrape import scrape_site_node
from pipeline.graph.nodes.write import write_sequence_node
from pipeline.graph.state import LeadState

_NODES = [
    ("scrape_site", scrape_site_node, "embed_chunks"),
    ("embed_chunks", embed_chunks_node, "research_brief"),
    ("research_brief", research_brief_node, "write_sequence"),
    ("write_sequence", write_sequence_node, "run_evals"),
    ("run_evals", run_evals_node, END),
]


def _route(state: LeadState, ok_next: str):
    """Divert to dead_letter on error, else proceed to the node's normal successor."""
    return "dead_letter" if state.error else ok_next


@functools.lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(LeadState)
    g.add_node("dead_letter", dead_letter_node)
    g.add_edge("dead_letter", END)

    for name, fn, ok_next in _NODES:
        g.add_node(name, fn)

    g.add_edge(START, "scrape_site")
    for name, _fn, ok_next in _NODES:
        g.add_conditional_edges(
            name,
            functools.partial(_route, ok_next=ok_next),
            {"dead_letter": "dead_letter", ok_next: ok_next},
        )
    return g.compile()
