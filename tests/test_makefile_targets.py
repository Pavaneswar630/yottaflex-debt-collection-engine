"""Verify the documented workflow targets remain available."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TARGETS = {
    "setup",
    "data",
    "data-starter",
    "validate",
    "repro",
    "test",
    "api",
    "ui",
    "demo",
    "eval-ai",
}


class MakefileTargetTests(unittest.TestCase):
    def test_required_make_targets_are_defined(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        targets = {
            line.split(":", maxsplit=1)[0].removeprefix(".PHONY")
            for line in makefile.splitlines()
            if ":" in line and not line.startswith("\t")
        }
        self.assertTrue(REQUIRED_TARGETS <= targets)


if __name__ == "__main__":
    unittest.main()
