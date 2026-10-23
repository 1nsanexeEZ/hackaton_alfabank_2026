import type { ClientStatus } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

import type { ApplicationStatus } from './types'

export const APPLICATION_STATUS_META: Record<ApplicationStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'neutral' },
  submitted: { label: 'Отправлена', tone: 'info' },
  checking: { label: 'Проверка данных', tone: 'info' },
  scoring: { label: 'Оценка риска', tone: 'info' },
  info_requested: { label: 'Нужны данные', tone: 'warning' },
  approved: { label: 'Одобрена', tone: 'success' },
  counter_offer: { label: 'Другие условия', tone: 'warning' },
  rejected: { label: 'Отказ', tone: 'brand' },
  signing: { label: 'Подписание', tone: 'info' },
  issued: { label: 'Кредит выдан', tone: 'success' },
}

/** Статусы клиента из BFF (`client_status`): те же, плюс закрытые без решения банка */
export const CLIENT_STATUS_META: Record<ClientStatus, { label: string; tone: BadgeTone }> = {
  ...APPLICATION_STATUS_META,
  cancelled: { label: 'Отменена', tone: 'neutral' },
  declined: { label: 'Вы отказались', tone: 'neutral' },
  expired: { label: 'Предложение истекло', tone: 'neutral' },
}

/** Заявка закрыта: по продукту можно подавать новую */
export const CLOSED_CLIENT_STATUSES: readonly ClientStatus[] = ['rejected', 'issued', 'cancelled', 'declined', 'expired']

/** Что ждёт от клиента банк (`action_required` строки BFF); none — ничего */
export const ACTION_REQUIRED_LABEL: Record<string, string> = {
  info: 'Банку нужны данные',
  offer: 'Готово предложение',
  sign: 'Подпишите договор',
}

/** Названия документов по типу: банк может запросить и то, чего нет в требованиях продукта */
export const DOCUMENT_TITLE: Record<string, string> = {
  financial_report: 'Бухгалтерская отчётность за последний год',
  financial_statement: 'Финансовая отчётность',
  tax_return: 'Налоговая декларация за последний год',
  bank_statement: 'Выписка по расчётному счёту за 6 месяцев (CSV)',
  collateral_documents: 'Документы на залог: право собственности и оценка',
  purchase_contract: 'Договор купли-продажи или счёт продавца',
  existing_loans_statement: 'Справка о действующих кредитах: остаток долга и график',
  business_plan: 'Бизнес-план',
  financial_model: 'Финансовая модель',
  other: 'Другой документ',
}
