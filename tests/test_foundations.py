"""Tests for deterministic IDs, random streams, dates, and integer-cent money."""

import unittest
from datetime import date
from decimal import Decimal

from yottaflex_debt_collection.ids import IdFactory
from yottaflex_debt_collection.money import as_cents, decimal_to_cents
from yottaflex_debt_collection.rng import (
    ENTITY_STREAMS,
    EntityRandomStreams,
    RNG,
    rng_for,
)
from yottaflex_debt_collection.settings import (
    AS_OF_DATE,
    DEFAULT_SEED,
    GENERATION_DATE,
    INSTALLMENTS_PER_LOAN,
)


class IdFactoryTests(unittest.TestCase):
    def test_global_ids_are_zero_padded_and_monotonically_issued(self) -> None:
        ids = IdFactory()
        self.assertEqual(ids.next_id("loan"), "LOAN-2026-000001")
        self.assertEqual(ids.next_id("loan"), "LOAN-2026-000002")
        self.assertEqual(ids.next_id("payment"), "PMT-2026-000001")
        self.assertEqual(ids.next_id("customer"), "CUS-000001")
        self.assertEqual(ids.next_id("account"), "ACC-000001")
        self.assertEqual(ids.next_id("case_state_history"), "CSH-000001")
        self.assertEqual(ids.next_id("dispute"), "DIS-2026-000001")
        self.assertEqual(ids.next_id("hardship_request"), "HRS-2026-000001")

    def test_child_ids_are_scoped_to_valid_parent_ids(self) -> None:
        ids = IdFactory()
        loan_id = ids.next_id("loan")
        case_id = ids.next_id("collection_case")

        self.assertEqual(ids.next_installment_id(loan_id), f"INS-{loan_id}-001")
        self.assertEqual(ids.next_installment_id(loan_id), f"INS-{loan_id}-002")
        self.assertEqual(ids.next_contact_attempt_id(case_id), f"CTP-{case_id}-001")
        self.assertEqual(ids.next_promise_id(case_id), f"PTP-{case_id}-001")
        self.assertEqual(ids.next_promise_id(case_id), f"PTP-{case_id}-002")
        self.assertEqual(
            ids.next_installment_id(ids.next_id("loan")),
            "INS-LOAN-2026-000002-001",
        )

    def test_invalid_entity_and_parent_ids_are_rejected(self) -> None:
        ids = IdFactory()
        with self.assertRaises(ValueError):
            ids.next_id("unknown")
        with self.assertRaises(ValueError):
            ids.next_installment_id("LOAN-2026-1")
        with self.assertRaises(ValueError):
            ids.next_contact_attempt_id("LOAN-2026-000001")


class EntityRandomStreamsTests(unittest.TestCase):
    def test_seed_repeats_named_entity_streams(self) -> None:
        first = EntityRandomStreams(DEFAULT_SEED)
        second = EntityRandomStreams(DEFAULT_SEED)

        for entity in ENTITY_STREAMS:
            self.assertEqual(
                first.for_entity(entity).integers(0, 2**31, size=8).tolist(),
                second.for_entity(entity).integers(0, 2**31, size=8).tolist(),
            )

    def test_consuming_one_stream_does_not_change_another(self) -> None:
        first = EntityRandomStreams(DEFAULT_SEED)
        second = EntityRandomStreams(DEFAULT_SEED)
        first.for_entity("customer").random(100)

        self.assertEqual(
            first.for_entity("loan").integers(0, 2**31, size=8).tolist(),
            second.for_entity("loan").integers(0, 2**31, size=8).tolist(),
        )

    def test_same_entity_reuses_its_generator(self) -> None:
        streams = EntityRandomStreams(DEFAULT_SEED)
        self.assertIs(streams.for_entity("loan"), streams.for_entity("loan"))
        self.assertIs(rng_for("loan"), RNG.for_entity("loan"))

    def test_unknown_or_invalid_streams_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EntityRandomStreams(-1)
        with self.assertRaises(ValueError):
            EntityRandomStreams(1, ("loan", "loan"))
        with self.assertRaises(ValueError):
            EntityRandomStreams(1).for_entity("unknown")


class MoneyTests(unittest.TestCase):
    def test_decimal_values_convert_to_integer_cents(self) -> None:
        self.assertEqual(decimal_to_cents(Decimal("12.34")), 1234)
        self.assertEqual(decimal_to_cents("12.345"), 1235)
        self.assertEqual(decimal_to_cents("-0.005"), -1)
        self.assertEqual(as_cents(1234), 1234)

    def test_float_boolean_and_non_finite_money_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            decimal_to_cents(12.34)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            decimal_to_cents(12)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            as_cents(True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            decimal_to_cents("NaN")


class ReproducibilityDefaultsTests(unittest.TestCase):
    def test_seed_and_as_of_date_are_fixed(self) -> None:
        self.assertEqual(DEFAULT_SEED, 20261022)
        self.assertEqual(AS_OF_DATE, date(2026, 10, 31))
        self.assertEqual(GENERATION_DATE, date(2026, 10, 31))
        self.assertEqual(INSTALLMENTS_PER_LOAN, 3)


if __name__ == "__main__":
    unittest.main()
