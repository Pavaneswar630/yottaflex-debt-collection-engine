"""Canonical seeded NumPy random streams used by data generation."""

from collections.abc import Iterator

import numpy as np
from numpy.random import Generator

from yottaflex_debt_collection.settings import DEFAULT_SEED

ENTITY_STREAMS = (
    "customer",
    "account",
    "loan",
    "installment",
    "delinquency_snapshot",
    "contact_preference",
    "contact_attempt",
    "promise_to_pay",
    "payment",
    "collection_case",
    "payment_allocation",
    "promise_reconciliation",
    "case_state_history",
    "decision_log",
    "ground_truth",
)


class EntityRandomStreams:
    """Create reproducible, isolated child generators for named entities."""

    def __init__(
        self, seed: int = DEFAULT_SEED, stream_names: tuple[str, ...] = ENTITY_STREAMS
    ) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not stream_names or any(
            not isinstance(name, str) or not name for name in stream_names
        ):
            raise ValueError("stream names must be non-empty strings")
        if len(set(stream_names)) != len(stream_names):
            raise ValueError("stream names must be unique")

        children = np.random.SeedSequence(seed).spawn(len(stream_names))
        self._generators = {
            name: np.random.default_rng(child)
            for name, child in zip(stream_names, children)
        }

    def for_entity(self, entity: str) -> Generator:
        """Return the persistent child generator assigned to an entity."""
        try:
            return self._generators[entity]
        except KeyError:
            raise ValueError(f"No random stream configured for {entity!r}") from None

    def names(self) -> Iterator[str]:
        """Iterate configured stream names in their stable order."""
        return iter(self._generators)


RNG = EntityRandomStreams(DEFAULT_SEED)


def rng_for(entity: str) -> Generator:
    """Get the singleton seeded generator for a named entity stream."""
    return RNG.for_entity(entity)
