"""Smoke tests for the scaffold command-line entry point."""

import unittest

from yottaflex_debt_collection.cli import main


class CliTests(unittest.TestCase):
    def test_main_accepts_no_arguments(self) -> None:
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
