import type {
  ApplicationStatusCode,
  BusinessPlanDto,
  ClientStatus,
  ConsentsDto,
  FounderPrescreenDto,
  OrganizationDetailDto,
  PreApprovedOfferDto,
  ProjectAssessmentDto,
} from '../client/types'
import type { DownloadedFile } from '../http'

/**
 * Бэк-офис андеррайтера на бэкенде (docs/api/client-journey.md §3.8): очередь задач,
 * карточка заявки с источниками, скорингом и правилами решения, решение по задаче, метрики.
 * Поля — как в openapi.json; здесь только то, что показывает рабочее место.
 */

/** Вид ручной проверки (policy_v5): check — проверка, dispute — спорная (модели или данные расходятся) */
export type ReviewKind = 'check' | 'dispute'

export type Grade = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J'

export interface QueueItemDto {
  task_id: string
  application_id: string
  number: string
  company_name: string
  inn: string
  product_code: string
  amount: string | null
  /** Балл и грейд PD-модели, A–J */
  score: number | null
  risk_grade: string | null
  /** По выпискам ожидается кассовый разрыв */
  cash_gap: boolean
  /** Почему заявка ушла на ручную проверку: ROUTE_* */
  routing_reasons: string[]
  review?: ReviewKind | null
  due_at: string | null
  overdue: boolean
  assignee_id: string | null
  /** open | in_progress | done | cancelled */
  status: string
  created_at: string
}

/** Заявка в списке всех заявок сотрудника (GET /applications): и черновики, и решённые автоматикой */
export interface StaffApplicationDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  status: ApplicationStatusCode
  client_stage: string | null
  amount: string | null
  term_months: number | null
  updated_at: string
  submitted_at: string | null
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
  product_terms: {
    code: string
    amount_min: string
    amount_max: string
    term_min_months: number
    term_max_months: number
    rate_base: string
    rate_max: string
    auto_decision_limit: string
    /** Маршрут продукта: по нему схема строится ещё до процесса — у черновика */
    workflow_code?: string
  }
  request: { amount: string; term_months: number; purpose: string; purpose_comment: string | null } | null
  product_fields: Record<string, unknown>
  collateral: { type: string; description: string; declared_value: string; owner: string } | null
  /** Согласия заявки: когда даны и откуда — галочка в черновике или из профиля */
  consents?: (ConsentsDto & { given_by?: string | null }) | null
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
    /** active | liquidating | liquidated | bankrupt | reorganizing | excluded */
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

export type EnrichmentSource =
  | 'egrul'
  | 'fns'
  | 'bki'
  | 'statement'
  | 'gir_bo'
  | 'kontur'
  | 'bki_head'
  | 'aml'
  | 'bank_stop_list'
  | 'bank_turnover'

export interface SourceErrorDto {
  source: EnrichmentSource
  code: string
  message: string
}

export interface CreditHistoryDto {
  obligations: ObligationDto[]
  inquiries_last_30d: number
  has_active_overdue: boolean
  max_overdue_days_12m: number
  total_monthly_payments: string
}

/** Бухотчётность из ГИР БО за год */
export interface AccountingPeriodDto {
  year: number
  revenue: string
  net_profit: string
  equity: string
  total_assets: string
  total_liabilities: string
  receivables: string
  cash: string
}

/** Контур: надёжность, суды, приставы, банкротство, госконтракты */
export interface CounterpartyRiskDto {
  reliability: 'green' | 'yellow' | 'red'
  notes: string[]
  arbitration: { as_defendant: number; as_plaintiff: number; defendant_sum: string }
  enforcement: { active: number; sum: string }
  bankruptcy_messages: { date: string; type: string; case: string }[]
  gov_contracts: { count: number; sum: string }
  active_pledges: number
}

/** Кого проверили по 115-ФЗ: компания, учредитель-юрлицо цепочки, руководитель, бенефициар, представитель */
export interface AmlSubjectDto {
  role: 'company' | 'founder_company' | 'head' | 'beneficial_owner' | 'representative'
  name: string
  inn: string | null
}

