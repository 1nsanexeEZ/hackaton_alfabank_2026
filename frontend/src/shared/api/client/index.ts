import { realClientApi } from './real'
import type { ClientApi } from './types'

/** Клиентский путь сайта: вход клиента, каталог, калькулятор, компании и заявка — всегда в бэкенд */
export const clientApi: ClientApi = realClientApi

export type * from './types'
