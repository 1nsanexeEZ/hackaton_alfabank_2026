import type { Permission } from '../identity'
import { readStorage, writeStorage } from '../../lib/storage'
import { ApiError, delay } from '../http'
import { DEFAULT_SCORING_CONFIG, scoreDossier } from './scoring'
import { DOSSIERS, dossierInn, dossierName, findDossier, type Dossier } from './sources'
import type {
  AdminApplication,
  ApplicationStatus,
  CreditApi,
  DashboardStats,
  DecisionOutcome,
  HistoryEntry,
  ProductSettings,
  RiskClass,
  ScoringConfig,
} from './types'

/**
 * Кредитный домен в браузере: заявки, скоринг, продукты, настройки.
 * Заявки сгенерированы из синтетических досье (frontend/mocks/external-sources.json),
 * изменения сохраняются в localStorage, «Сбросить демо-данные» возвращает исходное состояние.
 */
const STORAGE_KEY = 'admin-mock:credit'
const HOUR = 3600 * 1000
const SLA_HOURS = 24
const SYSTEM = 'Система'

type ProductSeed = Pick<ProductSettings, 'id' | 'title' | 'rateFrom' | 'amountMin' | 'amountMax' | 'termMin' | 'termMax' | 'decisionTime'>

interface MockContext {
  /** Каталог продуктов по умолчанию — его отдаёт слой app из сущности credit-product */
  products: ProductSeed[]
  /** Кто сейчас работает: имя для истории заявки и проверка прав, как это делал бы бэкенд по токену */
  actor: () => string
  can: (permission: Permission) => boolean
}

let context: MockContext = { products: [], actor: () => 'Сотрудник', can: () => false }

export function configureCreditMock(next: MockContext): void {
  context = next
}

interface Store {
  applications: AdminApplication[]
  products: ProductSettings[]
  scoring: ScoringConfig
}

/** Риск-надбавка к базовой ставке продукта, п. п. */
const RISK_PREMIUM: Record<RiskClass, number> = { A: 0, B: 1.5, C: 3, D: 5 }

interface SeedPlan {
  inn: string
  productId: string
  amount: number
  termMonths: number
  purpose: string
  status: ApplicationStatus
  /** Сколько часов назад подана */
  ageHours: number
}

const PURPOSE = {
  equipment: 'Покупка оборудования',
  working: 'Пополнение оборотных средств',
  gap: 'Кассовый разрыв',
  growth: 'Развитие бизнеса',
  refinance: 'Рефинансирование',
}

function seedPlans(): SeedPlan[] {
  const inn = DOSSIERS.map(dossierInn)
  const at = (index: number) => inn[index] ?? inn[0]!
  return [
    { inn: at(0), productId: 'secured', amount: 12_000_000, termMonths: 36, purpose: PURPOSE.equipment, status: 'scoring', ageHours: 20 },
    { inn: at(1), productId: 'unsecured', amount: 5_000_000, termMonths: 24, purpose: PURPOSE.working, status: 'issued', ageHours: 290 },
    { inn: at(2), productId: 'credit-line', amount: 15_000_000, termMonths: 24, purpose: PURPOSE.working, status: 'scoring', ageHours: 70 },
    { inn: at(3), productId: 'unsecured', amount: 1_500_000, termMonths: 12, purpose: PURPOSE.growth, status: 'info_requested', ageHours: 50 },
    { inn: at(4), productId: 'unsecured', amount: 8_000_000, termMonths: 36, purpose: PURPOSE.refinance, status: 'rejected', ageHours: 150 },
    { inn: at(5), productId: 'overdraft', amount: 2_000_000, termMonths: 12, purpose: PURPOSE.gap, status: 'rejected', ageHours: 220 },
    { inn: at(6), productId: 'overdraft', amount: 3_000_000, termMonths: 6, purpose: PURPOSE.gap, status: 'submitted', ageHours: 3 },
    { inn: at(7), productId: 'unsecured', amount: 2_500_000, termMonths: 24, purpose: PURPOSE.growth, status: 'scoring', ageHours: 11 },
    { inn: at(8), productId: 'credit-line', amount: 3_000_000, termMonths: 12, purpose: PURPOSE.working, status: 'approved', ageHours: 100 },
    { inn: at(9), productId: 'unsecured', amount: 1_000_000, termMonths: 24, purpose: PURPOSE.equipment, status: 'signing', ageHours: 125 },
    { inn: at(10), productId: 'unsecured', amount: 1_000_000, termMonths: 18, purpose: PURPOSE.equipment, status: 'counter_offer', ageHours: 170 },
    { inn: at(11), productId: 'overdraft', amount: 500_000, termMonths: 6, purpose: PURPOSE.gap, status: 'submitted', ageHours: 2 },
    { inn: at(12), productId: 'unsecured', amount: 800_000, termMonths: 12, purpose: PURPOSE.working, status: 'rejected', ageHours: 260 },
    { inn: at(1), productId: 'overdraft', amount: 1_500_000, termMonths: 12, purpose: PURPOSE.gap, status: 'issued', ageHours: 310 },
    { inn: at(0), productId: 'overdraft', amount: 4_000_000, termMonths: 12, purpose: PURPOSE.gap, status: 'issued', ageHours: 240 },
    { inn: at(8), productId: 'overdraft', amount: 800_000, termMonths: 6, purpose: PURPOSE.gap, status: 'scoring', ageHours: 26 },
    { inn: at(9), productId: 'credit-line', amount: 1_200_000, termMonths: 12, purpose: PURPOSE.working, status: 'checking', ageHours: 4 },
  ]
}

