import { computed, reactive, readonly } from 'vue'

import {
  assistantApi,
  AssistantError,
  type AssistantApplicationDto,
  type AssistantErrorKind,
  type AssistantMode,
} from '@/shared/api'

/** Длина вопроса, которую принимает сервис (docs/assistant-api.md) */
export const ASSISTANT_MAX_QUESTION = 1000

/** Как часто перепроверяем статус, пока страница открыта */
const STATUS_POLL_MS = 60_000

const CONVERSATION_KEY = 'assistant:conversation'

/** unknown — статус ещё не получен; off — сервис не ответил за 3 с или недоступен */
export type AssistantAvailability = 'unknown' | 'llm' | 'rules' | 'off'

/** Подпись состояния для подзаголовка окна и подсказки кнопки */
export const ASSISTANT_AVAILABILITY_LABEL: Record<AssistantAvailability, string> = {
  unknown: 'Проверяем доступность',
  llm: 'ИИ отвечает',
  rules: 'Отвечает по шаблонам',
  off: 'Недоступен',
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  /** Чем отвечено: модель или шаблон; у вопросов клиента null */
  mode: AssistantMode | null
  applicationId: string | null
  /** Ответ ещё приходит: пока текста нет, помощник «думает» */
  streaming?: boolean
  /** Вопрос остался без ответа: ошибка, можно повторить */
  failed?: boolean
}

export interface ChatError {
  kind: AssistantErrorKind
  message: string
  retryAfter: number | null
}

const state = reactive<{
  open: boolean
  availability: AssistantAvailability
  applications: AssistantApplicationDto[]
  applicationId: string | null
  conversationId: string | null
  messages: ChatMessage[]
  /** Идёт ответ на вопрос */
  busy: boolean
  /** Загружаем заявки и историю диалога */
  loading: boolean
  error: ChatError | null
}>({
  open: false,
  availability: 'unknown',
  applications: [],
  applicationId: null,
  conversationId: readConversationId(),
  messages: [],
  busy: false,
  loading: false,
  error: null,
})

function readConversationId(): string | null {
  try {
    return sessionStorage.getItem(CONVERSATION_KEY)
  } catch {
    return null
  }
}

function storeConversationId(id: string | null): void {
  state.conversationId = id
  try {
    if (id) sessionStorage.setItem(CONVERSATION_KEY, id)
    else sessionStorage.removeItem(CONVERSATION_KEY)
  } catch {
    // Хранилище недоступно — диалог просто не переживёт перезагрузку
  }
}

function toChatError(cause: unknown): ChatError {
  if (cause instanceof AssistantError) return { kind: cause.kind, message: cause.message, retryAfter: cause.retryAfter }
  return { kind: 'unavailable', message: 'Помощник временно недоступен', retryAfter: null }
}

let localId = 0
const nextLocalId = () => `local-${++localId}`

/** Свежая заявка — с наибольшим номером (номера вида 2026-000123 растут со временем) */
function latestApplication(list: readonly AssistantApplicationDto[]): AssistantApplicationDto | null {
  return list.reduce<AssistantApplicationDto | null>((best, item) => (!best || item.number > best.number ? item : best), null)
}

let statusRequest: Promise<void> | null = null

/** Статус помощника: от него зависит цвет точки на кнопке и подпись в окне */
function refreshStatus(): Promise<void> {
  statusRequest ??= assistantApi
    .status()
    .then((status) => {
      state.availability = status.mode === 'llm' ? 'llm' : 'rules'
    })
    .catch(() => {
      state.availability = 'off'
    })
    .finally(() => {
      statusRequest = null
    })
  return statusRequest
}

/** Опрос статуса, пока открыта страница с шапкой; возвращает функцию остановки */
function startStatusPolling(): () => void {
  void refreshStatus()
  const timer = setInterval(() => {
    if (document.visibilityState === 'visible') void refreshStatus()
  }, STATUS_POLL_MS)
  return () => clearInterval(timer)
}

async function loadApplications(): Promise<void> {
  const list = await assistantApi.applications()
  state.applications = list
  if (!list.some((item) => item.id === state.applicationId)) state.applicationId = latestApplication(list)?.id ?? null
}

async function loadHistory(): Promise<void> {
  if (!state.conversationId || state.messages.length) return
  try {
    const history = await assistantApi.conversation(state.conversationId)
    state.messages = history.messages.map((item) => ({
      id: item.id,
      role: item.role,
      text: item.text,
      mode: item.mode,
      applicationId: item.application_id,
    }))
  } catch (cause) {
    // Диалог живёт в памяти сервиса и пропал после его перезапуска — молча начинаем новый
    if (cause instanceof AssistantError && cause.kind === 'not_found') storeConversationId(null)
    else throw cause
  }
}

