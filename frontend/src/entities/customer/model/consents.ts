import { reactive, readonly, watch } from 'vue'

import { clientApi, type ConsentDto, type ConsentType } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

import { customer } from './session'

/**
 * Личные согласия человека (GET/POST /me/consents, DELETE /me/consents/{type}). Живут на аккаунте, а не
 * на заявке: кредитную историю руководителя по 218-ФЗ можно запросить только с его собственного согласия,
 * а заявку может заполнять бухгалтер. Без согласия руководителя по реестру банк его БКИ не запрашивает.
 */
/** Напоминание руководителю: банк рассматривает заявку компании, а его согласия на БКИ нет */
export interface ConsentReminder {
  applicationId: string
  number: string
  organizationName: string
}

const state = reactive<{ items: ConsentDto[] | null; loading: boolean; error: string | null; reminders: ConsentReminder[] }>({
  items: null,
  loading: false,
  error: null,
  reminders: [],
})

/** Для кого загружены согласия: сменился пользователь — список чужой */
let loadedFor: string | null = null
let pending: Promise<void> | null = null
/** Руководитель ли пользователь по реестру — по компании; ответ не меняется за сессию */
const registryHead = new Map<string, Promise<boolean>>()

watch(
  () => customer.state.me?.id ?? null,
  (id) => {
    if (id === loadedFor) return
    state.items = null
    state.error = null
    state.reminders = []
    loadedFor = null
    registryHead.clear()
    if (id) void loadReminders()
  },
  { immediate: true },
)

async function load(force = false): Promise<void> {
  const id = customer.state.me?.id ?? null
  if (!id) return
  if (!force && loadedFor === id && state.items) return
  if (pending && !force) return pending
  state.loading = true
  pending = (async () => {
    try {
      state.items = await clientApi.consents()
      state.error = null
      loadedFor = id
    } catch (caught) {
      state.error = errorMessage(caught)
    } finally {
      state.loading = false
      pending = null
    }
  })()
  return pending
}

/** Действующее согласие этого типа: не отозвано и не истекло */
function active(type: ConsentType): ConsentDto | null {
  return state.items?.find((item) => item.type === type && item.active) ?? null
}

async function give(types: ConsentType[]): Promise<void> {
  await clientApi.giveConsents(types)
  await Promise.all([load(true), loadReminders()])
}

/**
 * Пункты consent_required из Dashboard.todo по всем компаниям пользователя: бэк даёт их только руководителю
 * по реестру и только пока у компании есть заявка до решения. Компаний у клиента обычно одна-две.
 */
async function loadReminders(): Promise<void> {
  const id = customer.state.me?.id
  if (!id) return
  try {
    const organizations = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
    const dashboards = await Promise.all(organizations.map((item) => clientApi.dashboard(item.id).catch(() => null)))
    if (customer.state.me?.id !== id) return
    state.reminders = dashboards.flatMap((dashboard, index) =>
      (dashboard?.todo ?? [])
        .filter((todo) => todo.kind === 'consent_required')
        .map((todo) => ({ applicationId: todo.application_id, number: todo.number, organizationName: organizations[index]!.name })),
    )
  } catch {
    // Напоминание — подсказка, а не блокер: не загрузилось — не показываем
  }
}

async function revoke(type: ConsentType): Promise<void> {
  await clientApi.revokeConsent(type)
  // Заявка ещё у банка — без согласия напоминание вернётся
  await Promise.all([load(true), loadReminders()])
}

/**
 * Руководитель ли текущий пользователь по реестру (authority = registry): только он даёт согласие на
 * свою кредитную историю, и только его БКИ банк запрашивает по заявкам компании.
 */
function isRegistryHead(organizationId: string): Promise<boolean> {
  const me = customer.state.me?.id
  if (!me) return Promise.resolve(false)
  let answer = registryHead.get(organizationId)
  if (!answer) {
    answer = clientApi
      .members(organizationId)
      .then((members) => members.some((member) => member.account_id === me && member.authority === 'registry'))
      .catch(() => false)
    registryHead.set(organizationId, answer)
  }
  return answer
}

export const personalConsents = {
  state: readonly(state),
  load,
  active,
  give,
  revoke,
  isRegistryHead,
  loadReminders,
}

/** Тексты согласий — та же редакция, что фиксирует бэкенд (identity: pd-2026-10, bki-fl-2026-10) */
export const CONSENT_TEXT: Record<ConsentType, { title: string; validity: string; body: string }> = {
  personal_data: {
    title: 'Обработка моих персональных данных',
    validity: 'бессрочно, до отзыва',
    body:
      'По ст. 9 Федерального закона № 152-ФЗ «О персональных данных» я даю банку согласие на обработку моих ' +
      'персональных данных: ФИО, должность, контакты, сведения из ЕГРЮЛ/ЕГРИП и ФНС — для рассмотрения заявок ' +
      'компаний, в которых я участвую, и сопровождения кредитов. Согласие действует до отзыва.',
  },
  credit_bureau_personal: {
    title: 'Запрос моей кредитной истории',
    validity: '6 месяцев',
    body:
      'По ст. 6 Федерального закона № 218-ФЗ «О кредитных историях» я разрешаю банку получить мой кредитный ' +
      'отчёт как физического лица в бюро кредитных историй, чтобы оценить платёжную дисциплину руководителя при ' +
      'рассмотрении заявок компании. Согласие действует 6 месяцев; его можно отозвать в профиле — запросы, ' +
      'уже сделанные по заявкам, отзыв не отменяет.',
  },
}