const ANALYSTS = ['Воронцова М. И.', 'Сорокин К.']
const DECIDED: ApplicationStatus[] = ['approved', 'counter_offer', 'rejected', 'info_requested', 'signing', 'issued']
const ACTIVE: ApplicationStatus[] = ['submitted', 'checking', 'scoring']

function contactOf(dossier: Dossier): string {
  return dossier.kind === 'company' ? dossier.egrul.director.name : dossier.egrip.fio
}

function phoneFor(index: number): string {
  const tail = String(1_234_567 + index * 7_919).padStart(7, '0').slice(-7)
  return `+7 916 ${tail.slice(0, 3)}-${tail.slice(3, 5)}-${tail.slice(5)}`
}

function productOf(store: Store, id: string): ProductSettings | undefined {
  return store.products.find((item) => item.id === id)
}

function rateFor(store: Store, productId: string, risk: RiskClass): number {
  return (productOf(store, productId)?.rateFrom ?? 25) + RISK_PREMIUM[risk]
}

function seedApplication(store: Store, plan: SeedPlan, index: number, now: number): AdminApplication {
  const dossier = findDossier(plan.inn)!
  const created = now - plan.ageHours * HOUR
  const iso = (offsetHours: number) => new Date(created + offsetHours * HOUR).toISOString()
  const contact = contactOf(dossier)
  const analyst = ANALYSTS[index % ANALYSTS.length]!
  const history: HistoryEntry[] = [{ at: iso(0), status: 'submitted', actor: contact }]

  const reached = (status: ApplicationStatus) => plan.status === status || DECIDED.includes(plan.status)
  if (plan.status !== 'submitted') history.push({ at: iso(0.1), status: 'checking', actor: SYSTEM })
  if (reached('scoring')) history.push({ at: iso(0.3), status: 'scoring', actor: SYSTEM })

  const score = plan.status === 'submitted' || plan.status === 'checking'
    ? null
    : scoreDossier(dossier, plan.amount, store.scoring, new Date(created + 0.3 * HOUR))

  let decision: AdminApplication['decision'] = null
  if (score && DECIDED.includes(plan.status)) {
    const outcome: DecisionOutcome =
      plan.status === 'signing' || plan.status === 'issued' ? 'approved' : (plan.status as DecisionOutcome)
    const amount = outcome === 'counter_offer' ? (score.suggestedAmount ?? plan.amount * 0.6) : plan.amount
    // Явные отказы по стоп-факторам система выносит сама, остальное решает аналитик
    const decidedBy = outcome === 'rejected' && score.stopFactors.length ? SYSTEM : analyst
    decision = {
      outcome,
      amount,
      termMonths: plan.termMonths,
      rate: rateFor(store, plan.productId, score.riskClass),
      comment:
        outcome === 'rejected'
          ? score.stopFactors[0] ?? 'Высокий риск по совокупности факторов'
          : outcome === 'info_requested'
            ? score.missingData[0] ?? 'Нужны дополнительные документы'
            : outcome === 'counter_offer'
              ? 'Одобрено на меньшую сумму из-за долговой нагрузки'
              : 'Финансовое положение устойчивое',
      decidedBy,
      decidedAt: iso(decidedBy === SYSTEM ? 0.35 : 5),
    }
    history.push({ at: decision.decidedAt, status: outcome, actor: decidedBy, comment: decision.comment })
    if (plan.status === 'signing' || plan.status === 'issued') {
      history.push({ at: iso(26), status: 'signing', actor: analyst })
    }
    if (plan.status === 'issued') history.push({ at: iso(50), status: 'issued', actor: SYSTEM })
  }

  const last = history.at(-1)!
  return {
    id: `app-${104_500 + index}`,
    number: `ЗК-${104_500 + index}`,
    createdAt: iso(0),
    updatedAt: last.at,
    dueAt: iso(SLA_HOURS),
    status: plan.status,
    productId: plan.productId,
    amount: plan.amount,
    termMonths: plan.termMonths,
    purpose: plan.purpose,
    inn: plan.inn,
    applicantName: dossierName(dossier),
    contactName: contact,
    contactPhone: phoneFor(index),
    assignee: plan.status === 'scoring' && index % 2 === 0 ? analyst : DECIDED.includes(plan.status) && decision?.decidedBy !== SYSTEM ? analyst : null,
    score,
    decision,
    history,
  }
}

