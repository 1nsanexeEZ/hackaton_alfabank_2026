import type { ApplicationStatusCode } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

import type { ApplicationStatus } from './types'

/** Статусы заявки на бэкенде (ApplicationOut.status) — для клиентских экранов */
export const SERVER_STATUS_META: Record<ApplicationStatusCode, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'neutral' },
  submitted: { label: 'Отправлена', tone: 'info' },
  in_review: { label: 'На рассмотрении', tone: 'info' },
  info_requested: { label: 'Нужны данные', tone: 'warning' },
  offer_ready: { label: 'Готово предложение', tone: 'success' },
  signing: { label: 'Подписание', tone: 'info' },
  signed: { label: 'Подписана', tone: 'success' },
  disbursed: { label: 'Кредит выдан', tone: 'success' },
  rejected: { label: 'Отказ', tone: 'brand' },
  offer_declined: { label: 'Предложение отклонено', tone: 'neutral' },
  expired: { label: 'Срок истёк', tone: 'neutral' },
  cancelled: { label: 'Отменена', tone: 'neutral' },
}

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
