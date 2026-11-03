"""Tests for the deterministic database-backed demo command."""

import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class DemoCommandTests(unittest.TestCase):
    def test_demo_shows_queue_suppression_and_blocked_contact(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "demo.sqlite"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE priority_queue (
                    case_id TEXT,
                    priority_tier TEXT,
                    priority_score REAL,
                    days_past_due INTEGER,
                    arrears_amount INTEGER
                );
                CREATE TABLE collection_case (
                    case_id TEXT,
                    status TEXT,
                    suppression_rule_id TEXT,
                    priority_score REAL
                );
                CREATE TABLE decision_log (
                    case_id TEXT,
                    rule_id TEXT,
                    outcome TEXT,
                    reason TEXT,
                    decision_type TEXT,
                    as_of_date TEXT,
                    decision_id TEXT
                );
                INSERT INTO priority_queue VALUES
                    ('COL-2026-000001', 'P1', 90.5, 120, 123456);
                INSERT INTO collection_case VALUES
                    ('COL-2026-000002', 'paused', 'R-DISPUTE-01', 80.0);
                INSERT INTO decision_log VALUES
                    ('COL-2026-000003', 'R-CONTACT-01', 'block',
                     'outside permitted local window', 'contact_blocked',
                     '2026-10-31', 'DEC-2026-000001');
                """
            )
            connection.commit()
            connection.close()

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "demo.py"),
                    "--db",
                    str(database),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("COL-2026-000001", result.stdout)
        self.assertIn("Suppressed case", result.stdout)
        self.assertIn("R-DISPUTE-01", result.stdout)
        self.assertIn("Blocked contact", result.stdout)
        self.assertIn("R-CONTACT-01", result.stdout)
        self.assertIn("No contacts are sent or scheduled", result.stdout)


if __name__ == "__main__":
    unittest.main()
