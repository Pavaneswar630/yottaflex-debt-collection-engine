from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from yottaflex_debt_collection.api import create_app
from yottaflex_debt_collection.copilot import (
    CollectionCopilot,
    ReadOnlyCollectionTools,
    TOOL_DEFINITIONS,
)
from yottaflex_debt_collection.database import connect_readonly, load_dataset
from yottaflex_debt_collection.generator import generate_dataset
from yottaflex_debt_collection.guardrails import validate_outreach_draft
from yottaflex_debt_collection.knowledge import PolicyKnowledgeIndex


ROOT = Path(__file__).resolve().parents[1]


class GuardrailTests(unittest.TestCase):
    def test_outreach_checker_rejects_all_required_issue_types(self) -> None:
        cases = {
            "THREATENING_LANGUAGE": (
                "We will sue you tomorrow. If you believe this debt is inaccurate, "
                "you may dispute it."
            ),
            "THIRD_PARTY_DISCLOSURE": (
                "We will notify your employer of this debt. If you believe this "
                "debt is inaccurate, you may dispute it."
            ),
            "ABUSIVE_LANGUAGE": (
                "You are a deadbeat. If you believe this debt is inaccurate, "
                "you may dispute it."
            ),
            "MISSING_DISPUTE_NOTICE": "Please contact us about your account.",
        }
        for expected_issue, draft in cases.items():
            with self.subTest(expected_issue=expected_issue):
                result = validate_outreach_draft(draft)
                self.assertFalse(result.accepted)
                self.assertIn(expected_issue, result.issues)

    def test_outreach_checker_accepts_neutral_draft_with_dispute_notice(self) -> None:
        result = validate_outreach_draft(
            "Hello, please contact us through your secure account channel. "
            "If you believe this debt is inaccurate, you may dispute it."
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.issues, ())


class RetrievalTests(unittest.TestCase):
    def test_bm25_retrieves_rule_chunks_with_rule_id_citations(self) -> None:
        index = PolicyKnowledgeIndex(ROOT)
        cases = (
            ("What are permitted local contact hours?", "[R-CONTACT-01]"),
            ("How are score weights distributed between balance age and risk?", "[R-SCORE-01]"),
            ("What happens to disputed debt?", "[R-DISPUTE-01]"),
            ("How are promises reconciled against payments?", "[R-RECON-01]"),
        )
        for question, citation in cases:
            with self.subTest(question=question):
                results = index.search(question, limit=4)
                self.assertIn(citation, [result.citation for result in results])

    def test_golden_questions_pass_deterministic_retrieval_evaluation(self) -> None:
        from tools.eval_ai import evaluate

        with tempfile.TemporaryDirectory() as output:
            passed, total = evaluate(
                ROOT / "tests" / "ai_golden_questions.json",
                Path(output) / "evaluation.jsonl",
            )
        self.assertEqual(total, 18)
        self.assertEqual(passed, total)


class CopilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        generate_dataset(
            500,
            20261022,
            root,
            inject_anomalies=True,
            anomaly_rows_per_type=5,
            dataset_name="full",
        )
        cls.data_dir = root / "data" / "full"
        cls.labels_dir = root / "ground_truth" / "full"
        cls.db_path = cls.data_dir / "collection.sqlite"
        load_dataset(cls.data_dir, cls.db_path, cls.labels_dir)
        with closing(connect_readonly(cls.db_path)) as connection:
            row = connection.execute(
                """
                SELECT collection_case.case_id
                FROM collection_case
                LEFT JOIN contact_preference
                    ON contact_preference.account_id = collection_case.account_id
                WHERE collection_case.status = 'open'
                    AND collection_case.suppression_rule_id IS NULL
                    AND COALESCE(contact_preference.do_not_contact, 0) = 0
                ORDER BY collection_case.case_id
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise AssertionError("Synthetic test dataset has no unrestricted open case")
        cls.case_id = str(row["case_id"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        self.log_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.log_dir.name) / "interactions.jsonl"

    def tearDown(self) -> None:
        self.log_dir.cleanup()

    def test_tools_are_fixed_read_only_and_return_recorded_case_data(self) -> None:
        names = {item["function"]["name"] for item in TOOL_DEFINITIONS}
        self.assertEqual(
            names,
            {
                "get_case",
                "get_score_breakdown",
                "list_blocked_contacts",
                "get_promise_status",
            },
        )
        tools = ReadOnlyCollectionTools(self.db_path)
        case = tools.invoke("get_case", {"case_id": self.case_id})
        score = tools.invoke("get_score_breakdown", {"case_id": self.case_id})
        promises = tools.invoke("get_promise_status", {"case_id": self.case_id})
        blocked = tools.invoke("list_blocked_contacts", {"limit": 10})
        self.assertEqual(case["case_id"], self.case_id)
        self.assertAlmostEqual(
            sum(score["weighted_points"].values()),
            float(score["priority_score"]),
            places=2,
        )
        self.assertEqual(promises["case_id"], self.case_id)
        self.assertLessEqual(len(blocked["items"]), 10)
        self.assertTrue(all(item["outcome"] == "block" for item in blocked["items"]))
        with self.assertRaises(ValueError):
            tools.invoke("write_payment", {"case_id": self.case_id})

    def test_template_fallback_logs_prompt_tool_calls_and_latency(self) -> None:
        copilot = CollectionCopilot(
            ROOT,
            self.db_path,
            log_path=self.log_path,
            api_key="",
        )
        result = copilot.answer(
            "Explain this case score",
            case_id=self.case_id,
        )
        self.assertEqual(result["provider"], "template")
        self.assertEqual(result["tools_used"], ["get_score_breakdown"])
        self.assertIn("[R-SCORE-01]", result["citations"])
        log_record = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(log_record["prompt"], "Explain this case score")
        self.assertEqual(log_record["tool_calls"][0]["name"], "get_score_breakdown")
        self.assertGreaterEqual(log_record["latency_ms"], 0)

    def test_template_refuses_suppressed_outreach_and_includes_required_notice(self) -> None:
        copilot = CollectionCopilot(
            ROOT,
            self.db_path,
            log_path=self.log_path,
            api_key="",
        )
        response = copilot.answer(
            f"Draft an account reminder message for {self.case_id}",
            case_id=self.case_id,
            force_template=True,
        )
        self.assertFalse(response["refused"])
        self.assertIn("you may dispute it", response["answer"])
        self.assertIn("get_case", response["tools_used"])

    def test_sdk_is_used_only_when_key_is_configured_and_rejects_unsafe_draft(self) -> None:
        class FakeCompletions:
            def __init__(self, content: str) -> None:
                self.content = content

            def create(self, **_: object) -> object:
                message = SimpleNamespace(content=self.content, tool_calls=None)
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        def fake_factory(**kwargs: object) -> object:
            self.assertEqual(kwargs["api_key"], "test-key")
            return SimpleNamespace(
                chat=SimpleNamespace(
                    completions=FakeCompletions(
                        "We will sue you. If you believe this debt is inaccurate, "
                        "you may dispute it."
                    )
                )
            )

        copilot = CollectionCopilot(
            ROOT,
            self.db_path,
            log_path=self.log_path,
            api_key="test-key",
            client_factory=fake_factory,
        )
        result = copilot.answer(
            "Draft a message for a customer",
            case_id=self.case_id,
        )
        self.assertEqual(result["provider"], "openai")
        self.assertTrue(result["refused"])
        self.assertIn("threatening language", result["answer"])

    def test_sdk_can_call_only_the_fixed_score_tool(self) -> None:
        class FakeMessage:
            def __init__(self, *, content: str | None, tool_calls: list[object] | None) -> None:
                self.content = content
                self.tool_calls = tool_calls

            def model_dump(self, **_: object) -> dict[str, object]:
                return {"role": "assistant", "tool_calls": self.tool_calls or []}

        class FakeCompletions:
            def __init__(self) -> None:
                self.calls = 0

            def create(self, **_: object) -> object:
                self.calls += 1
                if self.calls == 1:
                    function = SimpleNamespace(
                        name="get_score_breakdown",
                        arguments=json.dumps({"case_id": CopilotTests.case_id}),
                    )
                    tool_call = SimpleNamespace(function=function, id="tool-call-1")
                    message = FakeMessage(content=None, tool_calls=[tool_call])
                else:
                    message = FakeMessage(
                        content="The recorded score is explained by its stored components [R-SCORE-01].",
                        tool_calls=None,
                    )
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        completions = FakeCompletions()
        copilot = CollectionCopilot(
            ROOT,
            self.db_path,
            log_path=self.log_path,
            api_key="test-key",
            client_factory=lambda **_: SimpleNamespace(
                chat=SimpleNamespace(completions=completions)
            ),
        )
        result = copilot.answer("Explain this score", case_id=self.case_id)
        self.assertEqual(completions.calls, 2)
        self.assertEqual(result["tools_used"], ["get_score_breakdown"])
        self.assertIn("[R-SCORE-01]", result["citations"])

    def test_outreach_is_refused_when_case_is_suppressed(self) -> None:
        with closing(connect_readonly(self.db_path)) as connection:
            row = connection.execute(
                """
                SELECT case_id
                FROM collection_case
                WHERE suppression_rule_id IS NOT NULL
                ORDER BY case_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)
        copilot = CollectionCopilot(
            ROOT,
            self.db_path,
            log_path=self.log_path,
            api_key="",
        )
        result = copilot.answer(
            f"Draft an account reminder message for {row['case_id']}",
            case_id=str(row["case_id"]),
        )
        self.assertTrue(result["refused"])
        self.assertIn("suppression or review", result["answer"])

    def test_api_exposes_chat_and_outreach_guardrail(self) -> None:
        app = create_app(
            data_dir=self.data_dir,
            db_path=self.db_path,
            ground_truth_dir=self.labels_dir,
            ai_log_path=self.log_path,
        )
        client = TestClient(app)
        answer = client.post(
            "/copilot/chat",
            json={
                "question": "Explain the priority score",
                "case_id": self.case_id,
            },
        )
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["provider"], "template")
        guardrail = client.post(
            "/copilot/check-outreach",
            json={"draft": "Please contact us about your account."},
        )
        self.assertEqual(guardrail.status_code, 200)
        self.assertFalse(guardrail.json()["accepted"])
        self.assertIn("MISSING_DISPUTE_NOTICE", guardrail.json()["issues"])


if __name__ == "__main__":
    unittest.main()
