import type { Dossier, ExpectedOutcome } from './sources'

/**
 * Контракт кредитного домена для админки. Бэкенда заявок пока нет, поэтому это наше предложение
 * контракта; мок ниже реализует его в браузере. Когда появится API, меняется только реализация.
 */
export type ApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'checking'
  | 'scoring'
  | 'info_requested'
  | 'approved'
  | 'counter_offer'
  | 'rejected'
  | 'signing'
  | 'issued'

export type DecisionOutcome = ExpectedOutcome

export type RiskClass = 'A' | 'B' | 'C' | 'D'

export interface ScoreFactor {
  id: ScoringFactorId
  label: string
  /** Влияние на балл: плюс снижает риск, минус повышает */
  impact: number
  /** Что именно увидели в данных, например «выручка +14% за год» */
  detail: string
}

export interface ScoreResult {
  /** 0–100, чем выше, тем ниже риск */
  score: number
  riskClass: RiskClass
  factors: ScoreFactor[]
  stopFactors: string[]
  /** Чего не хватает для решения, например «нет отчётности в ГИР БО» */
  missingData: string[]
  recommendation: DecisionOutcome
  /** Для встречного предложения — сумма, которую готовы дать */
  suggestedAmount: number | null
  calculatedAt: string
}

export interface Decision {
  outcome: DecisionOutcome
  amount: number
  termMonths: number
  rate: number
  comment: string
  decidedBy: string
  decidedAt: string
}

export interface HistoryEntry {
  at: string
  status: ApplicationStatus
  actor: string
  comment?: string
}

export interface AdminApplication {
  id: string
  number: string
  createdAt: string
  updatedAt: string
  /** Крайний срок решения по SLA */
  dueAt: string
  status: ApplicationStatus
  productId: string
  amount: number
  termMonths: number
  purpose: string
  inn: string
  applicantName: string
  contactName: string
  contactPhone: string
  assignee: string | null
  score: ScoreResult | null
  decision: Decision | null
  history: HistoryEntry[]
}

export interface ApplicationDetails extends AdminApplication {
  dossier: Dossier | null
}

export interface ApplicationFilters {
  status?: ApplicationStatus | 'active'
  productId?: string
  search?: string
}

export interface DecisionInput {
  outcome: DecisionOutcome
  amount: number
  termMonths: number
  rate: number
  comment: string
}

/** Шаги после решения: отправить на подписание, отметить выдачу */
export type ApplicationTransition = 'to_signing' | 'issue'

export type ScoringFactorId =
  | 'business_age'
  | 'revenue_growth'
  | 'profitability'
  | 'debt_load'
  | 'tax_discipline'
  | 'litigation'
  | 'enforcement'
  | 'reliability'
  | 'loan_to_revenue'

export type StopFactorId =
  | 'inactive'
  | 'bankruptcy'
  | 'account_blocks'
  | 'negative_equity'
  | 'disqualified'
  | 'large_enforcement'

export interface ScoringConfig {
  /** Множитель влияния фактора: 0 — не учитывать, 1 — как есть, 2 — вдвое сильнее */
  weights: Record<ScoringFactorId, number>
  stopFactors: Record<StopFactorId, boolean>
  /** Балл, от которого одобряем как есть */
  approveFrom: number
  /** Балл, от которого предлагаем другие условия; ниже — отказ */
  counterFrom: number
  /** Какую долю запрошенной суммы предлагаем во встречном предложении, % */
  counterAmountPercent: number
}

export interface ProductSettings {
  id: string
  title: string
  rateFrom: number
  amountMin: number
  amountMax: number
  termMin: number
  termMax: number
  decisionTime: string
  /** Принимаем ли заявки на продукт */
  active: boolean
  updatedAt: string | null
  updatedBy: string | null
}

export interface DashboardStats {
  total: number
  inProgress: number
  overdue: number
  decided: number
  approvalRate: number
  approvedVolume: number
  averageAmount: number
  /** Среднее время от подачи до решения, часы */
  averageDecisionHours: number
  byStatus: Record<ApplicationStatus, number>
  byProduct: { productId: string; title: string; count: number; amount: number }[]
  byRisk: Record<RiskClass, number>
  funnel: { label: string; count: number }[]
  /** Заявки за последние 14 дней */
  daily: { date: string; count: number }[]
}

/** Как изменятся рекомендации по заявкам, если применить черновик настроек */
export interface ScoringPreviewRow {
  applicationId: string
  number: string
  applicantName: string
  before: { score: number; recommendation: DecisionOutcome }
  after: { score: number; recommendation: DecisionOutcome }
}

export interface CreditApi {
  listApplications(filters?: ApplicationFilters): Promise<AdminApplication[]>
  getApplication(id: string): Promise<ApplicationDetails>
  rescore(id: string): Promise<ApplicationDetails>
  decide(id: string, input: DecisionInput): Promise<ApplicationDetails>
  transition(id: string, transition: ApplicationTransition): Promise<ApplicationDetails>
  assign(id: string): Promise<ApplicationDetails>
  getDashboard(): Promise<DashboardStats>
  /** Досье по ИНН и предварительный скоринг на указанную сумму; null — в источниках не найден */
  lookupInn(inn: string, amount: number): Promise<{ dossier: Dossier; score: ScoreResult } | null>
  listProducts(): Promise<ProductSettings[]>
  updateProduct(id: string, data: Partial<Omit<ProductSettings, 'id'>>): Promise<ProductSettings>
  getScoringConfig(): Promise<ScoringConfig>
  updateScoringConfig(config: ScoringConfig): Promise<ScoringConfig>
  previewScoring(config: ScoringConfig): Promise<ScoringPreviewRow[]>
  resetDemoData(): Promise<void>
}
