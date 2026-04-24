# ==========================================
# core/map/perist_reasoning_data.py
# Save-state: 2026-04-24T15:27:40-04:00
# Derived ontology builder (JSON -> reasoning_file/Turtle)
# ==========================================

import logging
from typing import Dict, Any, List, Optional

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, DCTERMS

logger = logging.getLogger(__name__)


PERIDOCS = Namespace("urn:peridocs:")

# ------------------------------------------------------------
# EXISTENCE CHECK
# ------------------------------------------------------------

def concept_exists(graph: Graph, concept_id: str) -> bool:
    """
    Checks whether a centroid/concept node already exists in the graph.

    This aligns with:
      - evaluator expecting stable ConceptSignal keys
      - admin_routing concept list derived from TTL parsing
    """

    uri = PERIDOCS[f"centroid:{concept_id}"]

    return (uri, None, None) in graph


# ------------------------------------------------------------
# TTL STUB CREATION (lazy ontology expansion)
# ------------------------------------------------------------

def create_reasoning_file_stub(
    graph: Graph,
    concept_id: str,
    label: Optional[str] = None
) -> URIRef:
    """
    Ensures a concept exists in the ontology graph.

    If missing:
        - creates concept_from_heuristic node
        - assigns rdf:type Concept
        - optionally adds rdfs:label

    This is the ONLY safe place in the system to introduce new ontology nodes
    without breaking determinism elsewhere.
    """

    concept_id = normalize_concept_id(concept_id)
    uri = PERIDOCS[f"concept_from_heuristic:{concept_id}"]

    if concept_exists(graph, concept_id):
        return uri

    # ------------------------------------------------------------
    # Create stub node (minimal valid ontology entity)
    # ------------------------------------------------------------
    graph.add((uri, RDF.type, PERIDOCS.Concept))

    if label:
        graph.add((uri, RDFS.label, Literal(label)))

    logger.info(
        "Created TTL stub for missing concept: %s",
        concept_id
    )

    return uri

# ------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------

async def build_reasoning_file_for_centroid_state(
    centroid_state,
    centroid_id: str,
) -> Graph:
    """
    Build reasoning_file graph from an in-memory CentroidState object.

    This function:
        - DOES NOT read disk
        - DOES NOT mutate system state
        - IS fully deterministic from input state
        - IS intended to be called after centroid approval/persistence

    Parameters
    ----------
    centroid_state:
        In-memory CentroidState instance (source of truth input snapshot)

    centroid_id:
        Active centroid identifier (post-approval ID)

    Returns
    -------
    reasoning_filelib.Graph
        Fully constructed reasoning_file graph representation of centroid + metadata
    """

    graph = Graph()
    graph.bind("peridocs", PERIDOCS)

    centroid_uri = PERIDOCS[f"centroid:{centroid_id}"]

    # ------------------------------------------------------------
    # Core centroid identity
    # ------------------------------------------------------------
    graph.add((centroid_uri, RDF.type, PERIDOCS.Concept))

    metadata = getattr(centroid_state, "metadata", {}) or {}

    title = metadata.get("title_from_human_moderator", "")
    description = metadata.get("description_from_human_moderator", "")

    graph.add((centroid_uri, RDFS.label, Literal(title)))
    graph.add((centroid_uri, DCTERMS.description, Literal(description)))

    logger.info("[reasoning_file_builder] Built reasoning_file graph for centroid: %s", centroid_id)

    return graph


# ------------------------------------------------------------
# Export helper (keeps reasoning_file generation + serialization separate)
# ------------------------------------------------------------

def serialize_graph_to_turtle(graph: Graph) -> str:
    """
    Serialize reasoning_file graph into Turtle format.

    Kept separate to preserve clean separation between:
        - ontology construction
        - representation output
    """

    return graph.serialize(format="turtle")