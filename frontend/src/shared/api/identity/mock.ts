import { readStorage, writeStorage } from '../../lib/storage'
import { ApiError, currentToken, delay } from '../http'
import type { AccountDto, IdentityApi, MeDto, Permission, PolicyMap, ProfileDto, RoleDto } from './types'

/**
 * Identity в браузере: повторяет поведение бэкенда (права, мягкое удаление, 409 на занятые роли),
 * чтобы админку можно было показать без запущенного бэкенда. Данные живут в localStorage.
 *
 * Демо-учётки: пароль админа совпадает с BOOTSTRAP_ADMIN_PASSWORD из docker-compose,
 * у остальных сотрудников — DEMO_PASSWORD.
 */
const STORAGE_KEY = 'admin-mock:identity'
const TOKEN_PREFIX = 'mock.'
const ADMIN_PASSWORD = 'Admin-2026!'
const DEMO_PASSWORD = 'Demo-2026!'

/** Демо-учётки для подсказки на экране входа */
export const MOCK_DEMO_ACCOUNTS = [
  { login: 'admin@example.com', password: ADMIN_PASSWORD, role: 'Администратор' },
  { login: 'analyst@example.com', password: DEMO_PASSWORD, role: 'Кредитный аналитик' },
  { login: 'head@example.com', password: DEMO_PASSWORD, role: 'Руководитель' },
] as const

interface StoredAccount extends AccountDto {
  password: string
}

interface Store {
  roles: RoleDto[]
  accounts: StoredAccount[]
}

const SEED_DATE = '2026-10-01T09:00:00Z'

function role(id: string, name: string, description: string, permissions: Permission[], policies: PolicyMap = {}): RoleDto {
  return { id, name, description, permissions, policies, created_at: SEED_DATE, updated_at: SEED_DATE }
}

function profile(last: string, first: string, middle: string | null, position: string | null): ProfileDto {
  return { last_name: last, first_name: first, middle_name: middle, position }
}

function seed(): Store {
  const roles = [
    role('r-admin', 'admin', 'Полный доступ', ['admin']),
    role('r-analyst', 'analyst', 'Кредитный аналитик: рассматривает заявки', [
      'requests.read',
      'requests.update',
      'credits.read',
      'profile.update',
    ]),
    role('r-head', 'head', 'Руководитель: продукты, сотрудники, отчёты', [
      'requests.read',
      'credits.read',
      'credits.update',
      'accounts.read',
      'roles.read',
      'profile.update',
    ]),
    role(
      'r-client',
      'client',
      'Клиент банка: только свои заявки',
      ['requests.read', 'requests.create', 'credits.read', 'profile.update'],
      { 'requests.read': ['own_only', 'not_deleted'], 'credits.read': ['own_only'] },
    ),
  ]

  const account = (
    id: string,
    email: string,
    roleId: string,
    data: ProfileDto,
    password = DEMO_PASSWORD,
    phone: string | null = null,
  ): StoredAccount => {
    const target = roles.find((item) => item.id === roleId)!
    return {
      id,
      email,
      phone,
      role: { id: target.id, name: target.name },
      profile: data,
      created_at: SEED_DATE,
      deleted_at: null,
      password,
    }
  }

  return {
    roles,
    accounts: [
      account('a-admin', 'admin@example.com', 'r-admin', profile('Admin', 'Admin', null, null), ADMIN_PASSWORD),
      account(
        'a-analyst',
        'analyst@example.com',
        'r-analyst',
        profile('Воронцова', 'Мария', 'Игоревна', 'Кредитный аналитик'),
        DEMO_PASSWORD,
        '+79161234567',
      ),
      account('a-head', 'head@example.com', 'r-head', profile('Литвинов', 'Олег', 'Борисович', 'Руководитель МСБ')),
      account('a-analyst-2', 'k.sorokin@example.com', 'r-analyst', profile('Сорокин', 'Кирилл', null, 'Аналитик')),
      account('a-client', 'anna.smirnova@example.com', 'r-client', profile('Смирнова', 'Анна', 'Викторовна', null)),
    ],
  }
}

let store: Store = readStorage<Store>(STORAGE_KEY) ?? seed()

function save() {
  writeStorage(STORAGE_KEY, store)
}

function publicAccount(stored: StoredAccount): AccountDto {
  const { password: _password, ...account } = stored
  return structuredClone(account)
}

function findRole(id: string): RoleDto {
  const found = store.roles.find((item) => item.id === id)
  if (!found) throw new ApiError(404, 'not_found', 'Роль не найдена')
  return found
}

function currentAccount(): StoredAccount {
  const token = currentToken()
  const id = token?.startsWith(TOKEN_PREFIX) ? token.slice(TOKEN_PREFIX.length) : null
  const account = store.accounts.find((item) => item.id === id && !item.deleted_at)
  if (!account) throw new ApiError(401, 'unauthorized', 'Сессия истекла, войдите снова')
  return account
}

function requirePermission(permission: Permission): StoredAccount {
  const account = currentAccount()
  const { permissions } = findRole(account.role.id)
  if (!permissions.includes('admin') && !permissions.includes(permission)) {
    throw new ApiError(403, 'permission_denied', 'Недостаточно прав')
  }
  return account
}

