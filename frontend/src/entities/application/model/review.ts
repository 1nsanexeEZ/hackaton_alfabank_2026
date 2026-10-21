import type { AdminApplication, ApplicationStatus, DecisionOutcome, RiskClass } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

/** Рассмотрение заявки сотрудником банка: исходы решения, классы риска, сроки */
export const DECISION_OUTCOME_META: Record<DecisionOutcome, { label: string; action: string; tone: BadgeTone }> = {
  approved: { label: 'Одобрить', action: 'Одобрена', tone: 'success' },
  counter_offer: { label: 'Другие условия', action: 'Встречное предложение', tone: 'warning' },
  info_requested: { label: 'Запросить данные', action: 'Запрошены данные', tone: 'info' },
  rejected: { label: 'Отказать', action: 'Отказ', tone: 'brand' },
}

export const RISK_CLASS_META: Record<RiskClass, { label: string; tone: BadgeTone; color: string }> = {
  A: { label: 'Низкий риск', tone: 'success', color: 'var(--color-success)' },
  B: { label: 'Умеренный риск', tone: 'info', color: 'var(--color-info)' },
  C: { label: 'Повышенный риск', tone: 'warning', color: 'var(--color-warning)' },
  D: { label: 'Высокий риск', tone: 'brand', color: 'var(--color-brand)' },
}

/** Заявки, которые ждут действий банка, — очередь аналитика */
export const ACTIVE_STATUSES: readonly ApplicationStatus[] = ['submitted', 'checking', 'scoring']

export function isActive(application: Pick<AdminApplication, 'status'>): boolean {
  return ACTIVE_STATUSES.includes(application.status)
}

export function isOverdue(application: Pick<AdminApplication, 'status' | 'dueAt'>, now = Date.now()): boolean {
  return isActive(application) && Date.parse(application.dueAt) < now
}

/** Надбавка к базовой ставке продукта за риск, п. п. — подсказка аналитику при выборе ставки */
export const RISK_RATE_PREMIUM: Record<RiskClass, number> = { A: 0, B: 1.5, C: 3, D: 5 }
