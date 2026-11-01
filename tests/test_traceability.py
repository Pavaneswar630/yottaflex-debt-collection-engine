"""Verify traceability matrix shape and required brief coverage."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDS = (
    [f"**R{i:02d}**" for i in range(1, 3)]
    + [f"**D{i:02d}**" for i in range(1, 13)]
    + [f"**B{i:02d}**" for i in range(1, 6)]
    + [f"**W{i:02d}**" for i in range(1, 16)]
    + [f"**G{i:02d}**" for i in range(1, 24)]
    + [f"**V{i:02d}**" for i in range(1, 21)]
    + [f"**P{i:02d}**" for i in range(1, 11)]
)


class TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (ROOT / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8")

    def test_all_traceability_tables_use_the_required_four_columns(self) -> None:
        for line in self.text.splitlines():
            if line.startswith("|"):
                with self.subTest(line=line[:80]):
                    self.assertEqual(len(line[1:-1].split("|")), 4)
        self.assertIn("| Brief sentence | Module | Test | Doc |", self.text)

    def test_every_prior_matrix_requirement_id_is_retained(self) -> None:
        for requirement_id in EXPECTED_IDS:
            with self.subTest(requirement_id=requirement_id):
                self.assertIn(requirement_id, self.text)

    def test_steps_rules_edge_cases_and_five_acceptance_items_are_explicit(self) -> None:
        for number in range(1, 11):
            self.assertIn(f"| Step {number}:", self.text)
        for number in range(1, 6):
            self.assertIn(f"| Business rule {number}:", self.text)
            self.assertIn(f"| Acceptance {number}:", self.text)
        for issue in (
            "a paid account remains in collection",
            "contact occurs outside the allowed window",
            "payment is allocated to the wrong installment",
            "promise amount exceeds arrears",
            "disputed debt is treated as confirmed",
        ):
            self.assertIn(issue, self.text)


if __name__ == "__main__":
    unittest.main()
