"""Evaluate the deterministic retrieval/template assistant on golden questions."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Sequence

from yottaflex_debt_collection.copilot import CollectionCopilot


ROOT = Path(__file__).resolve().parents[1]


def evaluate(questions_path: Path, log_path: Path) -> tuple[int, int]:
    questions: Any = json.loads(questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"Golden-question file must contain a non-empty array: {questions_path}")
    copilot = CollectionCopilot(
        ROOT,
        ROOT / "data" / "full" / "collection.sqlite",
        log_path=log_path,
        api_key="",
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    passed = 0
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        for index, item in enumerate(questions, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Golden question {index} must be an object")
            question = item.get("question")
            expected_citations = item.get("expected_citations")
            expected_terms = item.get("expected_terms")
            if (
                not isinstance(question, str)
                or not isinstance(expected_citations, list)
                or not isinstance(expected_terms, list)
            ):
                raise ValueError(f"Golden question {index} has an invalid shape")

            started = perf_counter()
            results = copilot.knowledge.search(question, limit=4)
            citations = [result.citation for result in results]
            corpus = "\n".join(result.text for result in results).lower()
            missing_citations = [
                citation for citation in expected_citations if citation not in citations
            ]
            missing_terms = [
                term for term in expected_terms if str(term).lower() not in corpus
            ]
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            success = not missing_citations and not missing_terms
            passed += int(success)
            log.write(
                json.dumps(
                    {
                        "question_id": index,
                        "prompt": question,
                        "provider": "template",
                        "citations": citations,
                        "missing_citations": missing_citations,
                        "missing_terms": missing_terms,
                        "latency_ms": elapsed_ms,
                        "passed": success,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return passed, len(questions)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        default=ROOT / "tests" / "ai_golden_questions.json",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=ROOT / "reports" / "ai_evaluation.jsonl",
    )
    args = parser.parse_args(argv)
    passed, total = evaluate(args.questions, args.log)
    rate = passed / total if total else 0
    print(f"AI retrieval evaluation: {passed}/{total} passed ({rate:.1%})")
    print(f"JSONL report: {args.log}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
