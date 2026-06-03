# ==========================================
# PeriDocs/audit_entries_store.py
# Save-state: 2026-06-03T11:50-04:00
#
# Purpose:
# Read-only integrity audit for the PeriDocs
# entries subsystem.
#
# Validates:
#
# 1. entries.json
# 2. entries_mean_embeddings_dump.npz
# 3. entries_clause_embeddings_dump.npz
# 4. entries_standout_flags_dump.npz
#
# Checks:
#
# - expected files exist
# - NPZ contents are readable
# - embedding dimensions are correct
# - no empty arrays
# - no all-zero embeddings
# - matching entry hashes
# - clause count == standout flag count
# - orphaned records
#
# Does NOT modify any data.
#
# Usage:
# 'python audit_entries_store.py data/entries'
# ==========================================

import os
import json
import sys
import numpy as np

EMBEDDING_DIM = 1024

BAD = []
WARNINGS = []


def fail(*parts):
    BAD.append(" ".join(str(x) for x in parts))


def warn(*parts):
    WARNINGS.append(" ".join(str(x) for x in parts))


def banner(text):
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def load_npz(path):
    try:
        return np.load(path, allow_pickle=True)
    except Exception as exc:
        fail(f"Unable to load NPZ: {path} ({exc})")
        return None


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        fail(f"Unable to load JSON: {path} ({exc})")
        return None


def validate_mean_embeddings(data):
    hashes = set()

    for key in data.files:

        hashes.add(key)

        v = data[key]

        if v.shape != (EMBEDDING_DIM,):
            fail(
                f"mean_embeddings: {key} "
                f"expected {(EMBEDDING_DIM,)} "
                f"got {v.shape}"
            )
            continue

        if v.size == 0:
            fail(f"mean_embeddings: {key} empty array")

        elif np.all(v == 0):
            fail(f"mean_embeddings: {key} all-zero vector")

    return hashes


def validate_clause_embeddings(data):
    hashes = set()
    clause_counts = {}

    for key in data.files:

        hashes.add(key)

        v = data[key]

        if len(v.shape) != 2:
            fail(
                f"clause_embeddings: {key} "
                f"expected 2D array got {v.shape}"
            )
            continue

        rows, cols = v.shape

        clause_counts[key] = rows

        if cols != EMBEDDING_DIM:
            fail(
                f"clause_embeddings: {key} "
                f"expected second dimension "
                f"{EMBEDDING_DIM}, got {cols}"
            )

        if rows == 0:
            fail(f"clause_embeddings: {key} contains zero clauses")

        elif np.all(v == 0):
            fail(f"clause_embeddings: {key} all-zero matrix")

    return hashes, clause_counts


def validate_standout_flags(data):
    hashes = set()
    flag_counts = {}

    for key in data.files:

        hashes.add(key)

        v = data[key]

        if len(v.shape) != 1:
            fail(
                f"standout_flags: {key} "
                f"expected 1D array got {v.shape}"
            )
            continue

        flag_counts[key] = len(v)

        if v.size == 0:
            fail(f"standout_flags: {key} empty array")

    return hashes, flag_counts


def extract_entry_hashes(entries_json):
    """
    Conservative extraction.

    We do not assume a specific schema because
    PeriDocs may evolve over time.
    """

    hashes = set()

    if isinstance(entries_json, list):

        for item in entries_json:

            if isinstance(item, dict):

                for candidate_key in (
                    "entry_hash",
                    "hash",
                    "id",
                    "entry_id",
                ):

                    value = item.get(candidate_key)

                    if isinstance(value, str):
                        hashes.add(value)

    return hashes


def compare_sets(label, reference, candidate):

    missing = sorted(reference - candidate)
    extra = sorted(candidate - reference)

    if missing:
        fail(
            f"{label}: missing "
            f"{len(missing)} entries"
        )

        for item in missing[:10]:
            fail(f"  missing -> {item}")

    if extra:
        fail(
            f"{label}: orphaned "
            f"{len(extra)} entries"
        )

        for item in extra[:10]:
            fail(f"  orphaned -> {item}")


def main():

    if len(sys.argv) != 2:
        raise RuntimeError(
            "Usage: python audit_entries_store.py "
            "<path_to_data_entries_folder>"
        )

    entries_dir = os.path.abspath(sys.argv[1])

    if not os.path.isdir(entries_dir):
        raise RuntimeError(
            f"Not a directory: {entries_dir}"
        )

    banner("PERIDOCS ENTRIES AUDIT")

    print("Directory:")
    print(entries_dir)

    entries_json_path = os.path.join(
        entries_dir,
        "entries.json",
    )

    mean_path = os.path.join(
        entries_dir,
        "entries_mean_embeddings_dump.npz",
    )

    clause_path = os.path.join(
        entries_dir,
        "entries_clause_embeddings_dump.npz",
    )

    standout_path = os.path.join(
        entries_dir,
        "entries_standout_flags_dump.npz",
    )

    banner("LOADING FILES")

    entries_json = load_json(entries_json_path)

    mean_npz = load_npz(mean_path)
    clause_npz = load_npz(clause_path)
    standout_npz = load_npz(standout_path)

    if any(
        x is None
        for x in (
            entries_json,
            mean_npz,
            clause_npz,
            standout_npz,
        )
    ):
        print("Audit aborted.")
        return

    banner("SCHEMA VALIDATION")

    mean_hashes = validate_mean_embeddings(mean_npz)

    clause_hashes, clause_counts = (
        validate_clause_embeddings(clause_npz)
    )

    standout_hashes, flag_counts = (
        validate_standout_flags(standout_npz)
    )

    json_hashes = extract_entry_hashes(
        entries_json
    )

    print("entries.json hashes:", len(json_hashes))
    print("mean embeddings:", len(mean_hashes))
    print("clause embeddings:", len(clause_hashes))
    print("standout flags:", len(standout_hashes))

    banner("CROSS-FILE CONSISTENCY")

    reference = (
        mean_hashes
        | clause_hashes
        | standout_hashes
        | json_hashes
    )

    compare_sets(
        "entries.json",
        reference,
        json_hashes,
    )

    compare_sets(
        "mean_embeddings",
        reference,
        mean_hashes,
    )

    compare_sets(
        "clause_embeddings",
        reference,
        clause_hashes,
    )

    compare_sets(
        "standout_flags",
        reference,
        standout_hashes,
    )

    banner("CLAUSE / FLAG CONSISTENCY")

    shared = (
        set(clause_counts.keys())
        & set(flag_counts.keys())
    )

    for key in shared:

        clauses = clause_counts[key]
        flags = flag_counts[key]

        if clauses != flags:

            fail(
                f"{key}: "
                f"{clauses} clause embeddings "
                f"but "
                f"{flags} standout flags"
            )

    banner("SUMMARY")

    print("Warnings:", len(WARNINGS))
    print("Failures:", len(BAD))

    if WARNINGS:

        print()
        print("WARNINGS")
        print("-" * 40)

        for item in WARNINGS:
            print(item)

    if BAD:

        print()
        print("FAILURES")
        print("-" * 40)

        for item in BAD:
            print(item)

    if not BAD:
        print()
        print("PASS: no integrity failures detected.")


if __name__ == "__main__":
    main()