function assertUniqueLogin(email: string | null | undefined, phone: string | null | undefined, exceptId?: string) {
  const taken = store.accounts.some(
    (item) =>
      item.id !== exceptId && !item.deleted_at && ((email && item.email === email) || (phone && item.phone === phone)),
  )
  if (taken) throw new ApiError(409, 'conflict', 'Аккаунт с таким email или телефоном уже есть')
}

function assertPolicies(permissions: Permission[], policies: PolicyMap) {
  const extra = Object.keys(policies).filter((key) => !permissions.includes(key as Permission))
  if (extra.length) {
    throw new ApiError(400, 'bad_request', `Политики заданы для прав, которых нет в роли: ${extra.join(', ')}`)
  }
}

function toMe(account: StoredAccount): MeDto {
  const { permissions, policies } = findRole(account.role.id)
  return { ...publicAccount(account), permissions: [...permissions], policies: structuredClone(policies) }
}

const now = () => new Date().toISOString()

export const mockIdentityApi: IdentityApi = {
  async login(login, password) {
    await delay(500)
    const value = login.trim().toLowerCase()
    const account = store.accounts.find(
      (item) => !item.deleted_at && (item.email === value || item.phone === value) && item.password === password,
    )
    if (!account) throw new ApiError(401, 'unauthorized', 'Неверный логин или пароль')
    return { access_token: `${TOKEN_PREFIX}${account.id}`, token_type: 'bearer', expires_in: 30 * 60 }
  },

  async me() {
    await delay(150)
    return toMe(currentAccount())
  },

  async updateProfile(data) {
    await delay()
    const account = requirePermission('profile.update')
    account.profile = { ...(account.profile ?? profile('', '', null, null)), ...data }
    save()
    return toMe(account)
  },

  async listAccounts() {
    await delay()
    requirePermission('accounts.read')
    return store.accounts.map(publicAccount)
  },

  async createAccount(data) {
    await delay()
    requirePermission('accounts.create')
    assertUniqueLogin(data.email, data.phone)
    const target = findRole(data.role_id)
    const account: StoredAccount = {
      id: crypto.randomUUID(),
      email: data.email ?? null,
      phone: data.phone ?? null,
      role: { id: target.id, name: target.name },
      profile: { ...data.profile },
      created_at: now(),
      deleted_at: null,
      password: data.password,
    }
    store.accounts.push(account)
    save()
    return publicAccount(account)
  },

  async updateAccount(id, data) {
    await delay()
    requirePermission('accounts.update')
    const account = store.accounts.find((item) => item.id === id)
    if (!account) throw new ApiError(404, 'not_found', 'Аккаунт не найден')
    assertUniqueLogin(data.email, data.phone, id)
    if (data.email !== undefined) account.email = data.email
    if (data.phone !== undefined) account.phone = data.phone
    if (data.password) account.password = data.password
    if (data.role_id) {
      const target = findRole(data.role_id)
      account.role = { id: target.id, name: target.name }
    }
    if (data.profile) account.profile = { ...(account.profile ?? profile('', '', null, null)), ...data.profile }
    save()
    return publicAccount(account)
  },

  async deleteAccount(id) {
    await delay()
    const actor = requirePermission('accounts.delete')
    if (actor.id === id) throw new ApiError(400, 'bad_request', 'Нельзя удалить свой аккаунт')
    const account = store.accounts.find((item) => item.id === id)
    if (!account) throw new ApiError(404, 'not_found', 'Аккаунт не найден')
    account.deleted_at = now()
    save()
  },

  async listRoles() {
    await delay()
    requirePermission('roles.read')
    return structuredClone(store.roles)
  },

  async createRole(data) {
    await delay()
    requirePermission('roles.create')
    if (store.roles.some((item) => item.name === data.name)) {
      throw new ApiError(409, 'conflict', 'Роль с таким названием уже есть')
    }
    assertPolicies(data.permissions, data.policies)
    const created: RoleDto = { id: crypto.randomUUID(), ...structuredClone(data), created_at: now(), updated_at: now() }
    store.roles.push(created)
    save()
    return structuredClone(created)
  },

  async updateRole(id, data) {
    await delay()
    requirePermission('roles.update')
    const target = findRole(id)
    if (data.name && store.roles.some((item) => item.id !== id && item.name === data.name)) {
      throw new ApiError(409, 'conflict', 'Роль с таким названием уже есть')
    }
    const next = { ...target, ...structuredClone(data), updated_at: now() }
    assertPolicies(next.permissions, next.policies)
    Object.assign(target, next)
    for (const account of store.accounts) {
      if (account.role.id === id) account.role.name = target.name
    }
    save()
    return structuredClone(target)
  },

  async deleteRole(id) {
    await delay()
    requirePermission('roles.delete')
    findRole(id)
    if (store.accounts.some((item) => item.role.id === id)) {
      throw new ApiError(409, 'conflict', 'Роль назначена аккаунтам, сначала смените им роль')
    }
    store.roles = store.roles.filter((item) => item.id !== id)
    save()
  },
}
