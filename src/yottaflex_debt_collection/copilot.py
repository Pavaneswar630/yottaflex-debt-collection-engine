"""Grounded policy assistance with fixed read-only data tools."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from time import perf_counter
from typing import Any

from yottaflex_debt_collection.database import connect_readonly
from yottaflex_debt_collection.guardrails import (
    inspect_unsafe_request,
    validate_outreach_draft,
)
from yottaflex_debt_collection.knowledge import PolicyKnowledgeIndex, SearchResult


_LOG_LOCK = threading.Lock()
_CASE_ID_PATTERN = re.compile(r"\bCOL-\d{4}-\d{6}\b", re.IGNORECASE)
_OUTREACH_PATTERN = re.compile(
    r"\b(?:draft|write|compose|create|generate)\b.{0,80}"
    r"\b(?:message|email|letter|text|outreach|reminder)\b",
    re.IGNORECASE,
)

SYSTEM_INSTRUCTIONS = """You are a read-only assistant for a synthetic debt-collection workflow.
Use only retrieved policy/document excerpts and the four supplied read-only tools.
Never make or alter a score, priority, suppression, contact-window, contact-scheduling,
payment-allocation, or compliance decision. Explain recorded values; do not authorize
contact, claim a debt is legally valid, or disclose debt to another person. Cite policy
rule IDs or document citations supplied in context. If facts are missing, say so.
When drafting outreach, use calm, non-coercive language and include the exact sentence
"If you believe this debt is inaccurate, you may dispute it." Never threaten, shame,
or suggest contacting third parties. Any draft is text only, not a scheduled or sent contact."""

TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "get_case",
            "description": "Read one case and its current loan, account, customer risk, and restriction facts.",
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_score_breakdown",
            "description": "Read stored priority components and calculate their displayed weighted contributions.",
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_blocked_contacts",
            "description": "List recorded blocked-contact decisions without scheduling or sending contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_promise_status",
            "description": "Read promise outcomes and reconciled payment totals for one case.",
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
                "additionalProperties": False,
            },
        },
    },
)
_ALLOWED_TOOL_NAMES = frozenset(
    definition["function"]["name"] for definition in TOOL_DEFINITIONS
)


def _read_case(connection: Any, case_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            collection_case.case_id,
            collection_case.account_id,
            collection_case.loan_id,
            collection_case.status,
            collection_case.opened_at,
            collection_case.priority_score,
            collection_case.priority_tier,
            collection_case.reason_codes,
            collection_case.suppression_rule_id,
            loan.loan_status,
            account.hardship_status,
            customer.risk_band,
            latest_snapshot.days_past_due,
            latest_snapshot.arrears_amount,
            latest_snapshot.dispute_status,
            contact_preference.do_not_contact
        FROM collection_case
        JOIN loan ON loan.loan_id = collection_case.loan_id
        JOIN account ON account.account_id = collection_case.account_id
        JOIN customer ON customer.customer_id = account.customer_id
        LEFT JOIN latest_snapshot
            ON latest_snapshot.loan_id = collection_case.loan_id
        LEFT JOIN contact_preference
            ON contact_preference.account_id = collection_case.account_id
        WHERE collection_case.case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Collection case not found: {case_id}")
    result = dict(row)
    result["citations"] = ["R-CASE-01", "R-PAIDOFF-01", "R-DISPUTE-01"]
    return result


def _read_score_breakdown(connection: Any, case_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            case_id,
            priority_score,
            priority_tier,
            balance_component,
            age_component,
            risk_component,
            reason_codes
        FROM collection_case
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Collection case not found: {case_id}")
    record = dict(row)
    weights = {"balance": 0.40, "age": 0.35, "risk": 0.25}
    components = {
        "balance": float(record["balance_component"]),
        "age": float(record["age_component"]),
        "risk": float(record["risk_component"]),
    }
    return {
        "case_id": record["case_id"],
        "priority_score": record["priority_score"],
        "priority_tier": record["priority_tier"],
        "components": components,
        "weights": weights,
        "weighted_points": {
            name: round(100 * value * weights[name], 2)
            for name, value in components.items()
        },
        "reason_codes": record["reason_codes"],
        "citations": ["R-SCORE-01"],
    }


def _read_blocked_contacts(connection: Any, limit: int) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 50))
    rows = connection.execute(
        """
        SELECT
            decision_id,
            case_id,
            loan_id,
            rule_id,
            decision_type,
            outcome,
            reason,
            as_of_date
        FROM decision_log
        WHERE outcome = 'block' OR decision_type = 'contact_blocked'
        ORDER BY as_of_date DESC, decision_id
        LIMIT ?
        """,
        (bounded_limit,),
    ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "limit": bounded_limit,
        "citations": ["R-CONTACT-01", "R-CONTACT-02"],
    }


def _read_promise_status(connection: Any, case_id: str) -> dict[str, Any]:
    if connection.execute(
        "SELECT 1 FROM collection_case WHERE case_id = ?", (case_id,)
    ).fetchone() is None:
        raise ValueError(f"Collection case not found: {case_id}")
    rows = connection.execute(
        """
        SELECT
            promise.promise_id,
            promise.promised_amount,
            promise.promised_date,
            promise.status,
            promise.recorded_at,
            promise.resolved_at,
            COALESCE(SUM(reconciliation.reconciled_amount), 0)
                AS reconciled_amount,
            COUNT(reconciliation.payment_id) AS matched_payment_count
        FROM promise_to_pay AS promise
        LEFT JOIN promise_reconciliation AS reconciliation
            ON reconciliation.promise_id = promise.promise_id
        WHERE promise.case_id = ?
        GROUP BY promise.promise_id
        ORDER BY promise.recorded_at, promise.promise_id
        """,
        (case_id,),
    ).fetchall()
    return {
        "case_id": case_id,
        "promises": [dict(row) for row in rows],
        "citations": ["R-PROMISE-01", "R-RECON-01"],
    }


class ReadOnlyCollectionTools:
    """The only database tools exposed to the assistant."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in _ALLOWED_TOOL_NAMES:
            raise ValueError(f"Unsupported assistant tool: {name}")
        if name in {"get_case", "get_score_breakdown", "get_promise_status"}:
            case_id = arguments.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{name} requires a non-empty case_id")
        if name == "list_blocked_contacts":
            limit = arguments.get("limit", 20)
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise ValueError("list_blocked_contacts limit must be an integer")
        with closing(connect_readonly(self.database_path)) as connection:
            if name == "get_case":
                return _read_case(connection, case_id)
            if name == "get_score_breakdown":
                return _read_score_breakdown(connection, case_id)
            if name == "list_blocked_contacts":
                return _read_blocked_contacts(connection, arguments.get("limit", 20))
            return _read_promise_status(connection, case_id)


