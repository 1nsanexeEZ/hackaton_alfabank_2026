import type { ApplicationStatusCode } from '@/shared/api'

import type { ApplicationStatus } from './types'

/**
 * Статус заявки бэкенда (ApplicationOut.status) → статус для клиента, как client_status в BFF
 * (backend/src/modules/bff/application/client_status.py, docs/api/client-journey.md §3.6).
 * Клиенту показываем только клиентские статусы — их список в status.ts сверяет тест бэкенда.
 */
const BY_STATUS: Partial<Record<ApplicationStatusCode, ApplicationStatus>> = {
  draft: 'draft',
  submitted: 'submitted',
  info_requested: 'info_requested',
  signing: 'signing',
  signed: 'issued',
  disbursed: 'issued',
  rejected: 'rejected',
}

/** Этапы процесса, где банк уже оценивает риск: «Оцениваем…», «Подбираем условия», «Заявка у специалиста» */
const SCORING_STAGE_MARKERS = ['оцени', 'подбира', 'специалист']

/** null — статусов «отказ от предложения», «истекла» и «отменена» на сайте пока нет */
export function toClientStatus(
  status: ApplicationStatusCode,
  clientStage: string | null,
  offerKind: 'as_requested' | 'counter' | null = null,
): ApplicationStatus | null {
  if (status === 'in_review') {
    const stage = (clientStage ?? '').toLowerCase()
    return SCORING_STAGE_MARKERS.some((marker) => stage.includes(marker)) ? 'scoring' : 'checking'
  }
  if (status === 'offer_ready') return offerKind === 'counter' ? 'counter_offer' : 'approved'
  return BY_STATUS[status] ?? null
}
