import { humanMessage } from './errorMessages'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

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

/** Массив — повторяющийся параметр: `status=open&status=in_progress` */
type Query = Record<string, string | number | readonly string[] | undefined>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  /** Чьим токеном подписать запрос; по умолчанию — сотрудника */
  realm?: AuthRealm
  /** Ответ — текст как есть (BPMN XML схемы маршрута), а не JSON */
  text?: boolean
}

/** Адрес ручки с префиксом API — для того, что ходит в бэк мимо http(): EventSource, ссылки */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item))
    else if (value !== undefined) params.set(key, String(value))
  }
  const search = params.toString()
  return `${API_BASE_URL}${path}${search ? `?${search}` : ''}`
}

/** Запрос с токеном нужного интерфейса; FormData уходит как есть — заголовок multipart с границей ставит браузер */
async function send(path: string, options: RequestOptions, accept: string): Promise<{ response: Response; token: string | null }> {
  const headers: Record<string, string> = { Accept: accept }
  const token = providers[options.realm ?? 'staff'].getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const form = options.body instanceof FormData
  if (options.body !== undefined && !form) headers['Content-Type'] = 'application/json'

  try {
    const response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : form ? (options.body as FormData) : JSON.stringify(options.body),
    })
    return { response, token }
  } catch {
    throw new ApiError(0, 'network_error', 'Сервер недоступен. Проверьте, что бэкенд запущен')
  }
}

/** Неудачный ответ — в ApiError того же формата, что у JSON-ручек */
async function fail(response: Response, token: string | null, realm: AuthRealm = 'staff'): Promise<never> {
  const data: unknown = await response.json().catch(() => null)
  if (response.status === 401 && token) providers[realm].onUnauthorized()
  throw toApiError(response.status, data, Boolean(token))
}

export async function http<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { response, token } = await send(path, options, options.text ? '*/*' : 'application/json')

  if (response.status === 204) return undefined as T
  if (response.ok && options.text) return (await response.text()) as T
  if (!response.ok) return fail(response, token, options.realm)

  return (await response.json().catch(() => null)) as T
}

/** Страница списка: total — сколько всего по тому же фильтру; null — бэкенд не сказал */
export interface Page<T> {
  items: T[]
  total: number | null
}

/** Список, у которого бэкенд кладёт общее число в заголовок X-Total-Count, а тело — массив */
export async function httpPage<T>(path: string, options: Omit<RequestOptions, 'text'> = {}): Promise<Page<T>> {
  const { response, token } = await send(path, options, 'application/json')
  if (!response.ok) return fail(response, token, options.realm)
  const items = ((await response.json().catch(() => null)) as T[] | null) ?? []
  const header = response.headers.get('X-Total-Count')
  const total = header === null || header.trim() === '' ? NaN : Number(header)
  return { items, total: Number.isFinite(total) ? total : null }
}

/** Файл из ответа и его имя из Content-Disposition (null — бэкенд имя не назвал) */
export interface DownloadedFile {
  blob: Blob
  filename: string | null
}

/**
 * Бинарный ответ (PDF договора). Обычная ссылка не подойдёт: ручке нужен заголовок Authorization,
 * поэтому файл забираем fetch'ем, а сохраняет его saveFile из shared/lib.
 */
export async function httpFile(path: string, options: Omit<RequestOptions, 'text' | 'body'> = {}): Promise<DownloadedFile> {
  const { response, token } = await send(path, options, '*/*')
  if (!response.ok) return fail(response, token, options.realm)
  return { blob: await response.blob(), filename: filenameFrom(response.headers.get('Content-Disposition')) }
}

/** `attachment; filename*=UTF-8''%D0%94…` или `filename="contract.pdf"` → имя файла */
function filenameFrom(disposition: string | null): string | null {
  if (!disposition) return null
  const encoded = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(disposition)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded.trim().replace(/^"|"$/g, ''))
    } catch {
      // Битая кодировка — пробуем обычное filename ниже
    }
  }
  return /filename\s*=\s*"?([^";]+)"?/.exec(disposition)?.[1]?.trim() ?? null
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
    // Такой ручки на бэкенде нет: роутер FastAPI отвечает { detail: "Not Found" } без кода бэкенда
    if (status === 404 && detail === 'Not Found') {
      return new ApiError(status, 'route_not_found', 'На бэкенде пока нет этой ручки')
    }
  }
  return new ApiError(status, 'error', humanMessage(status, undefined, {}, authorized))
}
