# ==========================================
# core/reasoning/reasoning.py
# Save-state: 2026-03-30T17:15:10-04:00
# ==========================================

import os
import json
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from owlrl import DeductiveClosure, OWLRL_Semantics

EX = Namespace("http://peridocs.org/ontology/")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CENTROID_DIR = os.path.join(BASE_DIR, "data", "centroids")
ENTRIES_FILE = os.path.join(BASE_DIR, "data", "entries", "entries.json")
ONTOLOGY_PATH = os.path.join(os.path.dirname(__file__), "ontology.ttl")


# --------------------------------------------------
# LOAD ENTRY
# --------------------------------------------------

def _load_entry(entry_id: str) -> dict:
    with open(ENTRIES_FILE, "r") as f:
        data = json.load(f)

    for e in data:
        if e["entry_id"] == entry_id:
            return e

    raise RuntimeError(f"Entry not found: {entry_id}")


# --------------------------------------------------
# LOAD CENTROID TITLE (APPROVED ONLY)
# --------------------------------------------------

def _load_centroid_title(centroid_filename: str) -> str:
    path = os.path.join(CENTROID_DIR, centroid_filename)

    with open(path, "r") as f:
        data = json.load(f)

    # Walk backwards → last approved state
    for state in reversed(data["states"]):
        if state["metadata"]["review_status"] == "approved":
            return state["metadata"]["title_from_human_moderator"]

    return ""


# --------------------------------------------------
# TITLE → ONTOLOGY CLASS (MINIMAL + DETERMINISTIC)
# --------------------------------------------------

def _title_to_classes(title: str):
    """
    No centroid IDs used.
    Only transforms human label → ontology classes.
    """

    t = title.lower()

    classes = set()

    # Minimal signal extraction from real titles
    if "comfort" in t:
        classes.add(EX.Comfort)

    if "connection" in t or "relationship" in t:
        classes.add(EX.ConnectionFragility)

    if "resilience" in t or "lack" in t:
        classes.add(EX.ConnectionFragility)

    return list(classes)


# --------------------------------------------------
# BUILD GRAPH FOR ENTRY
# --------------------------------------------------

def _build_graph(entry_id: str, classes):
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")

    entry_node = URIRef(f"http://peridocs.org/entry/{entry_id}")

    for cls in classes:
        g.add((entry_node, RDF.type, cls))

    return g, entry_node


# --------------------------------------------------
# RUN REASONING
# --------------------------------------------------

def _apply_reasoning(graph: Graph):
    DeductiveClosure(OWLRL_Semantics).expand(graph)
    return graph


# --------------------------------------------------
# EXTRACT RESULT SIGNALS
# --------------------------------------------------

def _extract(graph: Graph, entry_node):
    return {
        "turbulence": (entry_node, RDF.type, EX.RelationalTurbulence) in graph,
        "needs_preparation": (entry_node, RDF.type, EX.PreparationForStress) in graph,
    }


# --------------------------------------------------
# FINAL OUTPUT
# --------------------------------------------------

def _to_message(signals: dict) -> str:
    if signals["needs_preparation"]:
        return (
            "This entry may reflect overlapping or unstable relationship dynamics. "
            "It may be useful to explore material on setting expectations and boundaries "
            "during stable periods to better prepare for future stress."
        )

    if signals["turbulence"]:
        return (
            "This entry may reflect relational instability across multiple contexts."
        )

    return ""


# --------------------------------------------------
# PUBLIC FUNCTION
# --------------------------------------------------

def reason_from_entry_id(entry_id: str) -> dict:
    """
    This is the only function you call.

    It:
    1. Loads entry
    2. Gets centroid membership
    3. Loads centroid titles
    4. Converts titles → ontology classes
    5. Builds RDF graph
    6. Applies OWL reasoning
    7. Extracts signals
    8. Returns deterministic suggestion
    """

    entry = _load_entry(entry_id)

    centroid_files = entry.get("centroids", [])
    all_classes = set()

    for cf in centroid_files:
        title = _load_centroid_title(cf)
        classes = _title_to_classes(title)
        all_classes.update(classes)

    graph, entry_node = _build_graph(entry_id, list(all_classes))
    graph = _apply_reasoning(graph)

    signals = _extract(graph, entry_node)
    message = _to_message(signals)

    return {
        "entry_id": entry_id,
        "classes": [str(c) for c in all_classes],
        "signals": signals,
        "message": message,
    }