/** Загрузка окна, пока она идёт: вопрос ждёт её, иначе ушёл бы без заявки, выбранной по умолчанию */
let loading: Promise<void> | null = null

/**
 * Всё, что нужно окну при открытии: статус, заявки, история. Ошибки — в state.error.
 * Окно открыли снова, пока загрузка идёт, — ждём ту же, а не запрашиваем всё второй раз
 */
function load(): Promise<void> {
  loading ??= loadAll().finally(() => (loading = null))
  return loading
}

async function loadAll(): Promise<void> {
  state.loading = true
  state.error = null
  try {
    await refreshStatus()
    if (state.availability === 'off') return
    await Promise.all([loadApplications(), loadHistory()])
  } catch (cause) {
    state.error = toChatError(cause)
    if (state.error.kind === 'unavailable') state.availability = 'off'
  } finally {
    state.loading = false
  }
}

function open(): void {
  if (state.open) return
  state.open = true
  void load()
}

function close(): void {
  state.open = false
}

function toggle(): void {
  if (state.open) close()
  else open()
}

/** «Повторить» в состоянии «недоступен» и после ошибки загрузки */
async function retry(): Promise<void> {
  await load()
  const failed = state.messages.find((item) => item.failed)
  if (failed && !state.error && state.availability !== 'off') await answer(failed)
}

async function createConversation(): Promise<string> {
  const conversation = await assistantApi.createConversation()
  storeConversationId(conversation.id)
  return conversation.id
}

let controller: AbortController | null = null

/** Задать вопрос; ответ приходит потоком и дописывается в последнее сообщение */
async function send(text: string): Promise<void> {
  const question = text.trim()
  if (!question || state.busy) return
  if (question.length > ASSISTANT_MAX_QUESTION) {
    state.error = { kind: 'invalid', message: `Вопрос длиннее ${ASSISTANT_MAX_QUESTION} символов — сократите его`, retryAfter: null }
    return
  }
  if (loading) await loading
  // Вопросы без ответа из прошлых попыток не копим: повторить можно только последний
  state.messages = state.messages.filter((item) => !item.failed)
  const message: ChatMessage = { id: nextLocalId(), role: 'user', text: question, mode: null, applicationId: state.applicationId }
  state.messages.push(message)
  await answer(state.messages[state.messages.length - 1]!)
}

async function answer(question: ChatMessage): Promise<void> {
  state.busy = true
  state.error = null
  question.failed = false
  controller = new AbortController()
  const { signal } = controller

  const reply: ChatMessage = { id: nextLocalId(), role: 'assistant', text: '', mode: null, applicationId: null, streaming: true }
  state.messages.push(reply)
  const live = state.messages[state.messages.length - 1]!

  const ask = async (conversationId: string) =>
    assistantApi.ask(
      conversationId,
      { text: question.text, application_id: state.applicationId },
      { onDelta: (part) => (live.text += part) },
      signal,
    )

  try {
    let result
    try {
      result = await ask(state.conversationId ?? (await createConversation()))
    } catch (cause) {
      if (!(cause instanceof AssistantError) || cause.kind !== 'not_found') throw cause
      // Диалога больше нет — молча начинаем новый и повторяем вопрос один раз
      live.text = ''
      result = await ask(await createConversation())
    }
    Object.assign(live, { id: result.message_id, text: result.text, mode: result.mode, applicationId: result.application_id, streaming: false })
  } catch (cause) {
    const index = state.messages.indexOf(live)
    if (index !== -1) state.messages.splice(index, 1)
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    question.failed = true
    state.error = toChatError(cause)
    if (state.error.kind === 'unavailable') state.availability = 'off'
    // Заявки, которой нет у сервиса, — обновляем список, чтобы клиент выбрал другую
    if (state.error.kind === 'not_found') {
      state.applicationId = null
      state.error = { ...state.error, message: 'Заявка не найдена — список обновлён, выберите заявку ещё раз' }
      void loadApplications().catch(() => undefined)
    }
  } finally {
    state.busy = false
  }
}

/** «Новый диалог»: забываем историю; сам диалог на сервисе заводим при первом вопросе */
function newDialog(): void {
  controller?.abort()
  state.busy = false
  state.messages = []
  state.error = null
  storeConversationId(null)
}

/** Вышли из кабинета или сменили учётку: чужой диалог и заявки не остаются */
function reset(): void {
  newDialog()
  state.open = false
  state.applications = []
  state.applicationId = null
}

function selectApplication(id: string | null): void {
  state.applicationId = id
}

export const assistant = {
  state: readonly(state),
  open,
  close,
  toggle,
  load,
  retry,
  send,
  newDialog,
  reset,
  selectApplication,
  refreshStatus,
  startStatusPolling,
}

export function useAssistant() {
  return {
    state: assistant.state,
    selectedApplication: computed(() => state.applications.find((item) => item.id === state.applicationId) ?? null),
  }
}
