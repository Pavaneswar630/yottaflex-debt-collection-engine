"""Deterministic, sequential identifiers for generated records."""

import re


_SAFE_PREFIX = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\Z")
_GLOBAL_ID_PREFIXES = {
    "customer": "CUS",
    "account": "ACC",
    "loan": "LOAN-2026",
    "delinquency_snapshot": "DLS-2026",
    "contact_preference": "CPF-2026",
    "collection_case": "COL-2026",
    "case_state_history": "CSH",
    "payment": "PMT-2026",
}
_LOAN_ID = re.compile(r"LOAN-2026-\d{6}\Z")
_CASE_ID = re.compile(r"COL-2026-\d{6}\Z")
_GLOBAL_COUNTER_MAX = 999_999
_CHILD_COUNTER_MAX = 999


def make_id(prefix: str, n: int, width: int) -> str:
    """Build a deterministic ID from a stable prefix and zero-padded counter."""
    if not isinstance(prefix, str) or _SAFE_PREFIX.fullmatch(prefix) is None:
        raise ValueError(f"Invalid ID prefix: {prefix!r}")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("ID counter must be a positive integer")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("ID width must be a positive integer")
    if n >= 10**width:
        raise OverflowError(f"ID counter {n} does not fit width {width}")
    return f"{prefix}-{n:0{width}d}"


def loan_id(n: int) -> str:
    """Build a loan ID."""
    return make_id("LOAN-2026", n, 6)


def installment_id(parent_loan_id: str, n: int) -> str:
    """Build an installment ID scoped to a valid loan ID."""
    IdFactory._require_parent_id(parent_loan_id, _LOAN_ID, "loan")
    return make_id(f"INS-{parent_loan_id}", n, 3)


def case_id(n: int) -> str:
    """Build a collection case ID."""
    return make_id("COL-2026", n, 6)


def contact_id(parent_case_id: str, n: int) -> str:
    """Build a contact-attempt ID scoped to a valid collection case ID."""
    IdFactory._require_parent_id(parent_case_id, _CASE_ID, "collection case")
    return make_id(f"CTP-{parent_case_id}", n, 3)


def promise_id(parent_case_id: str, n: int) -> str:
    """Build a promise-to-pay ID scoped to a valid collection case ID."""
    IdFactory._require_parent_id(parent_case_id, _CASE_ID, "collection case")
    return make_id(f"PTP-{parent_case_id}", n, 3)


def case_state_history_id(n: int) -> str:
    """Build a case-state-history event ID."""
    return make_id("CSH", n, 6)


def payment_id(n: int) -> str:
    """Build a payment ID."""
    return make_id("PMT-2026", n, 6)


class IdFactory:
    """Issue immutable string IDs using schema-defined formats and counters."""

    def __init__(self) -> None:
        self._global_counters = {name: 0 for name in _GLOBAL_ID_PREFIXES}
        self._installment_counters: dict[str, int] = {}
        self._contact_attempt_counters: dict[str, int] = {}
        self._promise_counters: dict[str, int] = {}

    def next_id(self, entity: str) -> str:
        """Return the next globally numbered ID for a supported entity."""
        try:
            prefix = _GLOBAL_ID_PREFIXES[entity]
        except KeyError:
            raise ValueError(f"Unsupported ID entity: {entity!r}") from None

        counter = self._global_counters[entity] + 1
        if counter > _GLOBAL_COUNTER_MAX:
            raise OverflowError(f"{entity} ID counter exceeds six digits")
        self._global_counters[entity] = counter
        return make_id(prefix, counter, 6)

    def next_installment_id(self, loan_id: str) -> str:
        """Return the next installment ID scoped to a validated loan ID."""
        self._require_parent_id(loan_id, _LOAN_ID, "loan")
        counter = self._increment_child_counter(self._installment_counters, loan_id)
        return installment_id(loan_id, counter)

    def next_contact_attempt_id(self, case_id: str) -> str:
        """Return the next contact-attempt ID scoped to a validated case ID."""
        self._require_parent_id(case_id, _CASE_ID, "collection case")
        counter = self._increment_child_counter(self._contact_attempt_counters, case_id)
        return contact_id(case_id, counter)

    def next_promise_id(self, case_id: str) -> str:
        """Return the next promise ID scoped to a validated collection case."""
        self._require_parent_id(case_id, _CASE_ID, "collection case")
        counter = self._increment_child_counter(self._promise_counters, case_id)
        return promise_id(case_id, counter)

    @staticmethod
    def _require_parent_id(value: str, pattern: re.Pattern[str], name: str) -> None:
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise ValueError(f"Invalid {name} ID: {value!r}")

    @staticmethod
    def _increment_child_counter(counters: dict[str, int], parent_id: str) -> int:
        counter = counters.get(parent_id, 0) + 1
        if counter > _CHILD_COUNTER_MAX:
            raise OverflowError(f"Child ID counter for {parent_id} exceeds three digits")
        counters[parent_id] = counter
        return counter
