"""Contract tests for deterministic record identifier helpers."""

import re
import unittest

from yottaflex_debt_collection.ids import (
    case_id,
    case_state_history_id,
    contact_id,
    installment_id,
    loan_id,
    make_id,
    payment_id,
    promise_id,
    IdFactory,
)


class IdHelpersTests(unittest.TestCase):
    def test_patterns_and_zero_padding(self) -> None:
        loan = loan_id(1)
        case = case_id(12)
        self.assertRegex(loan, re.compile(r"^LOAN-2026-\d{6}$"))
        self.assertRegex(installment_id(loan, 1), re.compile(r"^INS-LOAN-2026-\d{6}-\d{3}$"))
        self.assertRegex(case, re.compile(r"^COL-2026-\d{6}$"))
        self.assertRegex(contact_id(case, 7), re.compile(r"^CTP-COL-2026-\d{6}-\d{3}$"))
        self.assertRegex(payment_id(8), re.compile(r"^PMT-2026-\d{6}$"))
        self.assertRegex(promise_id(case, 7), re.compile(r"^PTP-COL-2026-\d{6}-\d{3}$"))
        self.assertRegex(case_state_history_id(1), re.compile(r"^CSH-\d{6}$"))
        self.assertEqual(loan, "LOAN-2026-000001")
        self.assertEqual(installment_id(loan, 1), f"INS-{loan}-001")
        self.assertEqual(case, "COL-2026-000012")
        self.assertEqual(contact_id(case, 7), f"CTP-{case}-007")
        self.assertEqual(payment_id(8), "PMT-2026-000008")
        self.assertEqual(promise_id(case, 7), f"PTP-{case}-007")
        self.assertEqual(case_state_history_id(1), "CSH-000001")
        factory = IdFactory()
        self.assertEqual(factory.next_id("customer"), "CUS-000001")
        self.assertEqual(factory.next_id("account"), "ACC-000001")
        decision = factory.next_id("decision_log")
        self.assertRegex(decision, re.compile(r"^DEC-2026-\d{6}$"))
        self.assertEqual(decision, "DEC-2026-000001")
        self.assertEqual(factory.next_id("state_event"), "STE-2026-000001")

    def test_same_input_is_immutable_and_deterministic(self) -> None:
        self.assertEqual(make_id("LOAN-2026", 23, 6), make_id("LOAN-2026", 23, 6))
        self.assertEqual(loan_id(23), "LOAN-2026-000023")
        self.assertEqual(installment_id(loan_id(23), 4), installment_id(loan_id(23), 4))

    def test_distinct_counters_produce_unique_ids(self) -> None:
        self.assertEqual(len({loan_id(number) for number in range(1, 101)}), 100)
        self.assertEqual(len({case_id(number) for number in range(1, 101)}), 100)
        self.assertEqual(len({payment_id(number) for number in range(1, 101)}), 100)
        self.assertEqual(
            len({case_state_history_id(number) for number in range(1, 101)}), 100
        )
        factory = IdFactory()
        self.assertEqual(
            len({factory.next_id("decision_log") for _ in range(100)}), 100
        )
        factory = IdFactory()
        self.assertEqual(len({factory.next_id("state_event") for _ in range(100)}), 100)
        loan = loan_id(1)
        self.assertEqual(
            len({installment_id(loan, number) for number in range(1, 101)}), 100
        )
        case = case_id(1)
        self.assertEqual(len({promise_id(case, n) for n in range(1, 101)}), 100)

    def test_invalid_prefix_counter_width_and_parent_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_id("loan", 1, 6)
        with self.assertRaises(ValueError):
            make_id("LOAN", 0, 6)
        with self.assertRaises(ValueError):
            make_id("LOAN", 1, 0)
        with self.assertRaises(OverflowError):
            make_id("LOAN", 1000, 3)
        with self.assertRaises(ValueError):
            installment_id("LOAN-2026-1", 1)
        with self.assertRaises(ValueError):
            contact_id("COL-2026-1", 1)


if __name__ == "__main__":
    unittest.main()
