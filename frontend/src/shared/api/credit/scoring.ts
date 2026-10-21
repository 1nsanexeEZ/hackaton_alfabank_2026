import { dossierRegistrationDate, dossierStatus, type Dossier, type GirBoPeriod } from './sources'
import type { RiskClass, ScoreFactor, ScoreResult, ScoringConfig, ScoringFactorId, StopFactorId } from './types'

/**
 * Объяснимый скоринг: базовые 50 баллов, каждый фактор добавляет или снимает баллы,
 * вес из настроек усиливает или ослабляет фактор. Стоп-факторы ведут к отказу при любом балле.
 * Так считал бы сервис скоринга на бэкенде; здесь он работает внутри мока.
 */
const BASE_SCORE = 50

export const DEFAULT_SCORING_CONFIG: ScoringConfig = {
  weights: {
    business_age: 1,
    revenue_growth: 1,
    profitability: 1,
    debt_load: 1,
    tax_discipline: 1,
    litigation: 1,
    enforcement: 1,
    reliability: 1,
    loan_to_revenue: 1,
  },
  stopFactors: {
    inactive: true,
    bankruptcy: true,
    account_blocks: true,
    negative_equity: true,
    disqualified: true,
    large_enforcement: true,
  },
  approveFrom: 70,
  counterFrom: 45,
  counterAmountPercent: 60,
}

export const SCORING_FACTOR_LABEL: Record<ScoringFactorId, string> = {
  business_age: 'Возраст бизнеса',
  revenue_growth: 'Динамика выручки',
  profitability: 'Рентабельность',
  debt_load: 'Долговая нагрузка',
  tax_discipline: 'Налоговая дисциплина',
  litigation: 'Арбитражные споры',
  enforcement: 'Исполнительные производства',
  reliability: 'Оценка надёжности Контура',
  loan_to_revenue: 'Сумма кредита к выручке',
}

export const STOP_FACTOR_LABEL: Record<StopFactorId, string> = {
  inactive: 'Компания или ИП не действует',
  bankruptcy: 'Процедура банкротства',
  account_blocks: 'Приостановлены операции по счетам',
  negative_equity: 'Отрицательные чистые активы',
  disqualified: 'Дисквалифицированные лица в руководстве',
  large_enforcement: 'Исполнительные производства больше 5 млн ₽',
}

/** Доля выручки, которую бизнес платит налогом, — чтобы оценить выручку ИП по уплаченным налогам */
const TAX_TO_REVENUE: Record<string, number> = {
  'УСН (доходы)': 0.05,
  'УСН (доходы минус расходы)': 0.035,
  ОСНО: 0.06,
  ПСН: 0.008,
  АУСН: 0.06,
}

const ACTIVE_STATUSES = ['Действующее', 'Действующий']
const LARGE_ENFORCEMENT_RUB = 5_000_000

const MS_IN_YEAR = 365.25 * 24 * 3600 * 1000

function yearsSince(date: string, now: Date): number {
  return (now.getTime() - new Date(date).getTime()) / MS_IN_YEAR
}

function lastPeriods(dossier: Dossier): [GirBoPeriod | undefined, GirBoPeriod | undefined] {
  const periods = [...dossier.gir_bo.periods].sort((a, b) => a.year - b.year)
  return [periods.at(-2), periods.at(-1)]
}

/** Годовая выручка, ₽: из ГИР БО, а для ИП — оценка по уплаченным налогам */
export function estimateRevenue(dossier: Dossier): number {
  const [, last] = lastPeriods(dossier)
  if (last) return last.income['2110_revenue'] * 1000
  const rate = TAX_TO_REVENUE[dossier.fns.tax_regime] ?? 0.05
  const paid = Math.max(0, ...dossier.fns.taxes_paid.map((item) => item.paid_rub))
  return paid / rate
}

const percent = (value: number) => `${value > 0 ? '+' : ''}${Math.round(value * 100)}%`

function formatYears(years: number): string {
  if (years < 1) return `${Math.max(1, Math.round(years * 12))} мес.`
  return `${Math.floor(years)} г.`
}

/** Шкала: первое подходящее условие даёт баллы */
function pick(steps: [boolean, number][], fallback: number): number {
  return steps.find(([matches]) => matches)?.[1] ?? fallback
}

