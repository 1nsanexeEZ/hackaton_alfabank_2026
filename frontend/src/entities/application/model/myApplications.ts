import { reactive, readonly } from 'vue'

import { clientApi, type ApplicationStatusCode, type ApplicationSummaryDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Заявка закрыта: по продукту можно подавать новую, на первом экране её не показываем */
const FINAL_STATUSES: readonly ApplicationStatusCode[] = ['disbursed', 'rejected', 'offer_declined', 'expired', 'cancelled']

export interface MyApplication extends ApplicationSummaryDto {
  organization_name: string | null
}

/**
 * Активные заявки вошедшего клиента по всем его компаниям, свежие первыми. Загружает тот,
 * кто знает про вход (первый экран), перезагружает тот, кто меняет заявки (мастер заявки).
 */
const state = reactive<{ items: MyApplication[] | null; loading: boolean; error: string | null }>({
  items: null,
  loading: false,
  error: null,
})

// Ответ старого запроса (например, до выхода из учётки) не должен перезаписать новый
let requestId = 0

async function load(): Promise<void> {
  const id = ++requestId
  state.loading = true
  state.error = null
  try {
    const [applications, organizations] = await Promise.all([
      clientApi.listApplications(100),
      clientApi.listOrganizations(),
    ])
    if (id !== requestId) return
    const names = new Map(organizations.map((item) => [item.id, item.name]))
    state.items = applications
      .filter((item) => !FINAL_STATUSES.includes(item.status))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map((item) => ({ ...item, organization_name: names.get(item.organization_id) ?? null }))
  } catch (caught) {
    if (id !== requestId) return
    state.error = errorMessage(caught)
  } finally {
    if (id === requestId) state.loading = false
  }
}

/** Вышел из учётки — чужие заявки на экране не оставляем */
function clear(): void {
  requestId++
  state.items = null
  state.loading = false
  state.error = null
}

/** Перезагрузить, только если список уже показывали: без входа загружать нечего */
async function refresh(): Promise<void> {
  if (state.items || state.error) await load()
}

export const myApplications = {
  state: readonly(state),
  load,
  clear,
  refresh,
}
