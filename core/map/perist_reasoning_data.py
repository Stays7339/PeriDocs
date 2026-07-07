# ==========================================
# core/map/perist_reasoning_data.py
# Save-state: 2026-07-07T11:32-04:00
# ==========================================
import os
import re
import glob
import logging


from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, DCTERMS

logger = logging.getLogger(__name__)


PERIDOCS = Namespace("urn:peridocs:")

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")



async def persist_reasoning_data(reasoning_id: str, reasoning_file_turtle: str) -> None:
    """
    Generic TTL persistence layer for ALL reasoning artifacts.

    Naming rules:
    - centroid_*  → uses centroid_id directly
    - everything else → ISO-8601 filesystem-safe timestamp
    """

    reasoning_file_DIR = os.path.join(DATA_DIR, "reasoning")
    os.makedirs(reasoning_file_DIR, exist_ok=True)

    file_id = reasoning_id

    final_path = os.path.join(reasoning_file_DIR, f"{file_id}.ttl")
    tmp_path = final_path + ".tmp"

    # atomic write
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(reasoning_file_turtle)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, final_path)

def concept_exists(label: str, description: str) -> bool:
    ttl_dir = os.path.join(DATA_DIR, "reasoning")

    if not os.path.exists(ttl_dir):
        return False

    for path in glob.glob(os.path.join(ttl_dir, "*.ttl")):
        try:
            g = Graph()
            g.parse(path, format="turtle")

            for s in g.subjects(RDFS.label, Literal(label)):
                if (s, DCTERMS.description, Literal(description)) in g:
                    return True

        except Exception:
            continue

    return False

# ------------------------------------------------------------
# TTL STUB CREATION (heuristic materialization entrypoint)
# ------------------------------------------------------------

def create_reasoning_data_from_heuristic(
    graph: Graph,
    heuristic_id: str,
    concept_id: str,
    file_id: str,
    label: Optional[str] = None,
    description: Optional[str] = None
) -> URIRef:

    # Fix: Directly use the clean concept_id passed from the router
    uri = PERIDOCS[concept_id]

    exists = (uri, None, None) in graph
    if exists:
        return uri

    graph.add((uri, RDF.type, PERIDOCS.Concept))
    graph.add((uri, DCTERMS.source, Literal(heuristic_id)))
    graph.add((uri, DCTERMS.created, Literal(datetime.now(timezone.utc).isoformat())))

    if label:
        graph.add((uri, RDFS.label, Literal(label)))

    if description:
        graph.add((uri, DCTERMS.description, Literal(description)))

    return uri



async def create_reasoning_data_for_centroid_state(
    centroid_state,
    centroid_id: str,
) -> Graph:
    
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