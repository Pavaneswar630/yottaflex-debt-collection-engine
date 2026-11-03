"""Read-only FastAPI interface for generated collection datasets."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from yottaflex_debt_collection.copilot import CollectionCopilot
from yottaflex_debt_collection.database import connect_readonly
from yottaflex_debt_collection.detectors import detect
from yottaflex_debt_collection.integrity import validate_dataset_directory


ROOT = Path(__file__).resolve().parents[2]


class CopilotChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    case_id: str | None = Field(default=None, max_length=32)


class OutreachCheckRequest(BaseModel):
    draft: str = Field(min_length=1, max_length=8000)


def create_app(
    data_dir: Path | str = Path("data/full"),
    db_path: Path | str | None = None,
    ground_truth_dir: Path | str | None = None,
    policy_path: Path | str = ROOT / "config" / "policy.yaml",
    ai_log_path: Path | str | None = None,
) -> FastAPI:
    """Create the read-only API for one generated dataset."""
    data_root = Path(data_dir).resolve()
    database_path = (
        Path(db_path).resolve()
        if db_path is not None
        else (data_root / "collection.sqlite").resolve()
    )
    labels_root = (
        Path(ground_truth_dir).resolve()
        if ground_truth_dir is not None
        else (data_root.parent.parent / "ground_truth" / data_root.name).resolve()
    )
    policy_file = Path(policy_path).resolve()
    interaction_log = (
        Path(ai_log_path)
        if ai_log_path is not None
        else Path(
            os.environ.get(
                "YOTTAFLEX_AI_LOG_PATH",
                "reports/copilot_interactions.jsonl",
            )
        )
    )

    app = FastAPI(
        title="Yottaflex Debt Collection Read API",
        version="0.9.0",
        description="Read-only synthetic collection case and policy analytics API.",
    )
    app.state.data_dir = data_root
    app.state.database_path = database_path
    app.state.ground_truth_dir = labels_root
    app.state.policy_path = policy_file
    app.state.copilot = CollectionCopilot(
        ROOT,
        database_path,
        log_path=interaction_log,
    )

    def query_all(sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            connection = connect_readonly(database_path)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Dataset database is unavailable: {error}. "
                    "Load the dataset with `make db-load`."
                ),
            ) from error
        try:
            return [
                dict(row) for row in connection.execute(sql, parameters).fetchall()
            ]
        except sqlite3.Error as error:
            raise HTTPException(
                status_code=500, detail=f"Database query failed: {error}"
            ) from error
        finally:
            connection.close()

    @app.get("/health")
    def health() -> dict[str, object]:
        rows = query_all("PRAGMA quick_check")
        if not rows or rows[0].get("quick_check") != "ok":
            raise HTTPException(status_code=503, detail="SQLite quick_check failed")
        foreign_keys = query_all("PRAGMA foreign_keys")
        return {
            "status": "ok",
            "database": str(database_path),
            "foreign_keys_enabled": bool(foreign_keys[0]["foreign_keys"]),
        }

    @app.get("/queue")
    def queue(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        rows = query_all(
            """
            SELECT * FROM priority_queue
            ORDER BY priority_score DESC, case_id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        total = query_all("SELECT COUNT(*) AS count FROM priority_queue")[0]["count"]
        return {"items": rows, "limit": limit, "offset": offset, "total": total}

    @app.get("/cases/{case_id}")
    def case_detail(case_id: str) -> dict[str, object]:
        rows = query_all(
            """
            SELECT
                collection_case.*,
                loan.loan_status,
                loan.principal_amount,
                account.customer_id,
                customer.display_name,
                customer.risk_band,
                latest_snapshot.days_past_due,
                latest_snapshot.arrears_amount,
                latest_snapshot.snapshot_date
            FROM collection_case
            JOIN loan ON loan.loan_id = collection_case.loan_id
            JOIN account ON account.account_id = collection_case.account_id
            JOIN customer ON customer.customer_id = account.customer_id
            LEFT JOIN latest_snapshot
                ON latest_snapshot.loan_id = collection_case.loan_id
            WHERE collection_case.case_id = ?
            """,
            (case_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Collection case not found")
        return rows[0]

    @app.get("/cases/{case_id}/timeline")
    def case_timeline(case_id: str) -> dict[str, object]:
        if not query_all(
            "SELECT case_id FROM collection_case WHERE case_id = ?", (case_id,)
        ):
            raise HTTPException(status_code=404, detail="Collection case not found")
        rows = query_all(
            """
            SELECT
                'state_event' AS event_type,
                changed_at AS event_at,
                state_event_id AS event_id,
                new_state AS summary,
                reason_code AS detail
            FROM state_event
            WHERE case_id = ?
            UNION ALL
            SELECT
                'contact_attempt',
                attempted_at,
                contact_attempt_id,
                outcome,
                channel
            FROM contact_attempt
            WHERE case_id = ?
            UNION ALL
            SELECT
                'promise_to_pay',
                recorded_at,
                promise_id,
                status,
                CAST(promised_amount AS TEXT)
            FROM promise_to_pay
            WHERE case_id = ?
            UNION ALL
            SELECT
                'promise_payment',
                reconciliation.reconciled_at,
                reconciliation.promise_id || ':' || reconciliation.payment_id,
                reconciliation.match_status,
                CAST(reconciliation.reconciled_amount AS TEXT)
            FROM promise_reconciliation AS reconciliation
            JOIN promise_to_pay AS promise
                ON promise.promise_id = reconciliation.promise_id
            WHERE promise.case_id = ?
            ORDER BY event_at, event_type, event_id
            """,
            (case_id, case_id, case_id, case_id),
        )
        return {"case_id": case_id, "events": rows}

    @app.get("/decisions")
    def decisions(
        case_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        if case_id is None:
            rows = query_all(
                "SELECT * FROM decision_log ORDER BY created_at, decision_id LIMIT ? OFFSET ?",
                (limit, offset),
            )
            total = query_all("SELECT COUNT(*) AS count FROM decision_log")[0]["count"]
        else:
            rows = query_all(
                """
                SELECT * FROM decision_log WHERE case_id = ?
                ORDER BY created_at, decision_id LIMIT ? OFFSET ?
                """,
                (case_id, limit, offset),
            )
            total = query_all(
                "SELECT COUNT(*) AS count FROM decision_log WHERE case_id = ?",
                (case_id,),
            )[0]["count"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}

    @app.get("/exceptions")
    def exceptions(
        issue_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        detections = detect(data_root)
        if issue_type is not None:
            detections = [
                row for row in detections if row["issue_type"] == issue_type
            ]
        return {
            "items": detections[offset : offset + limit],
            "total": len(detections),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/metrics")
    def metrics() -> dict[str, object]:
        view_queries = {
            "roll_rates": "SELECT * FROM roll_rates ORDER BY from_bucket, to_bucket",
            "promise_kept_by_segment": (
                "SELECT * FROM promise_kept_by_segment ORDER BY segment"
            ),
            "cure_rate": "SELECT * FROM cure_rate",
            "violations_by_rule": (
                "SELECT * FROM violations_by_rule ORDER BY rule_id, decision_type, outcome"
            ),
        }
        return {
            name: query_all(sql) for name, sql in view_queries.items()
        } | {
            "priority_queue": {
                "open_case_count": query_all(
                    "SELECT COUNT(*) AS count FROM priority_queue"
                )[0]["count"]
            }
        }

    @app.get("/admin/policy")
    def admin_policy() -> dict[str, object]:
        if not policy_file.is_file():
            raise HTTPException(status_code=404, detail="Policy file not found")
        try:
            policy = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise HTTPException(
                status_code=500, detail=f"Policy could not be loaded: {error}"
            ) from error
        if not isinstance(policy, dict):
            raise HTTPException(status_code=500, detail="Policy root must be a mapping")
        return policy

    @app.get("/admin/validation")
    def admin_validation() -> dict[str, object]:
        result = validate_dataset_directory(data_root)
        return {
            "valid": result.valid,
            "data_dir": result.data_dir,
            "row_counts": result.row_counts,
            "checks_passed": result.checks_passed,
            "errors": result.errors,
        }

    @app.get("/admin/manifest")
    def admin_manifest() -> dict[str, object]:
        manifest_path = data_root / "manifest.json"
        if not manifest_path.is_file():
            raise HTTPException(status_code=404, detail="Dataset manifest not found")
        try:
            result = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=500, detail=f"Dataset manifest could not be loaded: {error}"
            ) from error
        if not isinstance(result, dict):
            raise HTTPException(status_code=500, detail="Manifest root must be an object")
        return result

    @app.post("/copilot/chat")
    def copilot_chat(request: CopilotChatRequest) -> dict[str, object]:
        try:
            return app.state.copilot.answer(
                request.question,
                case_id=request.case_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/copilot/check-outreach")
    def copilot_check_outreach(request: OutreachCheckRequest) -> dict[str, object]:
        return app.state.copilot.check_outreach(request.draft)

    return app


app = create_app(
    data_dir=Path(os.environ.get("YOTTAFLEX_DATA_DIR", "data/full")),
    db_path=os.environ.get("YOTTAFLEX_DB_PATH"),
    ground_truth_dir=os.environ.get("YOTTAFLEX_GROUND_TRUTH_DIR"),
)


if __name__ == "__main__":
    uvicorn.run(
        "yottaflex_debt_collection.api:app",
        host=os.environ.get("YOTTAFLEX_HOST", "127.0.0.1"),
        port=int(os.environ.get("YOTTAFLEX_PORT", "8000")),
        reload=False,
    )
