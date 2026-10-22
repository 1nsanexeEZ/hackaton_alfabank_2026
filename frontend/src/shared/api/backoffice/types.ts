import type { ApplicationStatusCode, ClientStatus } from '../client/types'

/**
 * Бэк-офис андеррайтера на бэкенде (docs/api/client-journey.md §3.8): очередь задач,
 * карточка заявки с источниками, скорингом и правилами решения, решение по задаче, метрики.
 * Поля — как в openapi.json; здесь только то, что показывает рабочее место.
 */

export interface QueueItemDto {
  task_id: string
  application_id: string
  number: string
  company_name: string
  inn: string
  product_code: string
  amount: string | null
  /** Балл скоринга и грейд A–E */
  score: number | null
  risk_grade: string | null
  /** По выпискам ожидается кассовый разрыв */
  cash_gap: boolean
  /** Почему заявка ушла на ручную проверку: ROUTE_* */
  routing_reasons: string[]
  due_at: string | null
  overdue: boolean
  assignee_id: string | null
  /** open | in_progress | done | cancelled */
  status: string
  created_at: string
}

export interface QueuePageDto {
  items: QueueItemDto[]
  total: number
}

export interface FinancialReportSnapshotDto {
  period_year: number
  period_quarter: number | null
  source: 'declared' | 'fns' | 'bank_statement'
  revenue: string
  expenses: string | null
  net_profit: string | null
  total_liabilities: string | null
  monthly_debt_payments: string | null
}

export interface UnderwriterApplicationDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  product_terms: { code: string; amount_min: string; amount_max: string; term_min_months: number; term_max_months: number; rate_base: string; rate_max: string; auto_decision_limit: string }
  request: { amount: string; term_months: number; purpose: string; purpose_comment: string | null } | null
  product_fields: Record<string, unknown>
  collateral: { type: string; description: string; declared_value: string; owner: string } | null
  org_snapshot: {
    inn: string
    ogrn: string
    kpp: string | null
    legal_form: string
    name: string
    registered_at: string
    business_age_months: number
    okved_main: string
    tax_regime: string
    employees_count: number
    registry_status: string
    verification_status: 'unverified' | 'verified' | 'mismatch'
    discrepancies: { field: string; declared: string | null; registry: string | null }[]
    head_name: string | null
    financial_reports: FinancialReportSnapshotDto[]
  } | null
  status: ApplicationStatusCode
  client_stage: string | null
  documents: { id: string; type: string; filename: string; status: string; uploaded_at: string | null; review_comment: string | null }[]
  info_requests: { id: string; requested_documents: string[]; comment: string; status: string; created_at: string; answered_at: string | null }[]
  offer: { kind: string; amount: string; term_months: number; rate: string; monthly_payment: string; conditions: string[]; expires_at: string } | null
  submitted_at: string | null
  created_at: string
}

export interface ObligationDto {
  creditor: string
  kind: string
  amount: string
  balance: string
  monthly_payment: string
  opened_at: string
  closes_at: string | null
  overdue_days: number
}

export interface EnrichmentDto {
  collected_at: string
  sources_ok: string[]
  sources_failed: { source: string; code: string; message: string }[]
  egrul: {
    full_name: string
    status: string
    registered_at: string
    okved_main: string
    head_last_name: string
    head_first_name: string
    head_middle_name: string | null
    head_position: string
    founders: { name: string; share_percent: string }[]
    address: string
    mass_address: boolean
  } | null
  fns: {
    tax_arrears: string
    avg_headcount: number
    reported_revenue: string | null
    report_year: number | null
    tax_regime: string
    disqualified_head: boolean
    in_msp_registry: boolean
  } | null
  bki: {
    obligations: ObligationDto[]
    inquiries_last_30d: number
    has_active_overdue: boolean
    max_overdue_days_12m: number
    total_monthly_payments: string
  } | null
  cashflow: {
    months_history: { month: string; inflow: string; outflow: string; net: string; balance: string }[]
    forecast: { month: string; projected_balance: string }[]
    gap_detected: boolean
    gap_month: string | null
    gap_amount: string | null
    annual_inflow: string
    revenue_confirmed: boolean | null
  } | null
}

export interface ScoringDto {
  model_version: string
  score: number
  grade: 'A' | 'B' | 'C' | 'D' | 'E'
  factors: { code: string; value: string | null; bin: string; points: number; direction: 'positive' | 'negative' | 'neutral'; client_hint: string | null }[]
  flags: string[]
  data_completeness: string
  computed_at: string
}

export interface DecisionDto {
  policy_version: string
  key_rate: string
  outcome: 'APPROVE' | 'COUNTER_OFFER' | 'REQUEST_INFO' | 'MANUAL_REVIEW' | 'REJECT'
  terms: { amount: string; term_months: number; rate: string; monthly_payment: string; conditions: string[] } | null
  alternative_product_code: string | null
  reason_codes: string[]
  client_explanation: string
  rule_trace: { rule: string; matched: boolean; detail: string }[]
  limits: { by_revenue: string | null; by_ltv: string | null; by_capacity: string | null }
  decided_by_type: 'auto' | 'underwriter'
  comment: string | null
  decided_at: string
}

export interface UnderwriterTaskDto {
  id: string
  type: string
  candidate_role: string
  assignee_id: string | null
  /** open | in_progress | done | cancelled */
  status: string
  created_at: string
  due_at: string | null
  result: Record<string, unknown> | null
}

/** Карточка андеррайтера (GET /bff/backoffice/applications/{id}) */
export interface UnderwriterCardDto {
  application: UnderwriterApplicationDto
  client_status: ClientStatus
  enrichment: EnrichmentDto | null
  scoring: ScoringDto | null
  decision: DecisionDto | null
  product_fit: { eligible: boolean; reasons: { code: string; passed: boolean; message: string }[] } | null
  timeline: { id: string; at: string; kind: string; title: string; audience: 'client' | 'bank' }[]
  process: {
    workflow_code: string
    status: string
    client_stage: string | null
    steps: { node_id: string; step_code: string | null; kind: string; started_at: string; finished_at: string | null; outcome: string | null; error: string | null }[]
  } | null
  task: UnderwriterTaskDto | null
  degraded: string[]
}

export interface MetricsDto {
  date_from: string
  date_to: string
  rows: {
    day: string
    product_code: string
    submitted: number
    approved: number
    counter_offers: number
    rejected: number
    manual_reviews: number
    auto_decisions: number
    avg_time_to_decision_sec: number | null
  }[]
  submitted: number
  decided: number
  auto_decision_share: number | null
  avg_time_to_decision_sec: number | null
}

export type TaskDecision = 'approve' | 'counter_offer' | 'reject' | 'request_info'

export interface TaskResultInput {
  decision: TaskDecision
  amount?: number | null
  term_months?: number | null
  rate?: number | null
  conditions: string[]
  requested_documents: string[]
  comment: string
}

export interface BackofficeApi {
  queue(query?: { status?: string; sort?: string; limit?: number; offset?: number }): Promise<QueuePageDto>
  card(applicationId: string): Promise<UnderwriterCardDto>
  /** Взять задачу на себя */
  claim(taskId: string): Promise<UnderwriterTaskDto>
  /** Решение по задаче: одобрить, контрпредложение, отказ, запрос информации */
  complete(taskId: string, input: TaskResultInput): Promise<UnderwriterTaskDto>
  metrics(query?: { dateFrom?: string; dateTo?: string }): Promise<MetricsDto>
  downloadDocument(applicationId: string, documentId: string): Promise<{ url: string }>
}