def _is_outreach_request(question: str) -> bool:
    return bool(_OUTREACH_PATTERN.search(question))


def _fallback_tool_names(question: str, case_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    normalized = question.lower()
    resolved_case_id = case_id
    if resolved_case_id is None:
        match = _CASE_ID_PATTERN.search(question)
        if match:
            resolved_case_id = match.group(0).upper()
    calls: list[tuple[str, dict[str, Any]]] = []
    if re.search(r"\b(blocked|blocked contact|contact restriction|contact window)\b", normalized):
        calls.append(("list_blocked_contacts", {"limit": 10}))
    if resolved_case_id:
        if re.search(r"\b(score|priority|tier|rank)\b", normalized):
            calls.append(("get_score_breakdown", {"case_id": resolved_case_id}))
        elif re.search(r"\b(promise|promised|commitment|payment status|kept|broken)\b", normalized):
            calls.append(("get_promise_status", {"case_id": resolved_case_id}))
        elif not calls:
            calls.append(("get_case", {"case_id": resolved_case_id}))
    return calls


def _snippet(text: str, maximum: int = 480) -> str:
    flattened = " ".join(text.split())
    return flattened if len(flattened) <= maximum else flattened[: maximum - 1].rstrip() + "…"


def _format_tool_result(name: str, result: dict[str, Any]) -> str:
    if name == "get_score_breakdown":
        points = result["weighted_points"]
        return (
            f"Recorded score: {result['priority_score']} ({result['priority_tier']}). "
            f"Weighted points: balance {points['balance']}, age {points['age']}, "
            f"risk {points['risk']}. Reason codes: {result['reason_codes']}."
        )
    if name == "get_case":
        return (
            f"Case {result['case_id']} is {result['status']}; loan status "
            f"{result['loan_status']}; DPD {result['days_past_due']}; arrears "
            f"{result['arrears_amount']} cents; suppression rule "
            f"{result['suppression_rule_id'] or 'none'}; do-not-contact "
            f"{bool(result['do_not_contact'])}."
        )
    if name == "get_promise_status":
        if not result["promises"]:
            return f"No promise records are available for case {result['case_id']}."
        return "Promise records: " + "; ".join(
            f"{row['promise_id']} status {row['status']}, amount "
            f"{row['promised_amount']} cents, reconciled "
            f"{row['reconciled_amount']} cents"
            for row in result["promises"]
        )
    items = result["items"]
    if not items:
        return "No blocked-contact decisions were found in the records queried."
    return "Recorded blocked-contact decisions: " + "; ".join(
        f"{row['case_id']} via {row['rule_id']} ({row['reason']})"
        for row in items[:5]
    )


class CollectionCopilot:
    """Retrieval-augmented policy assistant with optional OpenAI SDK access."""

    def __init__(
        self,
        repository_root: Path | str,
        database_path: Path | str,
        *,
        log_path: Path | str = Path("reports/copilot_interactions.jsonl"),
        api_key: str | None = None,
        model: str | None = None,
        client_factory: Any | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.database_path = Path(database_path)
        self.log_path = Path(log_path)
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("YOTTAFLEX_AI_MODEL", "gpt-4o-mini")
        self.client_factory = client_factory
        self.knowledge = PolicyKnowledgeIndex(self.repository_root)
        self.tools = ReadOnlyCollectionTools(self.database_path)

    def answer(
        self,
        question: str,
        *,
        case_id: str | None = None,
        force_template: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        results = self.knowledge.search(question, limit=4)
        citations = list(dict.fromkeys(result.citation for result in results))
        provider = "template" if force_template or not self.api_key else "openai"
        tool_calls: list[dict[str, Any]] = []
        try:
            unsafe_issues = inspect_unsafe_request(question)
            if unsafe_issues:
                response = {
                    "answer": (
                        "I can’t help create threatening, abusive, or third-party "
                        "debt disclosures. I can explain the documented policy instead."
                    ),
                    "refused": True,
                }
            elif _is_outreach_request(question):
                resolved_case_id = case_id
                if resolved_case_id is None:
                    match = _CASE_ID_PATTERN.search(question)
                    resolved_case_id = match.group(0).upper() if match else None
                if resolved_case_id is None:
                    response = {
                        "answer": (
                            "I can’t draft case-specific outreach without first "
                            "checking the account’s contact restrictions and "
                            "suppression status."
                        ),
                        "refused": True,
                    }
                else:
                    case = self.tools.invoke(
                        "get_case", {"case_id": resolved_case_id}
                    )
                    arguments = {"case_id": resolved_case_id}
                    tool_calls.append({"name": "get_case", "arguments": arguments})
                    citations = list(
                        dict.fromkeys(citations + case["citations"])
                    )
                    if (
                        case["suppression_rule_id"]
                        or case["status"] != "open"
                        or bool(case["do_not_contact"])
                    ):
                        response = {
                            "answer": (
                                "I can’t draft outreach for this case because the "
                                "recorded case status or contact restriction requires "
                                "suppression or review. Follow the applicable review "
                                "process; no contact was scheduled or sent."
                            ),
                            "refused": True,
                        }
                    elif provider == "openai":
                        answer_text, model_tool_calls, tool_citations = (
                            self._openai_answer(
                                question,
                                resolved_case_id,
                                results,
                                case_context=case,
                            )
                        )
                        tool_calls.extend(model_tool_calls)
                        citations = list(dict.fromkeys(citations + tool_citations))
                        guardrail = validate_outreach_draft(answer_text)
                        response = (
                            {"answer": answer_text, "refused": False}
                            if guardrail.accepted
                            else self._outreach_refusal(guardrail.issues)
                        )
                    else:
                        answer_text = self._outreach_template_draft()
                        guardrail = validate_outreach_draft(answer_text)
                        response = (
                            {"answer": answer_text, "refused": False}
                            if guardrail.accepted
                            else self._outreach_refusal(guardrail.issues)
                        )
            elif provider == "openai":
                answer_text, tool_calls, tool_citations = self._openai_answer(
                    question, case_id, results
                )
                citations = list(dict.fromkeys(citations + tool_citations))
                response = {"answer": answer_text, "refused": False}
            else:
                answer_text, tool_calls, tool_citations = self._template_answer(
                    question, case_id, results
                )
                citations = list(dict.fromkeys(citations + tool_citations))
                response = {"answer": answer_text, "refused": False}
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "model": self.model if provider == "openai" else None,
                "prompt": question,
                "case_id": case_id,
                "tool_calls": tool_calls,
                "citations": citations,
                "latency_ms": elapsed_ms,
                "refused": response["refused"],
            }
            self._append_log(record)
            return {
                **response,
                "citations": citations,
                "tools_used": [call["name"] for call in tool_calls],
                "provider": provider,
                "latency_ms": elapsed_ms,
            }
        except Exception as error:
            self._append_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": provider,
                    "model": self.model if provider == "openai" else None,
                    "prompt": question,
                    "case_id": case_id,
                    "tool_calls": tool_calls,
                    "citations": citations,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "error": str(error),
                }
            )
            raise

    def check_outreach(self, draft: str) -> dict[str, Any]:
        result = validate_outreach_draft(draft)
        self._append_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": "guardrail",
                "prompt": draft,
                "tool_calls": [],
                "latency_ms": 0,
                "accepted": result.accepted,
                "guardrail_issues": list(result.issues),
            }
        )
        return {"accepted": result.accepted, "issues": list(result.issues)}

    def _template_answer(
        self,
        question: str,
        case_id: str | None,
        results: list[SearchResult],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        tool_calls: list[dict[str, Any]] = []
        tool_citations: list[str] = []
        tool_summaries: list[str] = []
        for name, arguments in _fallback_tool_names(question, case_id):
            result = self.tools.invoke(name, arguments)
            tool_calls.append({"name": name, "arguments": arguments})
            tool_citations.extend(result["citations"])
            tool_summaries.append(_format_tool_result(name, result))

        if not results:
            answer = (
                "I couldn’t find matching guidance in the indexed policy and "
                "documentation. No collection decision was made."
            )
        else:
            guidance = "\n".join(
                f"- {_snippet(result.text)} {result.citation}"
                for result in results[:3]
            )
            answer = (
                "Based on the documented synthetic workflow:\n"
                f"{guidance}\n"
                "These sources explain policy; they do not authorize contact or "
                "change a recorded decision."
            )
        if tool_summaries:
            answer += "\n\nRecorded case data:\n" + "\n".join(
                f"- {summary}" for summary in tool_summaries
            )
        return answer, tool_calls, tool_citations

    @staticmethod
    def _outreach_template_draft() -> str:
        return (
            "Suggested neutral draft (text only; not scheduled or sent):\n\n"
            "Hello, we’re reaching out regarding your account. If you would like "
            "to discuss available options, please use your established, secure "
            "account channel. If you believe this debt is inaccurate, you may "
            "dispute it.\n\n"
            "Check the applicable contact window and preferences before any "
            "separate contact decision."
        )

    def _openai_answer(
        self,
        question: str,
        case_id: str | None,
        results: list[SearchResult],
        *,
        case_context: dict[str, Any] | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        client = self._make_openai_client()
        context = "\n\n".join(
            f"{result.citation} {result.text}" for result in results
        ) or "No matching policy/document excerpts were found."
        selected_case = f"\nSelected case ID: {case_id}" if case_id else ""
        if case_context is not None:
            selected_case += (
                "\nPrechecked case facts: "
                + json.dumps(case_context, sort_keys=True)
            )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    f"Question: {question}{selected_case}\n\n"
                    f"Retrieved policy/document context:\n{context}"
                ),
            },
        ]
        tool_calls: list[dict[str, Any]] = []
        tool_citations: list[str] = []
        for _ in range(4):
            completion = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=list(TOOL_DEFINITIONS),
                tool_choice="auto",
                temperature=0,
                max_tokens=700,
            )
            message = completion.choices[0].message
            if not message.tool_calls:
                if not message.content:
                    raise RuntimeError("AI SDK returned neither text nor tool calls")
                return message.content, tool_calls, tool_citations
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                name = call.function.name
                if name not in _ALLOWED_TOOL_NAMES:
                    raise ValueError(f"AI SDK requested an unsupported tool: {name}")
                arguments = json.loads(call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError(f"AI SDK arguments for {name} must be an object")
                if name in {"get_case", "get_score_breakdown", "get_promise_status"}:
                    arguments.setdefault("case_id", case_id)
                result = self.tools.invoke(name, arguments)
                tool_calls.append({"name": name, "arguments": arguments})
                tool_citations.extend(result["citations"])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, sort_keys=True),
                    }
                )
        raise RuntimeError("AI SDK exceeded the maximum of four tool-call rounds")

    def _make_openai_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory(api_key=self.api_key, timeout=30, max_retries=1)
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "OPENAI_API_KEY is set but the optional OpenAI SDK is not installed; "
                "install with `python -m pip install -e \".[ai]\"`."
            ) from error
        return OpenAI(api_key=self.api_key, timeout=30, max_retries=1)

    @staticmethod
    def _outreach_refusal(issues: tuple[str, ...]) -> dict[str, Any]:
        labels = {
            "THREATENING_LANGUAGE": "threatening language",
            "THIRD_PARTY_DISCLOSURE": "third-party disclosure",
            "ABUSIVE_LANGUAGE": "abusive wording",
            "MISSING_DISPUTE_NOTICE": "the required dispute notice is missing",
        }
        reasons = ", ".join(labels[issue] for issue in issues)
        return {
            "answer": (
                f"I can’t provide that outreach draft because it failed a safety "
                f"check ({reasons}). Review the communication with an authorized "
                "compliance reviewer."
            ),
            "refused": True,
        }

    def _append_log(self, record: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(record, sort_keys=True, ensure_ascii=True)
        with _LOG_LOCK:
            with self.log_path.open("a", encoding="utf-8", newline="\n") as output:
                output.write(serialized + "\n")
