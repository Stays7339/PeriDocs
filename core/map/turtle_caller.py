# ==========================================
# core/map/turtle_caller.py
# Save-state: 2026-04-15T16:22:05-04:00
# Derived ontology builder (JSON -> RDF/Turtle)
# ==========================================

import logging
from typing import Dict, Any, List, Optional

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, DCTERMS

logger = logging.getLogger(__name__)


PERIDOCS = Namespace("urn:peridocs:")

# ------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------

async def build_rdf_for_centroid_state(
    centroid_state,
    centroid_id: str,
) -> Graph:
    """
    Build RDF graph from an in-memory CentroidState object.

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
    rdflib.Graph
        Fully constructed RDF graph representation of centroid + metadata
    """

    graph = Graph()
    graph.bind("peridocs", PERIDOCS)

    centroid_uri = PERIDOCS[f"centroid:{centroid_id}"]

    # ------------------------------------------------------------
    # Core centroid identity
    # ------------------------------------------------------------
    graph.add((centroid_uri, RDF.type, PERIDOCS.Centroid))
    graph.add((centroid_uri, RDFS.label, Literal(getattr(centroid_state, "title_from_human_moderator", ""))))
    graph.add((centroid_uri, DCTERMS.description, Literal(getattr(centroid_state, "description_from_human_moderator", ""))))

    logger.info("[rdf_builder] Built RDF graph for centroid: %s", centroid_id)

    return graph


# ------------------------------------------------------------
# Export helper (keeps RDF generation + serialization separate)
# ------------------------------------------------------------

def serialize_graph_to_turtle(graph: Graph) -> str:
    """
    Serialize RDF graph into Turtle format.

    Kept separate to preserve clean separation between:
        - ontology construction
        - representation output
    """

    return graph.serialize(format="turtle")