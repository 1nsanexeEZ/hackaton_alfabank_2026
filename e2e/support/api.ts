import type { APIRequestContext } from '@playwright/test'

import { DEMO_PASSWORD, UNDERWRITER, type DemoAccount } from './accounts'

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

const bearer = (body: unknown): Headers => ({ Authorization: `Bearer ${(body as { access_token: string }).access_token}` })

async function login(request: APIRequestContext, account: DemoAccount): Promise<Headers> {
  const response = await request.post('/api/auth/login', { data: { login: account.login, password: DEMO_PASSWORD } })
  if (!response.ok()) {
    throw new Error(`Вход ${account.login} через API: ${response.status()} ${await response.text()}`)
  }
  return bearer(await response.json())
}

async function accountId(request: APIRequestContext, headers: Headers): Promise<string | null> {
  const response = await request.get('/api/me', { headers })
  return response.ok() ? ((await response.json()) as { id: string }).id : null
}

/**
 * Сотрудники, которые могут решить задачу, по id учётки: демо-учётки стенда (андеррайтер, затем админ) —
 * так решится и задача, которую кто-то из них уже взял. Демо-вход выключен — андеррайтер по паролю.
 */
async function staffSessions(request: APIRequestContext): Promise<Map<string, Headers>> {
  const sessions = new Map<string, Headers>()
  const listed = await request.get('/api/auth/demo-accounts')
  const staff = listed.ok() ? ((await listed.json()) as { login: string; role: string }[]).filter((item) => item.role !== 'client') : []
  for (const account of staff) {
    const response = await request.post('/api/auth/demo-login', { data: { login: account.login } })
    if (!response.ok()) continue
    const headers = bearer(await response.json())
    const id = await accountId(request, headers)
    if (id) sessions.set(id, headers)
  }
  if (!sessions.size) {
    const headers = await login(request, UNDERWRITER)
    const id = await accountId(request, headers)
    if (id) sessions.set(id, headers)
  }
  return sessions
}

interface QueueItem {
  task_id: string
  application_id: string
  assignee_id: string | null
}

/** Задача по заявке в очереди андеррайтера: status=open — и свободные, и уже взятые */
async function openTask(request: APIRequestContext, headers: Headers, applicationId: string): Promise<QueueItem | undefined> {
  const LIMIT = 100
  for (let offset = 0; ; offset += LIMIT) {
    const response = await request.get(`/api/bff/backoffice/queue?status=open&limit=${LIMIT}&offset=${offset}`, { headers })
    if (!response.ok()) return undefined
    const page = (await response.json()) as { items: QueueItem[]; total: number }
    const found = page.items.find((item) => item.application_id === applicationId)
    if (found || offset + LIMIT >= page.total) return found
  }
}

/**
 * Заявку на ручной проверке клиент закрыть не может — её решает андеррайтер, как в рабочем месте /admin:
 * берёт задачу и отказывает с комментарием. Взятую задачу решает тот, кто её взял, если это демо-учётка.
 * Задачи ещё нет (конвейер не дошёл) или её взял кто-то другой — ничего не делаем, следующий круг посмотрит снова.
 */
