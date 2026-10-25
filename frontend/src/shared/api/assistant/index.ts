import { mockAssistantApi } from './mock'
import { realAssistantApi } from './real'
import type { AssistantApi } from './types'

/** Помощник, как и весь сайт, ходит в бэкенд; шаблоны в браузере — только с VITE_ASSISTANT_MODE=mock */
export const ASSISTANT_MOCK: boolean = import.meta.env.VITE_ASSISTANT_MODE === 'mock'

/** Тумблер состояния ИИ в окне чата: только на моках и только в dev-сборке */
export const ASSISTANT_MOCK_CONTROLS: boolean = ASSISTANT_MOCK && import.meta.env.DEV

export const assistantApi: AssistantApi = ASSISTANT_MOCK ? mockAssistantApi : realAssistantApi

export { mockAssistantState, setMockAssistantState, type MockAssistantState } from './mock'
export { ASSISTANT_URL } from './real'
export * from './types'
