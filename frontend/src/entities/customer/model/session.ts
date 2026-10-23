import { computed, reactive, readonly } from 'vue'

import { ApiError, clientApi, configureAuth, type MeDto, type ProfileInput, type TokenResponse } from '@/shared/api'
import { readStorage, writeStorage } from '@/shared/lib'

/**
 * Клиент на сайте. Сессия независима от рабочего места сотрудников: свой токен в своём ключе
 * хранилища, запросы сайта подписываются только им. Вход в одном интерфейсе не влияет на другой.
 * Refresh у бэкенда нет: после истечения токена — повторный вход.
 */
const STORAGE_KEY = 'client:session'

interface StoredSession {
  token: string
  expiresAt: number
}

const state = reactive<{ token: string | null; expiresAt: number; me: MeDto | null }>({
  token: null,
  expiresAt: 0,
  me: null,
})

const stored = readStorage<StoredSession>(STORAGE_KEY)
if (stored && stored.expiresAt > Date.now()) {
  state.token = stored.token
  state.expiresAt = stored.expiresAt
}

function clear() {
  state.token = null
  state.expiresAt = 0
  state.me = null
  writeStorage(STORAGE_KEY, null)
}

function validToken(): string | null {
  if (state.token && state.expiresAt <= Date.now()) clear()
  return state.token
}

configureAuth({ getToken: validToken, onUnauthorized: clear }, 'client')

/** На сайт входят клиенты банка; у сотрудников своё рабочее место со своим входом */
export function isClientAccount(me: MeDto): boolean {
  return me.role.name === 'client'
}

export function customerName(me: Pick<MeDto, 'email' | 'phone' | 'profile'> | null): string {
  if (!me) return ''
  const profile = me.profile
  if (profile && (profile.first_name || profile.last_name)) {
    return [profile.first_name, profile.last_name].filter(Boolean).join(' ')
  }
  return me.email ?? me.phone ?? 'Клиент'
}

async function authorize(token: TokenResponse): Promise<MeDto> {
  state.token = token.access_token
  state.expiresAt = Date.now() + token.expires_in * 1000
  try {
    const me = await clientApi.me()
    if (!isClientAccount(me)) {
      throw new ApiError(403, 'permission_denied', 'Это вход для клиентов банка — учётная запись сотрудника здесь не подходит')
    }
    state.me = me
  } catch (error) {
    clear()
    throw error
  }
  writeStorage(STORAGE_KEY, { token: state.token, expiresAt: state.expiresAt } satisfies StoredSession)
  return state.me
}

async function login(login: string, password: string): Promise<MeDto> {
  return authorize(await clientApi.login(login, password))
}

/** Вход в демо-учётку без пароля — только на стенде с DEMO_LOGIN_ENABLED=true */
async function loginWithDemo(login: string): Promise<MeDto> {
  return authorize(await clientApi.demoLogin(login))
}

/** Профиль по сохранённому токену; токена нет или он истёк — null, то есть «не вошёл» */
async function restore(): Promise<MeDto | null> {
  if (!validToken()) return null
  if (state.me) return state.me
  try {
    const me = await clientApi.me()
    if (isClientAccount(me)) state.me = me
    else clear()
  } catch {
    clear()
  }
  return state.me
}

/** ФИО и должность в профиле: имя в шапке и в заявках обновляется сразу */
async function updateProfile(input: ProfileInput): Promise<MeDto> {
  state.me = await clientApi.updateProfile(input)
  return state.me
}

export const customer = {
  state: readonly(state),
  login,
  loginWithDemo,
  logout: clear,
  restore,
  updateProfile,
}

export function useCustomer() {
  return {
    me: computed(() => state.me),
    isAuthenticated: computed(() => Boolean(state.token && state.me)),
    name: computed(() => customerName(state.me)),
    logout: clear,
  }
}
