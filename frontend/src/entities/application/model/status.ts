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
