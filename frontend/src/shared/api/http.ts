import { humanMessage } from './errorMessages'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

/**
 * Режим API рабочего места сотрудников: mock — всё в браузере на синтетических данных,
 * real — вход, пользователи и роли идут в бэкенд. Сайт для клиентов всегда ходит в бэкенд.
 */
export const API_MODE: 'mock' | 'real' = import.meta.env.VITE_API_MODE === 'real' ? 'real' : 'mock'

/** Нарушение в поле: `{ code: "missing", field: "consents.credit_bureau" }` */
export interface ApiViolation {
  code: string
  field: string
}

/** Уточнение ошибки: `details.code`, нарушения полей, актуальная версия черновика и т. п. */
export interface ApiErrorDetails {
  code?: string
  violations?: ApiViolation[]
  [key: string]: unknown
}

/** Ошибка API в формате бэкенда: `{ code, message, details? }` */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ApiErrorDetails = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Чей токен у запроса. Сайт для клиентов и рабочее место сотрудников — независимые интерфейсы:
 * у каждого свой вход и своя сессия, вход в одном не влияет на другой.
 */
export type AuthRealm = 'staff' | 'client'

interface AuthProvider {
  getToken: () => string | null
  onUnauthorized: () => void
}

const providers: Record<AuthRealm, AuthProvider> = {
  staff: { getToken: () => null, onUnauthorized: () => {} },
  client: { getToken: () => null, onUnauthorized: () => {} },
}

/** Сессия сообщает http-клиенту, каким токеном подписывать запросы своего интерфейса и что делать при 401 */
export function configureAuth(options: AuthProvider, realm: AuthRealm = 'staff'): void {
  providers[realm] = options
}

export function currentToken(realm: AuthRealm = 'staff'): string | null {
  return providers[realm].getToken()
}

type Query = Record<string, string | number | undefined>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  /** Чьим токеном подписать запрос; по умолчанию — сотрудника */
  realm?: AuthRealm
}

/** Адрес ручки с префиксом API — для того, что ходит в бэк мимо http(): EventSource, ссылки */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.set(key, String(value))
  }
  const search = params.toString()
  return `${API_BASE_URL}${path}${search ? `?${search}` : ''}`
}

export async function http<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const provider = providers[options.realm ?? 'staff']
  const token = provider.getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Сервер недоступен. Проверьте, что бэкенд запущен')
  }

  if (response.status === 204) return undefined as T

  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T

  if (response.status === 401 && token) provider.onUnauthorized()
  throw toApiError(response.status, data, Boolean(token))
}

interface FastApiIssue {
  loc?: (string | number)[]
  msg?: string
  type?: string
}

function toApiError(status: number, data: unknown, authorized: boolean): ApiError {
  if (data && typeof data === 'object') {
    const { code, message, details, detail } = data as {
      code?: string
      message?: string
      details?: ApiErrorDetails
      detail?: unknown
    }
    if (code || message) {
      return new ApiError(status, code ?? 'error', humanMessage(status, message, details ?? {}, authorized), details ?? {})
    }
    // Ошибки валидации FastAPI: { detail: [{ loc, msg, type }] } — msg у них по-английски, нужны только поля
    if (Array.isArray(detail)) {
      const issues = detail as FastApiIssue[]
      const violations = issues.map((item) => ({
        code: item.type ?? 'invalid',
        field: (item.loc ?? []).filter((part) => part !== 'body').join('.'),
      }))
      return new ApiError(status, 'validation_error', 'Проверьте введённые данные', { violations })
    }
  }
  return new ApiError(status, 'error', humanMessage(status, undefined, {}, authorized))
}

/** Имитация сетевой задержки для моков, чтобы были видны состояния загрузки */
export function delay(ms = 300): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
