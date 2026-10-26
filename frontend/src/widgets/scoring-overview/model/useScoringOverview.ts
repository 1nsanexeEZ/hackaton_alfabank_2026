import { shallowRef } from 'vue'

import { backofficeApi, type ScoringOverviewDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Сколько последних поданных заявок показываем строками: счётчики бэкенд считает по всем до 1000 */
const LIMIT = 50

/**
 * Скоринг по заявкам одной ручкой (GET /bff/backoffice/scoring-overview): счётчики, грейды обеих моделей,
 * матрица зон и версии бэкенд считает сам, а строками отдаёт последние поданные заявки.
 */
export function useScoringOverview() {
  const data = shallowRef<ScoringOverviewDto | null>(null)
  const loading = shallowRef(true)
  const error = shallowRef<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      data.value = await backofficeApi.scoringOverview(LIMIT)
    } catch (caught) {
      error.value = errorMessage(caught)
    } finally {
      loading.value = false
    }
  }

  void load()
  return { data, loading, error, reload: load }
}
