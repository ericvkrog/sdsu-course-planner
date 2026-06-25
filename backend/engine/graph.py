"""
NetworkX DAG builder for prerequisite relationships.

Edge direction: A → B means "A must be completed before B."

This module is pure graph manipulation — no DB calls, no course-domain logic.
The solver and API route pass in rows fetched from the prerequisites table.
"""

from typing import Any

import networkx as nx


def build_graph(prerequisites: list[dict[str, Any]]) -> nx.DiGraph:
    """
    Build a directed prerequisite graph from prerequisite table rows.

    Each row must have:
      - course_code: the course that has the requirement
      - prereq_code: the course that must come first (may be None for
        standing-only requirements)
      - prereq_type, min_standing: stored as edge/node attributes

    Standing-only rows (prereq_code is None) add the course as a node with
    a min_standing attribute so the solver can read it later.
    """
    G: nx.DiGraph = nx.DiGraph()

    for row in prerequisites:
        course = row.get("course_code")
        prereq = row.get("prereq_code")

        if prereq:
            # Edge attributes carry the full row data for downstream inspection.
            attrs = {
                k: v for k, v in row.items()
                if k not in ("course_code", "prereq_code")
            }
            G.add_edge(prereq, course, **attrs)
        elif course:
            # Standing-only requirement: add the node so it's visible to the solver.
            # Merge with any existing node attributes to avoid duplicate-kwarg errors
            # when a course has more than one standing-only row.
            attrs = dict(G.nodes.get(course, {}))
            attrs["min_standing"] = row.get("min_standing")
            G.add_node(course, **attrs)

    return G


def break_cycles(G: nx.DiGraph) -> list[tuple[str, str]]:
    """
    Remove edges that form cycles in-place, returning the removed edges.

    Mutual pairs (A↔B) — e.g. CS 150 ↔ CS 150L co-requisites scraped as
    mutual prereqs — have BOTH edges removed so the solver treats them as
    independent and can place them in the same semester.

    Longer cycles have their last edge removed until the graph is acyclic.
    """
    removed: list[tuple[str, str]] = []

    # Pass 1: remove all mutual pairs (A→B and B→A both present).
    for u, v in list(G.edges()):
        if G.has_edge(u, v) and G.has_edge(v, u):
            G.remove_edge(u, v)
            G.remove_edge(v, u)
            removed.extend([(u, v), (v, u)])

    # Pass 2: break any remaining longer cycles by removing one edge at a time.
    while True:
        try:
            nx.find_cycle(G)
        except nx.NetworkXNoCycle:
            break
        cycle = nx.find_cycle(G)
        u, v = cycle[-1][0], cycle[-1][1]
        G.remove_edge(u, v)
        removed.append((u, v))
    return removed


def topological_order(G: nx.DiGraph) -> list[str]:
    """
    Return course codes in a valid completion order (all prereqs before dependents).

    Cycles are broken automatically (see break_cycles). Real cyclic prereqs
    cannot exist in a valid curriculum; cycles in the data are concurrent
    enrollment pairs that the scraper captured as mutual prerequisites.
    """
    break_cycles(G)
    return list(nx.topological_sort(G))


def prereq_chain(G: nx.DiGraph, course_code: str) -> nx.DiGraph:
    """
    Return a subgraph containing the full prerequisite tree for a course.

    Includes the course itself and all its transitive ancestors.
    Used by the /courses/{code}/prereq-graph endpoint.
    """
    if course_code not in G:
        return nx.DiGraph()
    ancestors = nx.ancestors(G, course_code) | {course_code}
    return G.subgraph(ancestors).copy()


def to_d3(subgraph: nx.DiGraph, courses_by_code: dict[str, dict]) -> dict:
    """
    Serialize a prerequisite subgraph to the {nodes, edges} format the
    frontend D3 visualization expects.

    Args:
        subgraph: A subgraph of the full prereq DAG (e.g. from prereq_chain).
        courses_by_code: Map of course_code → course dict for label/unit data.

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    nodes = []
    for node in subgraph.nodes:
        course = courses_by_code.get(node, {})
        nodes.append({
            "id": node,
            "label": course.get("title", node),
            "units": course.get("units", 0),
        })

    edges = [
        {"source": u, "target": v}
        for u, v in subgraph.edges
    ]

    return {"nodes": nodes, "edges": edges}
