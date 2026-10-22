import { reactive, readonly } from 'vue'

import { clientApi, type ApplicationRowDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

import { CLOSED_CLIENT_STATUSES } from './status'

export interface MyApplication extends ApplicationRowDto {
  organization_id: string
  organization_name: string
}

/**
 * Заявки вошедшего клиента по всем его компаниям, свежие первыми — строки BFF
 * (`GET /bff/applications`): клиентский статус, этап и «что ждёт банк» считает бэкенд.
 * Загружает тот, кто знает про вход (первый экран), перезагружает тот, кто меняет заявки.
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
    // Сотрудник банка видит все компании, но не участник ни одной — у клиента только свои
    const [all, plain] = await Promise.all([clientApi.listOrganizations(), clientApi.listApplications(100)])
    const organizations = all.filter((item) => item.my_role !== null)
    const lists = await Promise.all(
      organizations.map(async (organization) =>
        (await clientApi.listApplicationRows(organization.id, 100)).items.map((row) => ({
          ...row,
          organization_id: organization.id,
          organization_name: organization.name,
        })),
      ),
    )
    if (id !== requestId) return
    const rows: MyApplication[] = lists.flat()
    // Модель чтения BFF строится по событиям подачи — черновиков в ней нет, берём их из GET /applications
    const known = new Set(rows.map((row) => row.id))
    const names = new Map(organizations.map((organization) => [organization.id, organization.name]))
    for (const draft of plain) {
      const organizationName = names.get(draft.organization_id)
      if (draft.status !== 'draft' || known.has(draft.id) || !organizationName) continue
      rows.push({
        ...draft,
        product_name: '',
        client_status: 'draft',
        action_required: 'none',
        offer_amount: null,
        offer_rate: null,
        organization_name: organizationName,
      })
    }
    state.items = rows.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
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

/** Заявка ещё в работе: черновик, рассмотрение, предложение, подписание */
export function isActiveApplication(item: Pick<ApplicationRowDto, 'client_status'>): boolean {
  return !CLOSED_CLIENT_STATUSES.includes(item.client_status)
}

export const myApplications = {
  state: readonly(state),
  load,
  clear,
  refresh,
}
