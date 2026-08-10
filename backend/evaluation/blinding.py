"""
evaluation/blinding.py — Keep the evaluation blind.

A judge must not be able to tell whether a document came from the ChatGPT baseline or from our own system — otherwise scores are contaminated by expectation.

This module does exactly one thing: it takes the generated documents, strips every identifying field, assigns each a neutral label ("DOC_A", "DOC_B", …) in a DETERMINISTICALLY SHUFFLED order, and hands back both the anonymized documents and private key to un-blind them again after scoring.

Deterministic (seeded) shuffling matters: the run is reproducible, but the label order is not correlated with system identity (we don't, e.g., always put the
baseline first).
"""

from __future__ import annotations

import random
from string import ascii_uppercase

from .schemas import SystemLabel, WorldDocument


class BlindingKey:
    """The private mapping from blind label -> real document identity.

    Held by the orchestrator ONLY; never passed into a judge prompt.
    """

    def __init__(self, mapping: dict[str, WorldDocument]) -> None:
        self._by_blind: dict[str, WorldDocument] = mapping

    def reveal(self, blind_id: str) -> WorldDocument:
        """Return the original document behind a blind label."""
        return self._by_blind[blind_id]

    def system_of(self, blind_id: str) -> SystemLabel:
        return self._by_blind[blind_id].system_label

    def doc_id_of(self, blind_id: str) -> str:
        return self._by_blind[blind_id].doc_id

    @property
    def blind_ids(self) -> list[str]:
        return sorted(self._by_blind)


def _label_for(index: int) -> str:
    """0 -> DOC_A, 1 -> DOC_B, ... 26 -> DOC_AA (enough for any realistic run)."""
    if index < len(ascii_uppercase):
        return f"DOC_{ascii_uppercase[index]}"
    # Fall back to a two-letter scheme for large experiments.
    first, second = divmod(index, len(ascii_uppercase))
    return f"DOC_{ascii_uppercase[first - 1]}{ascii_uppercase[second]}"


def blind_documents(
    documents: list[WorldDocument],
    seed: int = 1337,
) -> tuple[list[WorldDocument], BlindingKey]:
    """Anonymize a set of documents for evaluation.

    Returns:
        blinded  — copies with `system_label`/`run_index`/`generator` scrubbed of meaning for the judge; only `blind_id` + `content` are usable.
        (We keep the pydantic type but overwrite identity fields.)
        key       — the private un-blinding map, for the orchestrator to use AFTER all scoring is complete.

    The judge is only ever given `blind_id` and `content` (see judge.py), so even though the object still carries a `system_label` field, that field never
    reaches the model.
    """
    order = list(range(len(documents)))
    random.Random(seed).shuffle(order)             # seeded -> reproducible, uncorrelated

    blinded: list[WorldDocument] = []
    mapping: dict[str, WorldDocument] = {}

    for position, original_index in enumerate(order):
        doc = documents[original_index]
        blind_id = _label_for(position)
        # Record the TRUE identity in the private key (with its blind_id stamped).
        revealed = doc.model_copy(update={"blind_id": blind_id})
        mapping[blind_id] = revealed
        blinded.append(revealed)

    return blinded, BlindingKey(mapping)


__all__ = ["BlindingKey", "blind_documents"]
