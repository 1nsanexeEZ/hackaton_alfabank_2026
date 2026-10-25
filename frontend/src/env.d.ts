/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Префикс API бэкенда, по умолчанию /api (проксируется Vite или nginx) */
  readonly VITE_API_BASE_URL?: string
  /** Куда dev-сервер проксирует /api, по умолчанию http://localhost:8000 */
  readonly VITE_API_PROXY_TARGET?: string
  /** mock — помощник отвечает шаблонами в браузере; не задан или real — бэкенд */
  readonly VITE_ASSISTANT_MODE?: 'mock' | 'real'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
