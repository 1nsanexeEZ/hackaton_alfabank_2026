import { computed, reactive, readonly } from 'vue'

import { configureAuth, identityApi, type MeDto, type Permission } from '@/shared/api'
import { readStorage, writeStorage } from '@/shared/lib'

/**
 * Сессия сотрудника. Храним только access-токен и время его жизни (refresh у бэкенда нет):
 * после истечения — повторный вход. Права берём из /me, как их видит бэкенд по токену.
 * С клиентом на сайте не связана: у сайта своя сессия (entities/customer) со своим токеном.
 */
const STORAGE_KEY = 'admin:session'

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

const expiredListeners = new Set<() => void>()

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

configureAuth(
  {
    getToken: validToken,
    onUnauthorized: () => {
      clear()
      expiredListeners.forEach((listener) => listener())
    },
  },
  'staff',
)

/** Подписка на истечение сессии: роутер уводит на экран входа */
export function onSessionExpired(listener: () => void): () => void {
  expiredListeners.add(listener)
  return () => expiredListeners.delete(listener)
}

export function hasPermission(me: MeDto | null, permission: Permission): boolean {
  if (!me) return false
  return me.permissions.includes('admin') || me.permissions.includes(permission)
}

/**
 * Вход в админку — для сотрудников. Клиент тоже читает заявки, но только своих компаний
 * (own_only в моке, org_member на бэкенде), поэтому его не пускаем.
 */
export function canEnterAdmin(me: MeDto | null): boolean {
  if (!me) return false
  if (me.permissions.includes('admin')) return true
  const policies = me.policies['requests.read'] ?? []
  const clientScope = policies.includes('own_only') || policies.includes('org_member')
  return (
    (hasPermission(me, 'requests.read') && !clientScope) ||
    hasPermission(me, 'accounts.read') ||
    hasPermission(me, 'roles.read')
  )
}

export function displayName(me: Pick<MeDto, 'email' | 'phone' | 'profile'> | null): string {
  if (!me) return ''
  const profile = me.profile
  if (profile && (profile.first_name || profile.last_name)) {
    return [profile.first_name, profile.last_name].filter(Boolean).join(' ')
  }
  return me.email ?? me.phone ?? 'Сотрудник'
}

/** Короткое имя для истории заявки: «Воронцова М. И.» */
export function shortName(me: Pick<MeDto, 'email' | 'phone' | 'profile'> | null): string {
  const profile = me?.profile
  if (!profile?.last_name) return displayName(me)
  const initials = [profile.first_name, profile.middle_name]
    .filter((part): part is string => Boolean(part))
    .map((part) => `${part.charAt(0)}.`)
    .join(' ')
  return initials ? `${profile.last_name} ${initials}` : profile.last_name
}

async function login(login: string, password: string): Promise<MeDto> {
  const token = await identityApi.login(login, password)
  state.token = token.access_token
  state.expiresAt = Date.now() + token.expires_in * 1000
  try {
    state.me = await identityApi.me()
  } catch (error) {
    clear()
    throw error
  }
  writeStorage(STORAGE_KEY, { token: state.token, expiresAt: state.expiresAt } satisfies StoredSession)
  return state.me
}

/** Подтянуть профиль по сохранённому токену; без токена — null */
async function restore(): Promise<MeDto | null> {
  if (!validToken()) return null
  if (state.me) return state.me
  try {
    state.me = await identityApi.me()
  } catch {
    clear()
  }
  return state.me
}

function setMe(me: MeDto) {
  state.me = me
}

export const session = {
  state: readonly(state),
  login,
  logout: clear,
  restore,
  setMe,
  can: (permission: Permission) => hasPermission(state.me, permission),
}

export function useSession() {
  return {
    me: computed(() => state.me),
    isAuthenticated: computed(() => Boolean(state.token && state.me)),
    name: computed(() => displayName(state.me)),
    can: session.can,
    login,
    logout: clear,
  }
}
