import { shallowRef } from 'vue'

import { backofficeApi, type ApplicationStatusCode, type StaffApplicationDto, type UnderwriterCardDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Сколько последних поданных заявок разбираем и сколько карточек грузим одновременно */
const LIMIT = 50
const PARALLEL = 6
/** Всё, кроме черновика: черновики не оценивались */
const SUBMITTED: ApplicationStatusCode[] = [
  'submitted',
  'in_review',
  'info_requested',
  'offer_ready',
  'signing',
  'signed',
  'disbursed',
  'rejected',
  'offer_declined',
  'expired',
  'cancelled',
]

export interface ScoredApplication {
  application: StaffApplicationDto
  card: UnderwriterCardDto
}

/**
 * Скоринг по заявкам: отдельной ручки со сводкой нет, поэтому берём последние поданные заявки
 * (GET /applications) и их карточки (GET /bff/backoffice/applications/{id}) — там оценки обеих
 * моделей, качество данных и решение. Черновики не оценивались — бэкенд их не отдаёт (status).
 */
export function useScoredApplications() {
  const items = shallowRef<ScoredApplication[]>([])
  const total = shallowRef(0)
  const loading = shallowRef(true)
  const error = shallowRef<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const submitted = await backofficeApi.applications({ status: SUBMITTED, limit: LIMIT })
      total.value = submitted.length
      const loaded: ScoredApplication[] = []
      for (let index = 0; index < submitted.length; index += PARALLEL) {
        const batch = submitted.slice(index, index + PARALLEL)
        const cards = await Promise.all(batch.map((item) => backofficeApi.card(item.id).catch(() => null)))
        batch.forEach((application, position) => {
          const card = cards[position]
          if (card) loaded.push({ application, card })
        })
        items.value = [...loaded]
      }
    } catch (caught) {
      error.value = errorMessage(caught)
    } finally {
      loading.value = false
    }
  }

  void load()
  return { items, total, loading, error, reload: load }
}