/** Проверка по 115-ФЗ: бенефициары, перечни Росфинмониторинга, публичные должностные лица, риск ЗСК */
export interface AmlCheckDto {
  lists_date: string
  zsk: { level: 'low' | 'medium' | 'high'; as_of: string }
  beneficial_owners: { name: string; basis: 'ownership' | 'head_by_default' | 'entrepreneur'; share_percent: string | null }[]
  subjects: AmlSubjectDto[]
  list_hits: { subject: AmlSubjectDto; list: 'terrorism' | 'freeze' | 'wmd'; record: string }[]
  pep_hits: { subject: AmlSubjectDto; kind: 'foreign' | 'russian' | 'international'; position: string }[]
}

/** Обороты по расчётному счёту в банке (АБС) за 24 месяца */
export interface BankTurnoverDto {
  client_since: string | null
  months: { month: string; inflow: string; outflow: string }[]
}

export interface EnrichmentDto {
  collected_at: string
  sources_ok: EnrichmentSource[]
  sources_failed: SourceErrorDto[]
  /** Не запрошены: БКИ — нет согласия, БКИ руководителя — нет согласия или руководителя */
  sources_skipped?: SourceErrorDto[]
  egrul: {
    full_name: string
    status: string
    registered_at: string
    okved_main: string
    head_last_name: string
    head_first_name: string
    head_middle_name: string | null
    head_position: string
    founders: { name: string; share_percent: string; inn?: string | null }[]
    address: string
    mass_address: boolean
    kpp?: string | null
    /** С какой даты руководитель в реестре */
    head_since?: string | null
    /** Отметки о недостоверности сведений: адрес, руководитель, учредитель */
    unreliable?: ('address' | 'head' | 'founder')[]
  } | null
  fns: {
    tax_arrears: string
    avg_headcount: number
    reported_revenue: string | null
    report_year: number | null
    tax_regime: string
    disqualified_head: boolean
    in_msp_registry: boolean
    /** Приостановления операций по счетам */
    account_blocks?: { decision_number: string; date: string; authority_code: string; reason: string }[]
    /** Признаки массового руководителя */
    mass_head?: boolean | null
  } | null
  bki: CreditHistoryDto | null
  /** БКИ руководителя — только с его личным согласием */
  bki_head?: CreditHistoryDto | null
  gir_bo?: { available: boolean; reason: string | null; periods: AccountingPeriodDto[] } | null
  kontur?: CounterpartyRiskDto | null
  /** Проверка по 115-ФЗ; null — не выполнена (aml в sources_failed) */
  aml?: AmlCheckDto | null
  /** Внутренний стоп-лист банка */
  bank_stop_list?: { listed: boolean; reason: string | null; listed_at: string | null } | null
  bank_turnover?: BankTurnoverDto | null
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

export interface FactorDto {
  code: string
  value: string | null
  bin: string
  points: number
  direction: 'positive' | 'negative' | 'neutral'
  client_hint: string | null
}

/** Оценка ML-модели на тех же данных и той же шкале A–J, что у PD-модели */
export interface MlScoreDto {
  model_version: string
  /** Вероятность дефолта за 12 месяцев, доля */
  pd_12m: string
  score: number
  grade: Grade
  factors: FactorDto[]
  reason_codes: string[]
}

export interface ScoringDto {
  model_version: string
  score: number
  grade: Grade
  factors: FactorDto[]
  flags: string[]
  data_completeness: string
  computed_at: string
  segment?: 'legal_entity' | 'entrepreneur' | 'new_client' | null
  scorecard?: string | null
  /** Вероятность дефолта за 12 месяцев, доля */
  pd_12m?: string | null
  /** Факторы, сильнее всего снизившие балл */
  reason_codes?: string[]
  /** Оценка ML-модели; нет — заявка оценена до появления второй модели */
  ml?: MlScoreDto | null
  /** Данные полные? degraded — не ответил критичный источник или мало признаков: решает человек */
  quality?: 'ok' | 'degraded' | null
  /** source_failed:<источник>, completeness_below:<доля> */
  quality_reasons?: string[]
}

/** Лимиты движка; binding — какой из них дал итоговый минимум */
export interface LimitsDto {
  by_revenue: string | null
  by_ltv: string | null
  by_capacity: string | null
  by_product?: string | null
  by_turnover?: string | null
  by_grade?: string | null
  by_group?: string | null
  final?: string | null
  binding?: string | null
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
  limits: LimitsDto
  decided_by_type: 'auto' | 'underwriter'
  comment: string | null
  decided_at: string
  /** Мягкие триггеры, из-за которых заявка ушла на ручную проверку */
  triggers?: { code: string; detail: string }[]
  /** Из чего сложилась ставка, процентные пункты */
  rate_breakdown?: { funding: string; expected_loss: string; capital: string; margin: string; total: string } | null
  /** Вид ручной проверки — только у MANUAL_REVIEW */
  review?: ReviewKind | null
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
  /** Заявка стартапа с проектной оценкой её продукта */
  startup?: StartupProjectDto | null
}

/** Проектная оценка стартапа для андеррайтера — с цифрами модели, которых клиент не видит */
export interface ProjectAssessmentFullDto extends ProjectAssessmentDto {
  figures: {
    requested_amount: string
    term_months: number
    rate: string
    cash_flow: string
    debt_service: string
    dscr: string | null
    own_share: string
    coverage: string
    /** Сколько выдерживает проект */
    capacity: string
  }
  version: string
}

/** С чем открыть форму проектной оценки: андеррайтер подтверждает или правит */
export interface ProjectFormDto {
  decision: 'approve' | 'counter_offer' | 'reject'
  amount: string | null
  term_months: number | null
  business_plan: 'strong' | 'acceptable' | 'weak'
  collateral: string | null
  support_program: boolean
}

export interface StartupProjectDto {
  assessment: ProjectAssessmentFullDto
  business_plan: BusinessPlanDto | null
  /** План уточнили после оценки */
  plan_changed: boolean
  /** Оценка действовала на дату подачи */
  valid_at_submission: boolean
  form: ProjectFormDto
}

/** Состояние процесса: running — идёт, waiting — ждёт человека или внешний сервис, остальные — финал */
export type ProcessStatus = 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled'

/** Шаг процесса — один проход узла BPMN; узел, пройденный дважды, даёт два шага с iteration 1 и 2 */
export interface ProcessStepDto {
  node_id: string
  step_code: string | null
  /** immediate — выполнен сразу, async — ждёт внешний сервис, stoppable — ждёт человека */
  kind: 'immediate' | 'async' | 'stoppable'
  iteration: number
  started_at: string
  finished_at: string | null
  /** completed | failed | cancelled; null — шаг ещё идёт */
  outcome: string | null
  client_stage: string | null
  error: string | null
}

/** Где заявка на маршруте банка (GET /processes/{application_id}) */
export interface ProcessDto {
  process_id: string
  application_id: string
  /** Код маршрута: схема — GET /workflows/{code}/diagram */
  workflow_code: string
  workflow_version: number
  status: ProcessStatus
  /** Узел, на котором процесс сейчас; у завершённого — null */
  current_node_id: string | null
  client_stage: string | null
  /** Пройденные узлы без повторов, в порядке первого прохода */
  visited_node_ids: string[]
  /** Шаги по времени, с повторами */
  steps: ProcessStepDto[]
  started_at: string
  finished_at: string | null
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
  /** Только проектная оценка стартапа */
  business_plan?: ProjectFormDto['business_plan']
  collateral?: string | null
  support_program?: boolean
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
  /** PDF договора — банк видит договоры всех заявок; kind не задан — последний готовый */
  contractDocument(applicationId: string, kind?: 'draft' | 'signed'): Promise<DownloadedFile>
  /** Процесс заявки: текущий узел и пройденные шаги */
  process(applicationId: string): Promise<ProcessDto>
  /** Схема маршрута — BPMN 2.0 XML */
  workflowDiagram(code: string): Promise<string>
  /** Все заявки, свежие сверху; сотруднику — всех компаний, со статусом, этапом и черновиками */
  applications(query?: { limit?: number; offset?: number }): Promise<StaffApplicationDto[]>
  organization(organizationId: string): Promise<OrganizationDetailDto>
  /** До заявки — предскоринг компании: предодобренные предложения, у стартапа — проверка учредителя и проектная оценка */
  preApprovedOffers(organizationId: string): Promise<PreApprovedOfferDto[]>
  /** 404 — проверки не было */
  founderPrescreen(organizationId: string): Promise<FounderPrescreenDto>
  /** 404 — оценки не было */
  projectAssessment(organizationId: string): Promise<ProjectAssessmentDto>
}
