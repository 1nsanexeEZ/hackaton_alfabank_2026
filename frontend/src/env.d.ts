/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Префикс API бэкенда, по умолчанию /api (проксируется Vite или nginx) */
  readonly VITE_API_BASE_URL?: string
  /** mock — всё на синтетических данных в браузере, real — вход, пользователи и роли через Identity API */
  readonly VITE_API_MODE?: 'mock' | 'real'
  /** Куда dev-сервер проксирует /api, по умолчанию http://localhost:8000 */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
