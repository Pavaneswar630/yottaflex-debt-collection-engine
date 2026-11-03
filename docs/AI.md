# Policy copilot and evaluation

The copilot explains the synthetic workflow; it does not make collection decisions. Its BM25 index is built from `config/policy.yaml`, the README, and Markdown under `docs/`. YAML rule chunks retain rule IDs as citations, while document chunks cite their file and heading. The evaluator checks the retrieved text and citation, not model-generated claims.

## Provider behavior

- Without `OPENAI_API_KEY`, `/copilot/chat` uses a deterministic local template and BM25 retrieval. No hosted model call is made.
- To opt in to the OpenAI Python SDK, install `python -m pip install -e ".[ai]"`, set `OPENAI_API_KEY`, and optionally set `YOTTAFLEX_AI_MODEL` (defaults to `gpt-4o-mini`).
- The SDK receives the question, selected case ID, retrieved policy/document excerpts, and any fixed-tool results. Enabling it sends this synthetic data and prompt to the configured provider. Do not enable it with real customer data without the required privacy, security, and legal approvals.

The only assistant tools are `get_case`, `get_score_breakdown`, `list_blocked_contacts`, and `get_promise_status`. They open query-only SQLite connections and return recorded facts; no tool can modify records, schedule a task, or contact a customer. The assistant is instructed to explain stored scores rather than produce or change them.

The case copilot displays citations, provider mode, latency, and tool names. Interaction records are appended to `reports/copilot_interactions.jsonl` by default; change the location with `YOTTAFLEX_AI_LOG_PATH`. JSONL records include the prompt, selected case ID, tool names/arguments, citations, provider, refusal state, and latency. They do not include the API key or tool-result payloads. Treat prompt logs as potentially sensitive if the UI is later connected to non-synthetic data.

## Outreach guardrails

`POST /copilot/check-outreach` and any generated draft check deterministic patterns for threatening language, third-party debt disclosure, abusive wording, and a dispute notice. A missing notice or any unsafe pattern rejects the draft. The local example notice is a safety check only; it is not a representation of a complete legal disclosure or legal advice. Review approved notices and all policy with qualified compliance counsel before any real-world use. Generated text is never scheduled or sent.

The service also refuses to draft without a case ID, or when the recorded case is not open, has a suppression rule, or has an active do-not-contact flag. Contact-window and weekly-cap checks are operational scheduling rules and remain the responsibility of the existing policy scheduler; the copilot cannot schedule a contact.

## Golden-question evaluation

Run `make eval-ai`. The 18 fixed cases verify retrieved citations and expected policy facts using the deterministic local fallback, independent of network access, API keys, and model variance. Results append to `reports/ai_evaluation.jsonl`, and the command prints the pass count/rate and exits nonzero when a case fails. The SDK path is tested with a stub client; the evaluation does not incur model costs.

The assistant must not decide scoring, contact eligibility, scheduling, suppression, dispute validity, or payment allocation. The API's domain endpoints and recorded policy decisions remain authoritative.
