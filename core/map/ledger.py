# ==========================================
# core/map/ledger.py
# Save-state: 202602192258
# ==========================================

"""
Deterministic identifier and event ledger.

Sole authority for:
- suffix issuance (precentroid / centroid)
- event index issuance
- lifecycle transitions
- replay audit history
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path


DATA_DIR = Path(os.getenv("PERIDOCS_DATA_DIR", "data"))
LEDGER_PATH = DATA_DIR / "ledger.json"

_ledger_lock = asyncio.Lock()
_ledger_cache: Dict[str, Any] | None = None


def _initial_ledger() -> Dict[str, Any]:
    return {
        "next_centroid_id": 1,
        "next_event_index": 1,
        "issued_suffixes": {},  # suffix -> allocation_type
        "events": [],
    }


async def _load() -> Dict[str, Any]:
    global _ledger_cache
    if _ledger_cache is not None:
        return _ledger_cache

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(LEDGER_PATH):
        _ledger_cache = _initial_ledger()
#        await _save(_ledger_cache)
    else:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            _ledger_cache = json.load(f)

    return _ledger_cache


async def _save(state: Dict[str, Any]) -> None:
    tmp = LEDGER_PATH.with_suffix(LEDGER_PATH.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, LEDGER_PATH)


class IdentifierLedger:
    """
    Appendix-A compliant ledger.
    Identifier allocation is a state transition.
    """

    VALID_KINDS = ("precentroid", "centroid_from_split")
    VALID_TRANSITIONS = {
        "precentroid": ("centroid",),
        "centroid_from_split": ("centroid",),
    }

    async def allocate_suffix(self, *, kind: str) -> int:
        if kind not in self.VALID_KINDS:
            raise ValueError(f"Invalid allocation kind: {kind}")

        async with _ledger_lock:
            ledger = await _load()
            suffix = ledger["next_centroid_id"]

            if str(suffix) in ledger["issued_suffixes"]:
                raise RuntimeError(f"Suffix {suffix} already issued")

            ledger["next_centroid_id"] += 1
            ledger["issued_suffixes"][str(suffix)] = {
                "kind": kind,
                "consumed": False,       # <-- track lifecycle
                "approved": False,
                "rejected": False
            }

            event_index = await self._allocate_event_index_locked(ledger)
            ledger["events"].append({
                "event_index": event_index,
                "type": "ISSUE_SUFFIX",
                "suffix": suffix,
                "kind": kind,
            })

            await _save(ledger)
            return suffix

    async def approve_suffix(self, suffix: int) -> None:
        async with _ledger_lock:
            ledger = await _load()
            record = ledger["issued_suffixes"].get(str(suffix))
            if not record:
                raise RuntimeError(f"Cannot approve unknown suffix {suffix}")
            if record["approved"]:
                raise RuntimeError(f"Suffix {suffix} already approved")
            if record["rejected"]:
                raise RuntimeError(f"Cannot approve rejected suffix {suffix}")

            record["approved"] = True
            record["consumed"] = True

            event_index = await self._allocate_event_index_locked(ledger)
            ledger["events"].append({
                "event_index": event_index,
                "type": "APPROVE_SUFFIX",
                "suffix": suffix,
            })
            await _save(ledger)

    async def reject_suffix(self, suffix: int) -> None:
        async with _ledger_lock:
            ledger = await _load()
            record = ledger["issued_suffixes"].get(str(suffix))
            if not record:
                raise RuntimeError(f"Cannot reject unknown suffix {suffix}")
            if record["approved"]:
                raise RuntimeError(f"Cannot reject already approved suffix {suffix}")
            if record["rejected"]:
                raise RuntimeError(f"Suffix {suffix} already rejected")

            record["rejected"] = True
            record["consumed"] = True

            event_index = await self._allocate_event_index_locked(ledger)
            ledger["events"].append({
                "event_index": event_index,
                "type": "REJECT_SUFFIX",
                "suffix": suffix,
            })
            await _save(ledger)

    async def record_event(self, payload: Dict[str, Any]) -> int:
        """
        Validate that payload has minimal required fields for deterministic replay.
        Enforce strong schema per event type.
        """
        # Base requirement
        if "type" not in payload:
            raise ValueError("Event payload missing required 'type' field")

        event_type = payload["type"]
        required_fields: Dict[str, set] = {
            "ISSUE_SUFFIX": {"suffix", "kind"},
            "APPROVE_SUFFIX": {"suffix"},
            "REJECT_SUFFIX": {"suffix"},
            "CREATE_PRECENTROID": {"centroid_id", "entry_ids"},
            "APPROVE_PRECENTROID": {"from", "to", "label", "nne"},
            "ADD_SAAJE": {"centroid_id", "entry_id", "similarity"},
            "REMOVE_SAAJE": {"centroid_id", "entry_id"},
            "REJECT_PRECENTROID": {"centroid_id", "failed_threshold"},
            "BURST_PRECENTROID": {"centroid_id", "threshold"},
            "SUGGEST_SPLIT": {"centroid_id", "threshold", "min_similarity"},
            "DELETE_ENTRY": {"entry_id"},
            # Extend as needed
        }

        req_keys = required_fields.get(event_type, set())
        missing = req_keys - payload.keys()
        if missing:
            raise ValueError(f"Event payload missing required keys for {event_type}: {missing}")

        async with _ledger_lock:
            ledger = await _load()
            idx = await self._allocate_event_index_locked(ledger)
            payload = dict(payload)
            payload["event_index"] = idx
            payload["occurred_at"] = datetime.now(timezone.utc).isoformat()

            # --- enforce VALID_TRANSITIONS for suffix events ---
            if event_type in {"APPROVE_SUFFIX", "REJECT_SUFFIX"}:
                suffix = payload["suffix"]
                record = ledger["issued_suffixes"].get(str(suffix))
                if not record:
                    raise RuntimeError(f"Suffix {suffix} not found for transition {event_type}")

                allowed = self.VALID_TRANSITIONS.get(record["kind"], ())
                target_prefix = "centroid" if event_type == "APPROVE_SUFFIX" else None
                if target_prefix and target_prefix not in allowed:
                    raise RuntimeError(f"Invalid lifecycle transition for suffix {suffix}: {event_type}")

            ledger["events"].append(payload)
            await _save(ledger)
            return idx

    async def replay_events(self):
        """
        Yield ledger events in strict event_index order for deterministic replay.
        """
        async with _ledger_lock:
            ledger = await _load()
            # sort by event_index just in case
            for event in sorted(ledger["events"], key=lambda e: e["event_index"]):
                yield dict(event)  # yield a copy to prevent mutation


    async def _allocate_event_index_locked(self, ledger: Dict[str, Any]) -> int:
        idx = ledger["next_event_index"]
        ledger["next_event_index"] += 1
        return idx

    async def snapshot(self) -> Dict[str, Any]:
        async with _ledger_lock:
            return json.loads(json.dumps(await _load()))

    async def is_loaded(self) -> bool:
        return _ledger_cache is not None

    async def load(self) -> None:
        """Explicitly load ledger into cache."""
        await _load()

    async def has_identifier(self, identifier: str) -> bool:
        ledger = await _load()
        # identifier = e.g. "centroid_00000000001"
        suffix = int(identifier.split("_")[1])
        return str(suffix) in ledger["issued_suffixes"]

    async def get_suffix_state(self, suffix: int) -> str:
        ledger = await _load()
        record = ledger["issued_suffixes"].get(str(suffix))
        if not record:
            raise RuntimeError(f"Suffix {suffix} unknown")
        if record["approved"]:
            return "approved"
        return "allocated"

    
    async def verify_runtime_state(self, centroids: "CentroidSystem") -> None:
        """
        Verify that all centroids in memory have corresponding ledger entries.

        Raises RuntimeError if any discrepancy is found.

        Performance:
        - Preloads ledger once (O(1) I/O)
        - Indexes event indices and issued_suffixes (O(N))
        - Scales to 10k+ centroids efficiently
        """
        # Ensure centroids are ready
        await centroids._assert_ledger_ready()

        # Preload ledger snapshot once
        ledger_snapshot = await self.snapshot()
        issued_suffixes = set(ledger_snapshot["issued_suffixes"].keys())
        ledger_event_indices = {e["event_index"] for e in ledger_snapshot["events"]}

        async with centroids._lock:
            for cid, c in centroids._centroids.items():
                # Extract numeric suffix (centroid_00000000001)
                try:
                    suffix = cid.split("_")[1]
                except IndexError:
                    raise RuntimeError(f"Invalid centroid ID format: {cid}")

                # Check if centroid exists in ledger
                if suffix not in issued_suffixes:
                    raise RuntimeError(f"Centroid {cid} exists in memory but is missing from ledger")

                # Check that each centroid state has a corresponding event
                for s in c.states:
                    if s.event_index not in ledger_event_indices:
                        raise RuntimeError(
                            f"Centroid {cid} state with event_index {s.event_index} missing in ledger"
                        )

        # Optionally: log success
        logging.getLogger("peridocs.mapping_runtime").info(
            f"Verified {len(centroids._centroids)} centroids successfully against ledger."
        )