async function rejectByUnderwriter(request: APIRequestContext, sessions: Map<string, Headers>, applicationId: string): Promise<void> {
  const [first] = sessions.values()
  if (!first) return
  const task = await openTask(request, first, applicationId)
  if (!task) return
  const headers = task.assignee_id ? sessions.get(task.assignee_id) : first
  if (!headers) return
  if (!task.assignee_id) await request.post(`/api/tasks/${task.task_id}/claim`, { headers })
  await request.post(`/api/tasks/${task.task_id}/complete`, {
    headers,
    data: { decision: 'reject', comment: 'Закрыта перед e2e-тестом' },
  })
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
 * и мастер не даст подать новую. Закрываем, как закрыли бы клиент и банк: черновик и ждущее клиента
 * отменяем, начатое подписание доводим до выдачи, заявку на ручной проверке решает андеррайтер (отказ).
 * Пока конвейер решает сам или банк выдаёт (signed) — ждём.
 */
export async function closeActiveApplications(
  request: APIRequestContext,
  account: DemoAccount,
  productCode: string,
  timeoutMs = 90_000,
): Promise<void> {
  const headers = await login(request, account)
  let staff: Map<string, Headers> | undefined
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const active = await activeApplications(request, headers, productCode)
    if (!active.length) return
    if (Date.now() > deadline) {
      const list = active.map((item) => `№ ${item.number} (${item.status})`).join(', ')
      throw new Error(
        `У ${account.login} остались активные заявки по ${productCode}: ${list}. ` +
          'Задачу по ней, видимо, взял сотрудник не из демо-учёток — решите её в рабочем месте /admin и запустите тесты снова.',
      )
    }
    for (const item of active) {
      // Статус мог смениться между списком и действием — ответ не важен, следующий круг перечитает список
      if (CANCELLABLE.has(item.status)) {
        await request.post(`/api/applications/${item.id}/cancel`, { headers, data: { reason: 'Закрыта перед e2e-тестом' } })
      } else if (item.status === 'signing') {
        await sign(request, headers, item.id)
      } else if (item.status === 'in_review') {
        staff ??= await staffSessions(request)
        await rejectByUnderwriter(request, staff, item.id)
      }
    }
    await sleep(2_000)
  }
}

/**
 * Проверка учредителя стартапа уже пройдена и действует (30 дней): сбросить её через API нельзя,
 * поэтому сценарий «без проверки заявку не подать» идёт только на стенде, где её ещё не проходили.
 */
export async function founderPrescreenPassed(request: APIRequestContext, account: DemoAccount): Promise<boolean> {
  const headers = await login(request, account)
  const organizations = (await (await request.get('/api/organizations', { headers })).json()) as { id: string }[]
  const [organization] = organizations
  if (!organization) throw new Error(`У ${account.login} нет компании`)
  const response = await request.get(`/api/organizations/${organization.id}/founder-prescreen`, { headers })
  if (response.status() === 404) return false
  const prescreen = (await response.json()) as { status: string; valid: boolean }
  return prescreen.status === 'passed' && prescreen.valid
}

/**
 * Заявка через API, как её отправил бы мастер: условия, согласия, ответы по 115-ФЗ — для тестов рабочего места,
 * которым нужна поданная заявка, а не путь клиента. Документы не загружаем — подходит продукту без обязательных.
 */
export async function submitApplication(
  request: APIRequestContext,
  account: DemoAccount,
  terms: { productCode: string; amount: number; termMonths: number; beneficialOwner: string },
): Promise<{ id: string; number: string }> {
  const headers = await login(request, account)
  const [organization] = (await (await request.get('/api/organizations', { headers })).json()) as { id: string }[]
  if (!organization) throw new Error(`У ${account.login} нет компании`)
  const created = await request.post('/api/applications', {
    headers,
    data: { organization_id: organization.id, product_code: terms.productCode },
  })
  if (!created.ok()) throw new Error(`Черновик заявки: ${created.status()} ${await created.text()}`)
  const { id, number } = (await created.json()) as { id: string; number: string }
  const { version } = (await (await request.get(`/api/applications/${id}`, { headers })).json()) as { version: number }
  const updated = await request.patch(`/api/applications/${id}`, {
    headers,
    data: {
      version,
      request: { amount: String(terms.amount), term_months: terms.termMonths, purpose: 'working_capital' },
      consents: { personal_data: true, credit_bureau: true },
      beneficiary: { acts_for_third_party: false },
      beneficial_owners: { owners: [{ name: terms.beneficialOwner, basis: 'ownership', country: null }] },
    },
  })
  if (!updated.ok()) throw new Error(`Заполнение заявки: ${updated.status()} ${await updated.text()}`)
  const submitted = await request.post(`/api/applications/${id}/submit`, { headers })
  if (!submitted.ok()) throw new Error(`Отправка заявки: ${submitted.status()} ${await submitted.text()}`)
  return { id, number }
}
