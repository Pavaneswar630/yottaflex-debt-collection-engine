import type { paths } from './api/schema'

type ApiPath = keyof paths

export interface QueueItem {
  case_id: string
  account_id: string
  loan_id: string
  status: string
  priority_score: number
  priority_tier: string
  balance_component: number
  age_component: number
  risk_component: number
  reason_codes: string
  suppression_rule_id: string | null
  next_action_at: string | null
  days_past_due: number | null
  arrears_amount: number | null
  snapshot_date: string | null
}

export interface QueueResponse {
  items: QueueItem[]
  limit: number
  offset: number
  total: number
}

export interface CaseDetail extends QueueItem {
  opened_at: string
  closed_at: string | null
  scored_at: string
  customer_id: string
  display_name: string
  risk_band: string
  loan_status: string
  principal_amount: number
  snapshot_date: string | null
}

export interface TimelineEvent {
  event_type: string
  event_at: string
  event_id: string
  summary: string
  detail: string | null
}

export interface TimelineResponse {
  case_id: string
  events: TimelineEvent[]
}

export interface ExceptionItem {
  issue_type: string
  entity_type: string
  entity_id: string
  rule_id: string
  evidence: string
}

export interface ExceptionResponse {
  items: ExceptionItem[]
  total: number
  limit: number
  offset: number
}

export interface MetricsResponse {
  roll_rates: Array<{
    from_bucket: string
    to_bucket: string
    loan_transitions: number
  }>
  promise_kept_by_segment: Array<{
    segment: string
    promise_count: number
    kept_count: number
    kept_rate: number
  }>
  cure_rate: Array<{
    delinquent_loans: number
    cured_loans: number
    cure_rate: number
  }>
  violations_by_rule: Array<{
    rule_id: string
    decision_type: string
    outcome: string
    decision_count: number
  }>
  priority_queue: { open_case_count: number }
}

export interface HealthResponse {
  status: string
  database: string
  foreign_keys_enabled: boolean
}

export interface ValidationResponse {
  valid: boolean
  data_dir: string
  row_counts: Record<string, number>
  checks_passed: number
  errors: string[]
}

export interface ManifestResponse {
  dataset: string
  seed: number
  generation_date: string
  as_of_date: string
  loans: number
  row_counts: Record<string, number>
  source: { type: string; external_data_used: boolean }
  files: Record<string, string>
}

export interface CopilotResponse {
  answer: string
  refused: boolean
  citations: string[]
  tools_used: string[]
  provider: 'template' | 'openai'
  latency_ms: number
}

export interface PolicyResponse {
  policy_version: number
  description: string
  rules: Record<string, { desc: string; [key: string]: unknown }>
  suppression: {
    first_match_order: string[]
    disposition: Record<string, string>
  }
  scoring: {
    w_balance: number
    w_age: number
    w_risk: number
    tiers: { p1_min_score: number; p2_min_score: number }
    formula: string
  }
}

async function getJson<T>(contractPath: ApiPath, requestPath: string): Promise<T> {
  const response = await fetch(`/api${requestPath}`)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(`${contractPath}: ${message}`)
  }
  return (await response.json()) as T
}

export const api = {
  queue(limit = 100, offset = 0) {
    return getJson<QueueResponse>(
      '/queue',
      `/queue?limit=${limit}&offset=${offset}`,
    )
  },
  caseDetail(caseId: string) {
    return getJson<CaseDetail>(
      '/cases/{case_id}',
      `/cases/${encodeURIComponent(caseId)}`,
    )
  },
  timeline(caseId: string) {
    return getJson<TimelineResponse>(
      '/cases/{case_id}/timeline',
      `/cases/${encodeURIComponent(caseId)}/timeline`,
    )
  },
  exceptions(limit = 1000) {
    return getJson<ExceptionResponse>('/exceptions', `/exceptions?limit=${limit}`)
  },
  metrics() {
    return getJson<MetricsResponse>('/metrics', '/metrics')
  },
  health() {
    return getJson<HealthResponse>('/health', '/health')
  },
  validation() {
    return getJson<ValidationResponse>('/admin/validation', '/admin/validation')
  },
  manifest() {
    return getJson<ManifestResponse>('/admin/manifest', '/admin/manifest')
  },
  policy() {
    return getJson<PolicyResponse>('/admin/policy', '/admin/policy')
  },
  copilot(question: string, caseId: string) {
    return fetch('/api/copilot/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, case_id: caseId }),
    }).then(async (response) => {
      if (!response.ok) {
        let message = `Request failed (${response.status})`
        try {
          const body = (await response.json()) as { detail?: string }
          if (body.detail) message = body.detail
        } catch {
          // Keep the HTTP status message when the server does not return JSON.
        }
        throw new Error(`/copilot/chat: ${message}`)
      }
      return (await response.json()) as CopilotResponse
    })
  },
}
