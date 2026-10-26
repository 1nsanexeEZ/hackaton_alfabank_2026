import type { ApplicationStatusCode } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

export const STATUS: Record<ApplicationStatusCode, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'neutral' },
  submitted: { label: 'Подана', tone: 'info' },
  in_review: { label: 'На рассмотрении', tone: 'info' },
  info_requested: { label: 'Запрос данных', tone: 'warning' },
  offer_ready: { label: 'Предложение', tone: 'success' },
  signing: { label: 'Подписание', tone: 'info' },
  signed: { label: 'Подписана', tone: 'success' },
  disbursed: { label: 'Кредит выдан', tone: 'success' },
  rejected: { label: 'Отказ', tone: 'brand' },
  offer_declined: { label: 'Клиент отказался', tone: 'neutral' },
  expired: { label: 'Истекла', tone: 'neutral' },
  cancelled: { label: 'Отменена', tone: 'neutral' },
}

/** Группы статусов для «Где заявки сейчас» */
export const STATUS_GROUPS: readonly { label: string; color: string; statuses: readonly ApplicationStatusCode[] }[] = [
  { label: 'Черновики', color: 'var(--color-surface-strong)', statuses: ['draft'] },
  { label: 'На рассмотрении', color: 'var(--color-info)', statuses: ['submitted', 'in_review', 'info_requested'] },
  { label: 'Одобрены и подписание', color: 'var(--color-success)', statuses: ['offer_ready', 'signing', 'signed'] },
  { label: 'Кредит выдан', color: 'var(--color-night)', statuses: ['disbursed'] },
  { label: 'Отказ', color: 'var(--color-brand)', statuses: ['rejected'] },
  { label: 'Закрыты без выдачи', color: 'var(--color-warning)', statuses: ['offer_declined', 'expired', 'cancelled'] },
]

/**
 * Подписи этапов воронки. Сколько заявок ДОШЛИ до этапа (не где они сейчас), считает бэкенд:
 * отказ тоже прошёл «Решение», отказ клиента и истёкшее предложение были одобрены.
 */
export const FUNNEL_LABEL: Record<string, string> = {
  started: 'Начаты',
  submitted: 'Поданы',
  decided: 'Решение банка',
  approved: 'Одобрены',
  signed: 'Подписаны',
  disbursed: 'Кредит выдан',
}

/** Шаги мини-трекера в ленте — как у клиента: подача, решение, подписание, выдача */
export const TRACK = ['Подана', 'Решение', 'Подписание', 'Выдача'] as const

/** Сколько шагов трекера пройдено; rejected — решение есть, дальше дороги нет */
export function trackProgress(status: ApplicationStatusCode): { done: number; failed: boolean } {
  switch (status) {
    case 'draft':
      return { done: 0, failed: false }
    case 'submitted':
    case 'in_review':
    case 'info_requested':
      return { done: 1, failed: false }
    case 'offer_ready':
    case 'signing':
    case 'offer_declined':
    case 'expired':
      return { done: 2, failed: false }
    case 'signed':
      return { done: 3, failed: false }
    case 'disbursed':
      return { done: 4, failed: false }
    case 'rejected':
      return { done: 2, failed: true }
    case 'cancelled':
      return { done: 0, failed: true }
  }
}