function seedProducts(): ProductSettings[] {
  return context.products.map((item) => ({ ...item, active: true, updatedAt: null, updatedBy: null }))
}

function seed(): Store {
  const store: Store = { applications: [], products: seedProducts(), scoring: structuredClone(DEFAULT_SCORING_CONFIG) }
  const now = Date.now()
  store.applications = seedPlans().map((plan, index) => seedApplication(store, plan, index, now))
  return store
}

let cached: Store | null = null

/** Хранилище поднимаем лениво: к этому моменту слой app уже передал каталог продуктов */
function db(): Store {
  if (!cached) cached = readStorage<Store>(STORAGE_KEY) ?? seed()
  return cached
}

function save() {
  writeStorage(STORAGE_KEY, cached)
}

function requirePermission(permission: Permission) {
  if (!context.can('admin') && !context.can(permission)) {
    throw new ApiError(403, 'permission_denied', 'Недостаточно прав')
  }
}

function findApplication(id: string): AdminApplication {
  const found = db().applications.find((item) => item.id === id)
  if (!found) throw new ApiError(404, 'not_found', 'Заявка не найдена')
  return found
}

function details(application: AdminApplication) {
  return { ...structuredClone(application), dossier: findDossier(application.inn) }
}

function setStatus(application: AdminApplication, status: ApplicationStatus, comment?: string, actor = context.actor()) {
  const at = new Date().toISOString()
  application.status = status
  application.updatedAt = at
  application.history.push({ at, status, actor, ...(comment ? { comment } : {}) })
}

function computeDashboard(store: Store): DashboardStats {
  const apps = store.applications
  const now = Date.now()
  const byStatus = Object.fromEntries(
    (['draft', 'submitted', 'checking', 'scoring', 'info_requested', 'approved', 'counter_offer', 'rejected', 'signing', 'issued'] as const).map(
      (status) => [status, apps.filter((item) => item.status === status).length],
    ),
  ) as Record<ApplicationStatus, number>
  const decided = apps.filter((item) => item.decision)
  const positive = decided.filter((item) => item.decision!.outcome === 'approved' || item.decision!.outcome === 'counter_offer')
  const decisionHours = decided.map((item) => (Date.parse(item.decision!.decidedAt) - Date.parse(item.createdAt)) / HOUR)
  const byRisk: Record<RiskClass, number> = { A: 0, B: 0, C: 0, D: 0 }
  for (const item of apps) if (item.score) byRisk[item.score.riskClass] += 1

  const days = Array.from({ length: 14 }, (_, offset) => {
    const date = new Date(now - (13 - offset) * 24 * HOUR)
    return date.toISOString().slice(0, 10)
  })

  return {
    total: apps.length,
    inProgress: apps.filter((item) => ACTIVE.includes(item.status)).length,
    overdue: apps.filter((item) => ACTIVE.includes(item.status) && Date.parse(item.dueAt) < now).length,
    decided: decided.length,
    approvalRate: decided.length ? positive.length / decided.length : 0,
    approvedVolume: positive.reduce((sum, item) => sum + item.decision!.amount, 0),
    averageAmount: apps.length ? apps.reduce((sum, item) => sum + item.amount, 0) / apps.length : 0,
    averageDecisionHours: decisionHours.length ? decisionHours.reduce((a, b) => a + b, 0) / decisionHours.length : 0,
    byStatus,
    byProduct: store.products.map((product) => {
      const items = apps.filter((item) => item.productId === product.id)
      return { productId: product.id, title: product.title, count: items.length, amount: items.reduce((sum, item) => sum + item.amount, 0) }
    }),
    byRisk,
    funnel: [
      { label: 'Подано', count: apps.length },
      { label: 'Проверено', count: apps.filter((item) => item.score).length },
      { label: 'Решение', count: decided.length },
      { label: 'Одобрено', count: positive.length },
      { label: 'Выдано', count: byStatus.issued },
    ],
    daily: days.map((date) => ({ date, count: apps.filter((item) => item.createdAt.startsWith(date)).length })),
  }
}

