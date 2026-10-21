const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** Режим API: mock — всё в браузере на синтетических данных, real — Identity идёт в бэкенд */
export const API_MODE: 'mock' | 'real' = import.meta.env.VITE_API_MODE === 'real' ? 'real' : 'mock'

/** Ошибка API в формате бэкенда: `{ code, message }` */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

let getToken: () => string | null = () => null
let onUnauthorized: () => void = () => {}

/** Сессия сообщает http-клиенту, каким токеном подписывать запросы и что делать при 401 */
export function configureAuth(options: { getToken: () => string | null; onUnauthorized: () => void }): void {
  getToken = options.getToken
  onUnauthorized = options.onUnauthorized
}

export function currentToken(): string | null {
  return getToken()
}

/** Сообщить о протухшей сессии — так же, как это делает http-клиент на ответ 401 */
export function notifyUnauthorized(): void {
  onUnauthorized()
}

type Query = Record<string, string | number | undefined>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
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
  const token = getToken()
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

  if (response.status === 401 && token) onUnauthorized()
  throw toApiError(response.status, data)
}

function toApiError(status: number, data: unknown): ApiError {
  if (data && typeof data === 'object') {
    const { code, message, detail } = data as { code?: string; message?: string; detail?: unknown }
    if (message) return new ApiError(status, code ?? 'error', message)
    // Ошибки валидации FastAPI: { detail: [{ msg }] }
    if (Array.isArray(detail)) {
      const text = detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ')
      return new ApiError(status, 'validation_error', text || 'Проверьте введённые данные')
    }
  }
  return new ApiError(status, 'error', status >= 500 ? 'Ошибка сервера, попробуйте позже' : 'Запрос не выполнен')
}

/** Имитация сетевой задержки для моков, чтобы были видны состояния загрузки */
export function delay(ms = 300): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
