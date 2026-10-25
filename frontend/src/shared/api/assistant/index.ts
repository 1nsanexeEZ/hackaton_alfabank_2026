import { realAssistantApi } from './real'
import type { AssistantApi } from './types'

/** Помощник, как и весь сайт, ходит в бэкенд: без модели бэкенд сам отвечает по шаблонам */
export const assistantApi: AssistantApi = realAssistantApi

export { ASSISTANT_URL } from './real'
export * from './types'
