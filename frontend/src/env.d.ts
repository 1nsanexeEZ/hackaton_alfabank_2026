/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Префикс API бэкенда, по умолчанию /api (проксируется Vite или nginx) */
  readonly VITE_API_BASE_URL?: string
  /** Только для рабочего места сотрудников: mock — синтетические данные в браузере, real — Identity бэкенда */
  readonly VITE_API_MODE?: 'mock' | 'real'
  /** Куда dev-сервер проксирует /api, по умолчанию http://localhost:8000 */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
