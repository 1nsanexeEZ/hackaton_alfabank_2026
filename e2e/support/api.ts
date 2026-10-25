import type { APIRequestContext } from '@playwright/test'

import { DEMO_PASSWORD, type DemoAccount } from './accounts'

/**
 * Подготовка стенда через API — то же, что клиент сделал бы в кабинете руками.
 * Интерфейс проверяют сами тесты, здесь только приводим данные к исходному состоянию.
 */

type Headers = Record<string, string>

interface ApplicationItem {
  id: string
  number: string
  product_code: string
  status: string
}

/** Не финальные статусы: пока заявка в одном из них, второй по тому же продукту у компании не будет */
const ACTIVE_STATUSES = ['draft', 'submitted', 'in_review', 'info_requested', 'offer_ready', 'signing', 'signed']
/** Отсюда клиент может отменить заявку сам */
const CANCELLABLE = new Set(['draft', 'submitted', 'info_requested', 'offer_ready'])

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

async function login(request: APIRequestContext, account: DemoAccount): Promise<Headers> {
  const response = await request.post('/api/auth/login', { data: { login: account.login, password: DEMO_PASSWORD } })
  if (!response.ok()) {
    throw new Error(`Вход ${account.login} через API: ${response.status()} ${await response.text()}`)
  }
  const { access_token: token } = (await response.json()) as { access_token: string }
  return { Authorization: `Bearer ${token}` }
}

async function activeApplications(request: APIRequestContext, headers: Headers, productCode: string) {
  const query = new URLSearchParams([...ACTIVE_STATUSES.map((status) => ['status', status]), ['limit', '100']])
  const response = await request.get(`/api/applications?${query}`, { headers })
  if (!response.ok()) throw new Error(`Список заявок: ${response.status()} ${await response.text()}`)
  const items = (await response.json()) as ApplicationItem[]
  return items.filter((item) => item.product_code === productCode)
}

/** Начатое подписание доводим до конца, как клиент: тот же пароль, хеш условий, проекта PDF и версия Правил */
async function sign(request: APIRequestContext, headers: Headers, id: string): Promise<void> {
  const contract = (await (await request.get(`/api/applications/${id}/contract`, { headers })).json()) as {
    offer_hash: string
    status: string
    document: { kind: string; status: string; sha256: string | null } | null
  }
  if (contract.status !== 'unsigned') return
  const draft = contract.document
  // PDF ещё формируется — подпишем на следующем круге
  if (draft && !(draft.kind === 'draft' && draft.status === 'ready' && draft.sha256)) return
  const rules = (await (await request.get('/api/esign/rules', { headers })).json()) as { version: string }
  await request.post(`/api/applications/${id}/sign`, {
    headers,
    data: {
      password: DEMO_PASSWORD,
      offer_hash: contract.offer_hash,
      document_hash: draft?.sha256 ?? null,
      rules_version: rules.version,
    },
  })
}

/**
 * У компании одна активная заявка на продукт: прошлый прогон или проверка руками могли её оставить,
 * и мастер не даст подать новую. Закрываем, как закрыл бы клиент: отменяем, а начатое подписание
 * доводим до выдачи. Пока банк решает (in_review) или выдаёт (signed) — ждём.
 */
export async function closeActiveApplications(
  request: APIRequestContext,
  account: DemoAccount,
  productCode: string,
  timeoutMs = 90_000,
): Promise<void> {
  const headers = await login(request, account)
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const active = await activeApplications(request, headers, productCode)
    if (!active.length) return
    if (Date.now() > deadline) {
      const list = active.map((item) => `№ ${item.number} (${item.status})`).join(', ')
      throw new Error(
        `У ${account.login} остались активные заявки по ${productCode}: ${list}. ` +
          'Скорее всего, заявка ждёт андеррайтера — решите её в рабочем месте /admin и запустите тесты снова.',
      )
    }
    for (const item of active) {
      // Статус мог смениться между списком и действием — ответ не важен, следующий круг перечитает список
      if (CANCELLABLE.has(item.status)) {
        await request.post(`/api/applications/${item.id}/cancel`, { headers, data: { reason: 'Закрыта перед e2e-тестом' } })
      } else if (item.status === 'signing') {
        await sign(request, headers, item.id)
      }
    }
    await sleep(2_000)
  }
}