function collectFactors(dossier: Dossier, amount: number, now: Date): Omit<ScoreFactor, 'label'>[] {
  const factors: Omit<ScoreFactor, 'label'>[] = []
  const age = yearsSince(dossierRegistrationDate(dossier), now)
  factors.push({
    id: 'business_age',
    impact: pick([[age >= 5, 12], [age >= 3, 8], [age >= 1, 2]], -12),
    detail: `работает ${formatYears(age)}`,
  })

  const [prev, last] = lastPeriods(dossier)
  if (prev && last && prev.income['2110_revenue'] > 0) {
    const growth = last.income['2110_revenue'] / prev.income['2110_revenue'] - 1
    factors.push({
      id: 'revenue_growth',
      impact: pick([[growth >= 0.1, 8], [growth >= 0, 3], [growth >= -0.2, -4]], -12),
      detail: `выручка ${percent(growth)} за год`,
    })
  }

  if (last && last.income['2110_revenue'] > 0) {
    const margin = last.income['2400_net_profit'] / last.income['2110_revenue']
    factors.push({
      id: 'profitability',
      impact: pick([[margin >= 0.08, 8], [margin >= 0.03, 4], [margin >= 0, 0]], -14),
      detail: `чистая маржа ${percent(margin)}`,
    })
  }

  if (last && last.balance['1600_total_assets'] > 0) {
    const debt =
      (last.balance['1400_long_term_liabilities'] + last.balance['1500_short_term_liabilities']) /
      last.balance['1600_total_assets']
    factors.push({
      id: 'debt_load',
      impact: pick([[debt <= 0.5, 6], [debt <= 0.75, 0], [debt <= 0.9, -6]], -12),
      detail: `обязательства — ${Math.round(debt * 100)}% активов`,
    })
  }

  const arrears = dossier.fns.tax_arrears_rub
  factors.push({
    id: 'tax_discipline',
    impact: arrears > 0 ? -12 : 4,
    detail: arrears > 0 ? `недоимка ${Math.round(arrears / 1000)} тыс. ₽` : 'недоимки нет',
  })

  const cases = dossier.kontur.arbitration.as_defendant
  factors.push({
    id: 'litigation',
    impact: pick([[cases === 0, 2], [cases <= 3, -4], [cases <= 10, -8]], -14),
    detail: cases === 0 ? 'нет дел в роли ответчика' : `ответчик в ${cases} делах`,
  })

  const enforcement = dossier.kontur.enforcement_proceedings.active
  factors.push({
    id: 'enforcement',
    impact: pick([[enforcement === 0, 2], [enforcement <= 2, -4]], -14),
    detail: enforcement === 0 ? 'нет производств' : `${enforcement} активных`,
  })

  const reliability = dossier.kontur.reliability
  factors.push({
    id: 'reliability',
    impact: { green: 6, yellow: -4, red: -14 }[reliability],
    detail: { green: 'зелёная', yellow: 'жёлтая', red: 'красная' }[reliability],
  })

  const revenue = estimateRevenue(dossier)
  const ratio = revenue > 0 ? amount / revenue : Infinity
  factors.push({
    id: 'loan_to_revenue',
    impact: pick([[ratio <= 0.15, 6], [ratio <= 0.3, 2], [ratio <= 0.5, -6]], -14),
    detail: Number.isFinite(ratio) ? `${Math.round(ratio * 100)}% годовой выручки` : 'выручки нет',
  })

  return factors
}

function collectStopFactors(dossier: Dossier): StopFactorId[] {
  const [, last] = lastPeriods(dossier)
  const status = dossierStatus(dossier)
  const found: [StopFactorId, boolean][] = [
    ['inactive', !ACTIVE_STATUSES.includes(status) && !status.toLowerCase().includes('банкрот')],
    ['bankruptcy', dossier.kontur.bankruptcy_messages.length > 0 || status.toLowerCase().includes('банкрот')],
    ['account_blocks', dossier.fns.account_blocks.length > 0],
    ['negative_equity', Boolean(last && last.balance['1300_equity'] < 0)],
    ['disqualified', dossier.fns.disqualified_persons],
    ['large_enforcement', dossier.kontur.enforcement_proceedings.sum_rub > LARGE_ENFORCEMENT_RUB],
  ]
  return found.filter(([, matches]) => matches).map(([id]) => id)
}

function collectMissingData(dossier: Dossier, now: Date): string[] {
  const missing: string[] = []
  if (dossier.kind === 'company' && !dossier.gir_bo.available) {
    missing.push('Нет отчётности в ГИР БО — запросить управленческую отчётность и выписку по счёту')
  }
  if (dossier.kind === 'entrepreneur' && yearsSince(dossier.egrip.registration_date, now) < 0.5) {
    missing.push('ИП работает меньше 6 месяцев — запросить выписку по счёту')
  }
  for (const item of dossier.fns.unreliable_data) {
    missing.push(`В ЕГРЮЛ отметка о недостоверности: ${item === 'address' ? 'адрес' : item} — запросить подтверждение`)
  }
  return missing
}

function riskClass(score: number): RiskClass {
  if (score >= 75) return 'A'
  if (score >= 60) return 'B'
  if (score >= 45) return 'C'
  return 'D'
}

export function scoreDossier(dossier: Dossier, amount: number, config: ScoringConfig, now = new Date()): ScoreResult {
  const factors = collectFactors(dossier, amount, now).map((factor) => ({
    ...factor,
    label: SCORING_FACTOR_LABEL[factor.id],
    impact: Math.round(factor.impact * config.weights[factor.id]),
  }))
  const score = Math.min(100, Math.max(0, BASE_SCORE + factors.reduce((sum, factor) => sum + factor.impact, 0)))
  const stopFactors = collectStopFactors(dossier)
    .filter((id) => config.stopFactors[id])
    .map((id) => STOP_FACTOR_LABEL[id])
  const missingData = collectMissingData(dossier, now)

  let recommendation: ScoreResult['recommendation']
  if (stopFactors.length) recommendation = 'rejected'
  else if (missingData.length) recommendation = 'info_requested'
  else if (score >= config.approveFrom) recommendation = 'approved'
  else if (score >= config.counterFrom) recommendation = 'counter_offer'
  else recommendation = 'rejected'

  const suggestedAmount =
    recommendation === 'counter_offer' ? Math.round((amount * config.counterAmountPercent) / 100 / 10_000) * 10_000 : null

  return {
    score,
    riskClass: riskClass(score),
    factors: factors.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact)),
    stopFactors,
    missingData,
    recommendation,
    suggestedAmount,
    calculatedAt: now.toISOString(),
  }
}
