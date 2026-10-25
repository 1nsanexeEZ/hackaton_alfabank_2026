import { currentToken } from '../http'
import {
  AssistantError,
  type AskHandlers,
  type AskInput,
  type AssistantAnswerDto,
  type AssistantApi,
  type AssistantErrorKind,
} from './types'

/** Помощник — модуль бэкенда: та же база API, что у остальных запросов кабинета (docs/assistant-api.md) */
export const ASSISTANT_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')

/** Статус не получен за это время — помощник считается недоступным */
const STATUS_TIMEOUT_MS = 3_000

const KIND_BY_STATUS: Record<number, AssistantErrorKind> = {
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  422: 'invalid',
  429: 'rate_limited',
}

const MESSAGE_BY_KIND: Record<AssistantErrorKind, string> = {
  unauthorized: 'Войдите в кабинет, чтобы задать вопрос помощнику',
  forbidden: 'Помощник вам недоступен',
  not_found: 'Диалог или заявка не найдены',
  invalid: 'Вопрос должен быть не пустым и не длиннее 1000 символов',
  rate_limited: 'Слишком часто, повторите чуть позже',
  unavailable: 'Помощник временно недоступен',
}

function error(kind: AssistantErrorKind, retryAfter: number | null = null): AssistantError {
  const message =
    kind === 'rate_limited' && retryAfter ? `Слишком часто, повторите через ${retryAfter} с` : MESSAGE_BY_KIND[kind]
  return new AssistantError(kind, message, retryAfter)
}

function failure(response: Response): AssistantError {
  const kind = KIND_BY_STATUS[response.status] ?? 'unavailable'
  const retryAfter = Number.parseInt(response.headers.get('Retry-After') ?? '', 10)
  return error(kind, kind === 'rate_limited' && retryAfter > 0 ? retryAfter : null)
}

function isAbort(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError'
}

async function request(path: string, init: RequestInit = {}, authorized = true): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = authorized ? currentToken('client') : null
  if (token) headers.set('Authorization', `Bearer ${token}`)
  try {
    return await fetch(`${ASSISTANT_URL}${path}`, { ...init, headers })
  } catch (cause) {
    if (isAbort(cause)) throw cause
    throw error('unavailable')
  }
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  const response = await request(path, { ...init, headers })
  if (!response.ok) throw failure(response)
  try {
    return (await response.json()) as T
  } catch {
    throw error('unavailable')
  }
}

/**
 * Поток ответа: события `status`, `delta`, `done`, `error`, строки `: ping` — keep-alive.
 * Событие — блок строк до пустой строки; `data:` может занимать несколько строк.
 */
async function readStream(response: Response, handlers: AskHandlers): Promise<AssistantAnswerDto> {
  if (!response.body) throw error('unavailable')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let answer: AssistantAnswerDto | null = null

  const handle = (block: string) => {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line === '' || line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
    }
    if (!data.length) return
    let payload: unknown
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      return
    }
    if (event === 'status') handlers.onThinking?.()
    else if (event === 'delta') {
      const text = (payload as { text?: unknown }).text
      if (typeof text === 'string' && text) handlers.onDelta(text)
    } else if (event === 'done') answer = payload as AssistantAnswerDto
    else if (event === 'error') throw error('unavailable')
  }

  try {
    for (;;) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n?/g, '\n')
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        handle(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        end = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    if (buffer.trim()) handle(buffer)
  } catch (cause) {
    if (cause instanceof AssistantError || isAbort(cause)) throw cause
    throw error('unavailable')
  }
  if (!answer) throw error('unavailable')
  return answer
}

async function ask(id: string, input: AskInput, handlers: AskHandlers, signal?: AbortSignal): Promise<AssistantAnswerDto> {
  const response = await request(`/assistant/conversations/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })
  if (!response.ok) throw failure(response)
  if (response.headers.get('Content-Type')?.includes('text/event-stream')) return readStream(response, handlers)
  // Сервис ответил обычным JSON — показываем текст целиком
  const answer = (await response.json().catch(() => null)) as AssistantAnswerDto | null
  if (!answer?.text) throw error('unavailable')
  handlers.onDelta(answer.text)
  return answer
}

/** Клиент сервиса помощника; токен — клиента сайта, как у остальных запросов кабинета */
export const realAssistantApi: AssistantApi = {
  async status() {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), STATUS_TIMEOUT_MS)
    try {
      const response = await request('/assistant/status', { headers: { Accept: 'application/json' }, signal: controller.signal }, false)
      if (!response.ok) throw error('unavailable')
      return await response.json()
    } catch (cause) {
      if (cause instanceof AssistantError) throw cause
      throw error('unavailable')
    } finally {
      clearTimeout(timer)
    }
  },
  applications: () => json('/assistant/applications'),
  createConversation: () => json('/assistant/conversations', { method: 'POST' }),
  conversation: (id) => json(`/assistant/conversations/${encodeURIComponent(id)}`),
  ask,
}
