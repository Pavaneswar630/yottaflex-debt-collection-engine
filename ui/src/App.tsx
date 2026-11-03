import { useEffect, useMemo, useState } from 'react'
import type {
  CaseDetail,
  ExceptionItem,
  QueueItem,
  TimelineEvent,
} from './api'
import { api } from './api'

type Screen = 'queue' | 'case' | 'compliance' | 'admin'
function useResource<T>(loader: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    loader()
      .then((result) => {
        if (active) setData(result)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'Unexpected API error')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
    // The dependency list is intentionally controlled by each screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, refreshKey])

  return { data, error, loading, refresh: () => setRefreshKey((key) => key + 1) }
}

function formatCurrency(cents: number | null | undefined) {
  if (cents === null || cents === undefined) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(cents / 100)
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function scoreReasonCodes(value: string): string[] {
  try {
    const parsed: unknown = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.filter((item): item is string => typeof item === 'string')
  } catch {
    return value.split(/[|,;]/).map((part) => part.trim()).filter(Boolean)
  }
  return []
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

function App() {
  const [screen, setScreen] = useState<Screen>('queue')
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)

  function openCase(caseId: string) {
    setSelectedCaseId(caseId)
    setScreen('case')
  }

  const title = screen === 'case' ? 'Case details' : screen === 'queue' ? 'Priority queue' : screen === 'compliance' ? 'Compliance & outcomes' : 'System administration'
  const subtitle = screen === 'queue'
    ? 'A clear, policy-aware view of accounts that need attention.'
    : screen === 'case'
      ? 'Understand the score, history and next permissible action.'
      : screen === 'compliance'
        ? 'Monitor exceptions and outcome measures without losing traceability.'
        : 'Inspect the dataset, policy and service health.'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span>Y</span></div>
          <div><strong>yottaflex</strong><small>COLLECTIONS INTELLIGENCE</small></div>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <div className="workspace-card">
          <span className="workspace-dot" />
          <div><strong>Operations</strong><small>Synthetic portfolio</small></div>
          <span className="chevron">⌄</span>
        </div>
        <nav className="navigation" aria-label="Main navigation">
          <div className="nav-caption">WORKSPACE</div>
          <NavButton active={screen === 'queue' || screen === 'case'} icon="▤" label="Priority queue" onClick={() => setScreen('queue')} />
          <NavButton active={screen === 'compliance'} icon="◈" label="Compliance & metrics" onClick={() => setScreen('compliance')} />
          <div className="nav-caption nav-caption-spaced">MANAGE</div>
          <NavButton active={screen === 'admin'} icon="⚙" label="Administration" onClick={() => setScreen('admin')} />
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon">i</div>
            <strong>Built for thoughtful collections</strong>
            <p>Every decision is explainable. Contact restrictions always come first.</p>
            <span>POLICY-FIRST WORKFLOW</span>
          </div>
          <div className="profile">
            <div className="profile-avatar">OA</div>
            <div><strong>Operations analyst</strong><small>Read-only workspace</small></div>
            <span className="more">···</span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><i>/</i><strong>{title}</strong></div>
          <div className="topbar-actions">
            <div className="read-only"><span /> Read-only</div>
            <div className="today-label"><span className="calendar-icon">▦</span> As of Oct 31, 2026</div>
            <div className="top-avatar">OA</div>
          </div>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">COLLECTION OPERATIONS</div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            <div className="heading-actions">
              <span className="synthetic-tag"><span /> Synthetic data</span>
              {screen === 'case' && <button className="button button-secondary" onClick={() => setScreen('queue')}>← Back to queue</button>}
            </div>
          </div>
          {screen === 'queue' && <QueueScreen onOpenCase={openCase} />}
          {screen === 'case' && <CaseScreen caseId={selectedCaseId} onBack={() => setScreen('queue')} />}
          {screen === 'compliance' && <ComplianceScreen onOpenCase={openCase} />}
          {screen === 'admin' && <AdminScreen />}
          <footer className="page-footer">
            <span>Yottaflex collections intelligence</span>
            <span>Thoughtful engagement. Clear decisions.</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

function NavButton({ active, icon, label, onClick }: { active: boolean; icon: string; label: string; onClick: () => void }) {
  return <button className={`nav-item${active ? ' active' : ''}`} onClick={onClick}><span className="nav-icon">{icon}</span><span>{label}</span>{active && <span className="nav-active-mark" />}</button>
}

function QueueScreen({ onOpenCase }: { onOpenCase: (caseId: string) => void }) {
  const [offset, setOffset] = useState(0)
  const [tier, setTier] = useState('All priorities')
  const [search, setSearch] = useState('')
  const queue = useResource(() => api.queue(100, offset), [offset])
  const items = queue.data?.items ?? []
  const filtered = useMemo(() => items.filter((item) => {
    const matchesTier = tier === 'All priorities' || item.priority_tier === tier
    const matchesSearch = `${item.case_id} ${item.account_id} ${item.loan_id}`.toLowerCase().includes(search.toLowerCase())
    return matchesTier && matchesSearch
  }), [items, search, tier])
  const p1Count = items.filter((item) => item.priority_tier === 'P1').length
  const showingFrom = queue.data && queue.data.total > 0 ? queue.data.offset + 1 : 0
  const showingTo = Math.min(offset + 100, queue.data?.total ?? 0)

  return (
    <>
      <section className="stat-grid">
        <StatCard label="Open cases" value={queue.loading ? '—' : (queue.data?.total ?? 0).toLocaleString()} note="Current priority queue" icon="▤" tone="blue" />
        <StatCard label="P1 priority" value={queue.loading ? '—' : p1Count.toLocaleString()} note="On this page" icon="↗" tone="amber" />
        <StatCard label="Portfolio review" value="Policy-led" note="Restrictions checked first" icon="◈" tone="green" />
      </section>
      <section className="panel queue-panel">
        <div className="panel-heading">
          <div><div className="section-title">Accounts needing attention</div><div className="section-subtitle">Ranked by explainable balance, age and risk signals</div></div>
          <button className="button button-secondary" onClick={queue.refresh} disabled={queue.loading}><span className="refresh-glyph">↻</span> Refresh</button>
        </div>
        <div className="table-toolbar">
          <label className="search-field"><span>⌕</span><input aria-label="Search cases" placeholder="Search by case, account or loan..." value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <label className="select-field"><span className="filter-glyph">☷</span><select aria-label="Filter by priority" value={tier} onChange={(event) => setTier(event.target.value)}><option>All priorities</option><option>P1</option><option>P2</option><option>P3</option></select></label>
        </div>
        {queue.loading && <LoadingState label="Loading the priority queue…" />}
        {queue.error && <ErrorState message={queue.error} onRetry={queue.refresh} />}
        {queue.data && (
          <>
            <div className="table-scroll">
              <table className="data-table queue-table">
                <thead><tr><th>CASE / ACCOUNT</th><th>PRIORITY</th><th>DPD</th><th>ARREARS</th><th>SCORE</th><th>REASONS</th><th>NEXT ACTION</th><th /></tr></thead>
                <tbody>
                  {filtered.map((item) => <QueueRow key={item.case_id} item={item} onClick={() => onOpenCase(item.case_id)} />)}
                  {filtered.length === 0 && <tr><td colSpan={8} className="empty-cell">No cases match these filters.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="table-foot">
              <span>Showing <strong>{showingFrom}–{showingTo}</strong> of <strong>{queue.data.total.toLocaleString()}</strong> open cases</span>
              <div className="pagination">
                <button aria-label="Previous page" disabled={offset === 0 || queue.loading} onClick={() => setOffset(Math.max(0, offset - 100))}>←</button>
                <span>Page {Math.floor(offset / 100) + 1}</span>
                <button aria-label="Next page" disabled={offset + 100 >= queue.data.total || queue.loading} onClick={() => setOffset(offset + 100)}>→</button>
              </div>
            </div>
          </>
        )}
      </section>
      <section className="quiet-note"><span className="note-icon">✓</span><div><strong>Policy-led prioritization</strong><span>Suppression and contact restrictions are evaluated before any task can be scheduled. This queue is read-only.</span></div></section>
    </>
  )
}

function QueueRow({ item, onClick }: { item: QueueItem; onClick: () => void }) {
  const reasons = scoreReasonCodes(item.reason_codes)
  return (
    <tr className="clickable-row" onClick={onClick} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onClick() }} tabIndex={0}>
      <td><div className="primary-cell">{item.case_id}</div><div className="secondary-cell">{item.account_id}</div></td>
      <td><TierBadge tier={item.priority_tier} /></td>
      <td><span className="dpd-value">{item.days_past_due ?? '—'} <small>days</small></span></td>
      <td className="money-cell">{formatCurrency(item.arrears_amount)}</td>
      <td><div className="score-cell"><div className="score-track"><span style={{ width: `${Math.min(100, item.priority_score)}%` }} /></div><strong>{Number(item.priority_score).toFixed(1)}</strong></div></td>
      <td><div className="reason-chips">{reasons.slice(0, 2).map((reason) => <span className="reason-chip" key={reason}>{reason.replaceAll('_', ' ')}</span>)}{reasons.length > 2 && <span className="more-reasons">+{reasons.length - 2}</span>}</div></td>
      <td><span className="date-cell">{formatDate(item.next_action_at)}</span></td>
      <td><button className="row-arrow" aria-label={`View ${item.case_id}`}>→</button></td>
    </tr>
  )
}

function CaseScreen({ caseId, onBack }: { caseId: string | null; onBack: () => void }) {
  const detail = useResource(() => caseId ? api.caseDetail(caseId) : Promise.reject(new Error('Choose a case from the queue first.')), [caseId])
  const timeline = useResource(() => caseId ? api.timeline(caseId) : Promise.resolve({ case_id: '', events: [] }), [caseId])

  if (!caseId) return <ErrorState message="Select a case from the priority queue to review its details." onRetry={onBack} />
  if (detail.loading || timeline.loading) return <LoadingState label="Loading case history…" />
  if (detail.error) return <ErrorState message={detail.error} onRetry={detail.refresh} />
  if (timeline.error) return <ErrorState message={timeline.error} onRetry={timeline.refresh} />
  if (!detail.data || !timeline.data) return null

  return <CaseDetailView detail={detail.data} events={timeline.data.events} />
}

function CaseDetailView({ detail, events }: { detail: CaseDetail; events: TimelineEvent[] }) {
  const reasons = scoreReasonCodes(detail.reason_codes)
  const scoreParts = [
    { label: 'Balance', value: detail.balance_component, weight: 0.4, color: 'var(--blue)' },
    { label: 'Delinquency age', value: detail.age_component, weight: 0.35, color: 'var(--amber)' },
    { label: 'Customer risk', value: detail.risk_component, weight: 0.25, color: 'var(--green)' },
  ]
  return (
    <>
      <section className="case-hero panel">
        <div className="case-identity">
          <div className="customer-avatar">{initials(detail.display_name)}</div>
          <div><div className="eyebrow">COLLECTION CASE</div><h2>{detail.display_name}</h2><p>{detail.case_id} <span>·</span> {detail.account_id} <span>·</span> {detail.loan_id}</p></div>
        </div>
        <div className="case-hero-status"><TierBadge tier={detail.priority_tier} /><span className="status-pill status-open">{detail.status}</span></div>
      </section>
      <div className="detail-grid">
        <div className="detail-main">
          <section className="panel score-panel">
            <div className="panel-heading"><div><div className="section-title">Priority score</div><div className="section-subtitle">Transparent weighted components · {formatDate(detail.scored_at)}</div></div><div className="big-score">{Number(detail.priority_score).toFixed(1)}<small>/100</small></div></div>
            <div className="score-bar-large"><span style={{ width: `${Math.min(100, detail.priority_score)}%` }} /></div>
            <div className="score-breakdown">{scoreParts.map((part) => <div className="score-part" key={part.label}><div className="score-part-top"><span><i style={{ background: part.color }} />{part.label}</span><strong>{(part.value * part.weight * 100).toFixed(1)}<small> pts</small></strong></div><div className="score-part-track"><span style={{ width: `${Math.max(0, Math.min(100, part.value * 100))}%`, background: part.color }} /></div><small>{(part.value * 100).toFixed(0)}% component × {part.weight.toFixed(2)} weight</small></div>)}</div>
            <div className="formula-note">Score = 100 × (0.40 × balance + 0.35 × age + 0.25 × risk)</div>
          </section>
          <section className="panel">
            <div className="panel-heading"><div><div className="section-title">Case timeline</div><div className="section-subtitle">Recorded events and commitment outcomes</div></div><span className="event-count">{events.length} events</span></div>
            {events.length ? <Timeline events={events} /> : <div className="empty-state">No timeline events have been recorded for this case.</div>}
          </section>
        </div>
        <aside className="detail-side">
          <section className="panel overview-panel">
            <div className="section-title">Account overview</div>
            <div className="overview-row"><span>Current arrears</span><strong>{formatCurrency(detail.arrears_amount)}</strong></div>
            <div className="overview-row"><span>Days past due</span><strong>{detail.days_past_due ?? '—'} days</strong></div>
            <div className="overview-row"><span>Customer risk</span><strong className="capitalize">{detail.risk_band.replaceAll('_', ' ')}</strong></div>
            <div className="overview-row"><span>Loan status</span><strong className="capitalize">{detail.loan_status.replaceAll('_', ' ')}</strong></div>
            <div className="overview-row"><span>Principal</span><strong>{formatCurrency(detail.principal_amount)}</strong></div>
            <div className="overview-row"><span>Case opened</span><strong>{formatDate(detail.opened_at)}</strong></div>
          </section>
          <section className="panel">
            <div className="section-title">Reason codes</div>
            <div className="reason-list">{reasons.map((reason) => <div className="reason-list-item" key={reason}><span>✓</span><div><strong>{reason.replaceAll('_', ' ')}</strong><small>Contributed to this prioritization</small></div></div>)}</div>
          </section>
          <div className="compliance-callout"><span>◈</span><div><strong>Respectful engagement</strong><p>All contact decisions are subject to local-time windows, preferences, weekly caps and suppression rules.</p></div></div>
        </aside>
      </div>
    </>
  )
}

function Timeline({ events }: { events: TimelineEvent[] }) {
  return <ol className="timeline">{events.map((event) => <li className="timeline-item" key={`${event.event_type}-${event.event_id}`}><div className={`timeline-marker marker-${event.event_type.replaceAll('_', '-')}`}><TimelineIcon type={event.event_type} /></div><div className="timeline-content"><div className="timeline-top"><strong>{event.summary.replaceAll('_', ' ')}</strong><time>{formatDate(event.event_at)} <span>{new Date(event.event_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></time></div><div className="timeline-kind">{event.event_type.replaceAll('_', ' ')}</div>{event.detail && <div className="timeline-detail">{event.detail}</div>}</div></li>)}</ol>
}

function TimelineIcon({ type }: { type: string }) {
  const icon = type === 'contact_attempt' ? '↗' : type === 'promise_to_pay' ? '$' : type === 'promise_payment' ? '✓' : '◷'
  return <span aria-hidden="true">{icon}</span>
}

function ComplianceScreen({ onOpenCase }: { onOpenCase: (caseId: string) => void }) {
  const exceptions = useResource(() => api.exceptions(1000))
  const metrics = useResource(() => api.metrics())
  const [filter, setFilter] = useState('All exception types')
  const [query, setQuery] = useState('')
  const allExceptions = exceptions.data?.items ?? []
  const filtered = useMemo(() => allExceptions.filter((item) => {
    const matchesType = filter === 'All exception types' || item.issue_type === filter
    const matchesSearch = `${item.entity_id} ${item.rule_id} ${item.evidence}`.toLowerCase().includes(query.toLowerCase())
    return matchesType && matchesSearch
  }), [allExceptions, filter, query])
  const cure = metrics.data?.cure_rate[0]
  const kept = metrics.data?.promise_kept_by_segment.reduce((sum, segment) => sum + segment.kept_count, 0) ?? 0
  const promiseCount = metrics.data?.promise_kept_by_segment.reduce((sum, segment) => sum + segment.promise_count, 0) ?? 0
  const keptRate = promiseCount ? kept / promiseCount : 0
  const types = [...new Set(allExceptions.map((item) => item.issue_type))]

  return (
    <>
      <section className="stat-grid">
        <StatCard label="Detected exceptions" value={exceptions.loading ? '—' : (exceptions.data?.total ?? 0).toLocaleString()} note="Input-only blind detectors" icon="!" tone="red" />
        <StatCard label="Promise kept" value={metrics.loading ? '—' : `${(keptRate * 100).toFixed(1)}%`} note={`${kept.toLocaleString()} of ${promiseCount.toLocaleString()} promises`} icon="✓" tone="green" />
        <StatCard label="Cure rate" value={metrics.loading ? '—' : `${((cure?.cure_rate ?? 0) * 100).toFixed(1)}%`} note={`${(cure?.cured_loans ?? 0).toLocaleString()} loans cured`} icon="↗" tone="blue" />
      </section>
      {metrics.error && <ErrorState message={metrics.error} onRetry={metrics.refresh} />}
      <section className="panel compliance-panel">
        <div className="panel-heading"><div><div className="section-title">Exceptions to review</div><div className="section-subtitle">Detections explain where a policy or data rule may need attention</div></div><span className="exception-count">{exceptions.data?.total ?? 0} findings</span></div>
        <div className="table-toolbar">
          <label className="search-field"><span>⌕</span><input aria-label="Search exceptions" placeholder="Search entity, rule or evidence…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label className="select-field"><span className="filter-glyph">☷</span><select aria-label="Filter exception type" value={filter} onChange={(event) => setFilter(event.target.value)}><option>All exception types</option>{types.map((type) => <option key={type}>{type}</option>)}</select></label>
        </div>
        {exceptions.loading && <LoadingState label="Loading exception detections…" />}
        {exceptions.error && <ErrorState message={exceptions.error} onRetry={exceptions.refresh} />}
        {exceptions.data && <div className="table-scroll"><table className="data-table exception-table"><thead><tr><th>ISSUE TYPE</th><th>AFFECTED RECORD</th><th>RULE</th><th>EVIDENCE</th><th /></tr></thead><tbody>
          {filtered.map((item) => <ExceptionRow item={item} key={`${item.issue_type}-${item.entity_id}`} onOpenCase={onOpenCase} />)}
          {!filtered.length && <tr><td colSpan={5} className="empty-cell">No findings match this filter.</td></tr>}
        </tbody></table></div>}
        {exceptions.data && <div className="table-foot"><span>Showing <strong>{filtered.length}</strong> of <strong>{exceptions.data.total}</strong> detected findings</span><span className="blind-label">Ground-truth blind</span></div>}
      </section>
      {metrics.data && <section className="metrics-grid">
        <div className="panel metric-panel"><div className="panel-heading"><div><div className="section-title">Promise outcomes by segment</div><div className="section-subtitle">Aggregate commitment reconciliation</div></div></div>
          {metrics.data.promise_kept_by_segment.length ? metrics.data.promise_kept_by_segment.map((row) => <div className="metric-row" key={row.segment}><div className="metric-row-label"><strong>{row.segment.replaceAll('_', ' ')}</strong><span>{row.kept_count}/{row.promise_count}</span></div><div className="metric-progress"><span style={{ width: `${row.kept_rate * 100}%` }} /></div><small>{(row.kept_rate * 100).toFixed(1)}% kept</small></div>) : <div className="empty-state">No promise outcomes available.</div>}
        </div>
        <div className="panel metric-panel"><div className="panel-heading"><div><div className="section-title">Policy decisions</div><div className="section-subtitle">Logged blocked, review and closed outcomes</div></div></div>
          {metrics.data.violations_by_rule.length ? <div className="rule-list">{metrics.data.violations_by_rule.slice(0, 8).map((row, index) => <div className="rule-row" key={`${row.rule_id}-${row.decision_type}-${row.outcome}-${index}`}><div><strong>{row.rule_id}</strong><small>{row.decision_type.replaceAll('_', ' ')}</small></div><span className={`outcome-pill outcome-${row.outcome}`}>{row.outcome}</span><b>{row.decision_count}</b></div>)}</div> : <div className="empty-state">No policy exceptions were logged.</div>}
        </div>
      </section>}
    </>
  )
}

function ExceptionRow({ item, onOpenCase }: { item: ExceptionItem; onOpenCase: (caseId: string) => void }) {
  const canOpen = item.entity_type === 'collection_case'
  return <tr>
    <td><span className="issue-label">{item.issue_type.replaceAll('_', ' ')}</span></td>
    <td><div className="primary-cell">{item.entity_id.split('|')[0]}</div><div className="secondary-cell">{item.entity_type.replaceAll('_', ' ')}</div></td>
    <td><span className="rule-code">{item.rule_id}</span></td>
    <td className="evidence-cell">{item.evidence}</td>
    <td>{canOpen && <button className="row-arrow" aria-label={`Open ${item.entity_id}`} onClick={() => onOpenCase(item.entity_id)}>→</button>}</td>
  </tr>
}

function AdminScreen() {
  const health = useResource(() => api.health())
  const validation = useResource(() => api.validation())
  const manifest = useResource(() => api.manifest())
  const policy = useResource(() => api.policy())
  const loading = health.loading || validation.loading || manifest.loading || policy.loading
  const error = health.error ?? validation.error ?? manifest.error ?? policy.error
  const refresh = () => { health.refresh(); validation.refresh(); manifest.refresh(); policy.refresh() }

  return <>
    <section className="admin-status-grid">
      <div className="panel admin-status-card"><span className={`status-orb ${health.data?.status === 'ok' ? 'orb-ok' : ''}`} /><div><small>API / DATABASE</small><strong>{health.data?.status === 'ok' ? 'Connected' : health.loading ? 'Checking…' : 'Unavailable'}</strong><span>{health.data?.foreign_keys_enabled ? 'Foreign keys enabled' : 'Read-only service health'}</span></div></div>
      <div className="panel admin-status-card"><span className={`status-orb ${validation.data?.valid ? 'orb-ok' : ''}`} /><div><small>DATA VALIDATION</small><strong>{validation.data ? (validation.data.valid ? 'Passed' : 'Review needed') : '—'}</strong><span>{validation.data ? `${validation.data.checks_passed} checks passed` : 'Integrity status'}</span></div></div>
      <div className="panel admin-status-card"><span className="status-orb orb-info" /><div><small>DATASET SOURCE</small><strong>{manifest.data?.source.type ?? '—'}</strong><span>{manifest.data?.source.external_data_used ? 'External data present' : 'No external data used'}</span></div></div>
    </section>
    <div className="admin-grid">
      <section className="panel admin-panel">
        <div className="panel-heading"><div><div className="section-title">Dataset manifest</div><div className="section-subtitle">Provenance and reproducibility details</div></div><button className="button button-secondary" onClick={refresh} disabled={loading}><span className="refresh-glyph">↻</span> Refresh</button></div>
        {manifest.data && <div className="manifest-list">
          <AdminValue label="Dataset" value={manifest.data.dataset} />
          <AdminValue label="Seed" value={manifest.data.seed.toLocaleString()} />
          <AdminValue label="Loans" value={manifest.data.loans.toLocaleString()} />
          <AdminValue label="As-of date" value={formatDate(manifest.data.as_of_date)} />
          <AdminValue label="Generated" value={formatDate(manifest.data.generation_date)} />
          <AdminValue label="Provenance" value={manifest.data.source.external_data_used ? 'External data included' : 'Fully synthetic'} />
        </div>}
        {manifest.loading && <LoadingState label="Loading manifest…" />}
      </section>
      <section className="panel admin-panel">
        <div className="panel-heading"><div><div className="section-title">Data checks</div><div className="section-subtitle">Integrity validation for the loaded dataset</div></div></div>
        {validation.data && <>
          <div className={`validation-banner ${validation.data.valid ? 'validation-pass' : 'validation-fail'}`}><strong>{validation.data.valid ? '✓ Dataset validated' : '! Validation needs review'}</strong><span>{validation.data.valid ? 'Primary keys, joins and business rules passed.' : `${validation.data.errors.length} issue(s) require attention.`}</span></div>
          <div className="manifest-list"><AdminValue label="Checks passed" value={validation.data.checks_passed.toLocaleString()} />{Object.entries(validation.data.row_counts).slice(0, 6).map(([name, count]) => <AdminValue key={name} label={name.replaceAll('_', ' ')} value={count.toLocaleString()} />)}</div>
          {validation.data.errors.length > 0 && <ul className="error-list">{validation.data.errors.slice(0, 8).map((item) => <li key={item}>{item}</li>)}</ul>}
        </>}
        {validation.loading && <LoadingState label="Checking dataset integrity…" />}
      </section>
    </div>
    <section className="panel policy-panel">
      <div className="panel-heading"><div><div className="section-title">Active policy summary</div><div className="section-subtitle">View-only configuration · policy version {policy.data?.policy_version ?? '—'}</div></div><span className="read-only"><span /> Read-only</span></div>
      {policy.data && <>
        <p className="policy-description">{policy.data.description}</p>
        <div className="policy-rules">{Object.entries(policy.data.rules).map(([id, rule]) => <div className="policy-rule" key={id}><span className="rule-code">{id}</span><span>{rule.desc}</span></div>)}</div>
        <div className="suppression-order"><div className="eyebrow">SUPPRESSION ORDER · FIRST MATCH WINS</div><div>{policy.data.suppression.first_match_order.map((rule, index) => <span className="suppression-step" key={rule}><b>{index + 1}</b>{rule}</span>)}</div></div>
        <div className="formula-note">Priority score: {policy.data.scoring.formula}</div>
      </>}
      {policy.loading && <LoadingState label="Loading active policy…" />}
    </section>
    {error && <ErrorState message={error} onRetry={refresh} />}
  </>
}

function AdminValue({ label, value }: { label: string; value: string }) {
  return <div className="manifest-row"><span>{label}</span><strong>{value}</strong></div>
}

function StatCard({ label, value, note, icon, tone }: { label: string; value: string; note: string; icon: string; tone: string }) {
  return <div className="panel stat-card"><div className={`stat-icon icon-${tone}`}>{icon}</div><div className="stat-copy"><span>{label}</span><strong>{value}</strong><small>{note}</small></div><span className="stat-spark" aria-hidden="true">⌁</span></div>
}

function TierBadge({ tier }: { tier: string }) {
  return <span className={`tier-badge tier-${tier.toLowerCase()}`}><i />{tier}</span>
}

function LoadingState({ label }: { label: string }) {
  return <div className="loading-state"><span className="spinner" /><span>{label}</span></div>
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="error-state"><div className="error-icon">!</div><div><strong>We couldn’t load this information</strong><p>{message}</p><button className="button button-secondary" onClick={onRetry}>Try again</button></div></div>
}

export default App
