/** Контракт сервиса «Умный помощник»: docs/assistant-api.md. Поля повторяют ответы сервиса как есть */

/** llm — отвечает модель, rules — шаблоны (модель выключена или недоступна) */
export type AssistantMode = 'llm' | 'rules'

export interface AssistantStatusDto {
  enabled: boolean
  mode: AssistantMode
  model: string | null
  host: string | null
  reachable: boolean
  reason: string | null
}

/** Заявка, о которой можно спросить */
export interface AssistantApplicationDto {
  id: string
  number: string
  product_code: string
  status: string
  client_stage: string | null
}

export interface ConversationDto {
  id: string
  created_at: string
}

export interface AssistantHistoryMessageDto {
  id: string
  role: 'user' | 'assistant'
  text: string
  created_at: string
  application_id: string | null
  mode: AssistantMode | null
}

export interface ConversationHistoryDto extends ConversationDto {
  messages: AssistantHistoryMessageDto[]
}

export interface AskInput {
  text: string
  application_id: string | null
}

export type AssistantIntent =
  | 'decision'
  | 'status'
  | 'products'
  | 'payment'
  | 'greeting'
  | 'off_topic'
  | 'injection'
  | 'internal_data'

/** Итог ответа: приходит и в обычном ответе, и в событии `done` потока */
export interface AssistantAnswerDto {
  message_id: string
  text: string
  mode: AssistantMode
  intent: AssistantIntent
  application_id: string | null
  fallback_reason: string | null
}

/** Что делать клиенту с ошибкой — по таблице из контракта */
export type AssistantErrorKind =
  | 'unauthorized' // 401: нет или просрочен токен
  | 'forbidden' // 403: нет права assistant.use
  | 'not_found' // 404: нет диалога или заявки
  | 'invalid' // 422: вопрос пустой или длиннее 1000 символов
  | 'rate_limited' // 429: лимит вопросов в минуту
  | 'unavailable' // 502/503, сеть, оборванный поток

export class AssistantError extends Error {
  constructor(
    readonly kind: AssistantErrorKind,
    message: string,
    /** Секунды из Retry-After при 429 */
    readonly retryAfter: number | null = null,
  ) {
    super(message)
    this.name = 'AssistantError'
  }
}

export interface AskHandlers {
  /** Сервис думает: постпроверка ответа до показа */
  onThinking?: () => void
  /** Очередной кусок текста */
  onDelta: (text: string) => void
}

export interface AssistantApi {
  status: () => Promise<AssistantStatusDto>
  applications: () => Promise<AssistantApplicationDto[]>
  createConversation: () => Promise<ConversationDto>
  conversation: (id: string) => Promise<ConversationHistoryDto>
  ask: (id: string, input: AskInput, handlers: AskHandlers, signal?: AbortSignal) => Promise<AssistantAnswerDto>
}
