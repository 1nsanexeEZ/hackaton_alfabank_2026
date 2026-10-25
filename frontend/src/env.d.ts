/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Префикс API бэкенда, по умолчанию /api (проксируется Vite или nginx) */
  readonly VITE_API_BASE_URL?: string
  /** Куда dev-сервер проксирует /api, по умолчанию http://localhost:8000 */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