export const mockCreditApi: CreditApi = {
  async listApplications(filters = {}) {
    await delay()
    requirePermission('requests.read')
    const search = filters.search?.trim().toLowerCase()
    return structuredClone(
      db()
        .applications.filter((item) => {
          if (filters.status === 'active' && !ACTIVE.includes(item.status)) return false
          if (filters.status && filters.status !== 'active' && item.status !== filters.status) return false
          if (filters.productId && item.productId !== filters.productId) return false
          if (search) {
            const haystack = `${item.number} ${item.inn} ${item.applicantName} ${item.contactName}`.toLowerCase()
            if (!haystack.includes(search)) return false
          }
          return true
        })
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    )
  },

  async getApplication(id) {
    await delay(200)
    requirePermission('requests.read')
    return details(findApplication(id))
  },

  async rescore(id) {
    await delay(700)
    requirePermission('requests.update')
    const application = findApplication(id)
    const dossier = findDossier(application.inn)
    if (!dossier) throw new ApiError(404, 'not_found', 'Компания не найдена во внешних источниках')
    application.score = scoreDossier(dossier, application.amount, db().scoring)
    if (application.status === 'submitted') setStatus(application, 'checking', undefined, SYSTEM)
    if (application.status === 'checking') setStatus(application, 'scoring', 'Проверки пройдены, балл рассчитан', SYSTEM)
    application.updatedAt = new Date().toISOString()
    save()
    return details(application)
  },

  async decide(id, input) {
    await delay(500)
    requirePermission('requests.update')
    const application = findApplication(id)
    if (!['scoring', 'info_requested'].includes(application.status)) {
      throw new ApiError(409, 'conflict', 'Решение можно принять только по заявке на рассмотрении')
    }
    application.decision = { ...input, decidedBy: context.actor(), decidedAt: new Date().toISOString() }
    application.assignee ??= context.actor()
    setStatus(application, input.outcome, input.comment)
    save()
    return details(application)
  },

  async transition(id, transition) {
    await delay(400)
    requirePermission('requests.update')
    const application = findApplication(id)
    if (transition === 'to_signing') {
      if (!['approved', 'counter_offer'].includes(application.status)) {
        throw new ApiError(409, 'conflict', 'На подписание отправляем только одобренные заявки')
      }
      setStatus(application, 'signing', 'Договор отправлен клиенту на подписание')
    } else {
      if (application.status !== 'signing') throw new ApiError(409, 'conflict', 'Выдать можно только подписанную заявку')
      setStatus(application, 'issued', 'Деньги зачислены на расчётный счёт')
    }
    save()
    return details(application)
  },

  async assign(id) {
    await delay(250)
    requirePermission('requests.update')
    const application = findApplication(id)
    application.assignee = context.actor()
    application.updatedAt = new Date().toISOString()
    save()
    return details(application)
  },

  async getDashboard() {
    await delay()
    requirePermission('requests.read')
    return computeDashboard(db())
  },

  async lookupInn(inn, amount) {
    await delay(600)
    requirePermission('requests.read')
    const dossier = findDossier(inn)
    return dossier ? { dossier, score: scoreDossier(dossier, amount, db().scoring) } : null
  },

  async listProducts() {
    await delay()
    requirePermission('credits.read')
    return structuredClone(db().products)
  },

  async updateProduct(id, data) {
    await delay()
    requirePermission('credits.update')
    const product = productOf(db(), id)
    if (!product) throw new ApiError(404, 'not_found', 'Продукт не найден')
    if ((data.amountMin ?? product.amountMin) > (data.amountMax ?? product.amountMax)) {
      throw new ApiError(400, 'bad_request', 'Минимальная сумма больше максимальной')
    }
    if ((data.termMin ?? product.termMin) > (data.termMax ?? product.termMax)) {
      throw new ApiError(400, 'bad_request', 'Минимальный срок больше максимального')
    }
    Object.assign(product, data, { updatedAt: new Date().toISOString(), updatedBy: context.actor() })
    save()
    return structuredClone(product)
  },

  async getScoringConfig() {
    await delay(200)
    requirePermission('requests.read')
    return structuredClone(db().scoring)
  },

  async updateScoringConfig(config) {
    await delay()
    requirePermission('admin')
    if (config.counterFrom > config.approveFrom) {
      throw new ApiError(400, 'bad_request', 'Порог встречного предложения выше порога одобрения')
    }
    db().scoring = structuredClone(config)
    save()
    return structuredClone(config)
  },

  async previewScoring(config) {
    await delay(200)
    requirePermission('requests.read')
    const store = db()
    return store.applications.flatMap((application) => {
      const dossier = findDossier(application.inn)
      if (!dossier) return []
      const before = scoreDossier(dossier, application.amount, store.scoring)
      const after = scoreDossier(dossier, application.amount, config)
      return [
        {
          applicationId: application.id,
          number: application.number,
          applicantName: application.applicantName,
          before: { score: before.score, recommendation: before.recommendation },
          after: { score: after.score, recommendation: after.recommendation },
        },
      ]
    })
  },

  async resetDemoData() {
    await delay()
    requirePermission('admin')
    cached = seed()
    save()
  },
}
