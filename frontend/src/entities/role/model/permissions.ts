import type { Permission, Policy } from '@/shared/api'

export interface PermissionGroup {
  id: string
  title: string
  /** Действия группы в порядке колонок матрицы прав */
  items: { permission: Permission; action: string }[]
}

/** Права бэкенда (backend/src/core/access/permissions.py), сгруппированные для матрицы */
export const PERMISSION_GROUPS: readonly PermissionGroup[] = [
  {
    id: 'requests',
    title: 'Заявки',
    items: [
      { permission: 'requests.read', action: 'Просмотр' },
      { permission: 'requests.create', action: 'Создание' },
      { permission: 'requests.update', action: 'Изменение' },
      { permission: 'requests.delete', action: 'Удаление' },
    ],
  },
  {
    id: 'credits',
    title: 'Кредиты и продукты',
    items: [
      { permission: 'credits.read', action: 'Просмотр' },
      { permission: 'credits.create', action: 'Создание' },
      { permission: 'credits.update', action: 'Изменение' },
      { permission: 'credits.delete', action: 'Удаление' },
    ],
  },
  {
    id: 'accounts',
    title: 'Пользователи',
    items: [
      { permission: 'accounts.read', action: 'Просмотр' },
      { permission: 'accounts.create', action: 'Создание' },
      { permission: 'accounts.update', action: 'Изменение' },
      { permission: 'accounts.delete', action: 'Удаление' },
    ],
  },
  {
    id: 'roles',
    title: 'Роли',
    items: [
      { permission: 'roles.read', action: 'Просмотр' },
      { permission: 'roles.create', action: 'Создание' },
      { permission: 'roles.update', action: 'Изменение' },
      { permission: 'roles.delete', action: 'Удаление' },
    ],
  },
]

export const MATRIX_ACTIONS = ['Просмотр', 'Создание', 'Изменение', 'Удаление'] as const

/** Политики применимы только к моделям с нужными миксинами — на бэкенде это заявки и кредиты */
export const POLICY_META: Record<Policy, { label: string; description: string; appliesTo: readonly string[] }> = {
  own_only: {
    label: 'Только свои',
    description: 'Видит только записи, где он владелец',
    appliesTo: ['requests', 'credits'],
  },
  not_deleted: {
    label: 'Без удалённых',
    description: 'Удалённые записи скрыты',
    appliesTo: ['requests', 'credits', 'accounts'],
  },
  org_member: {
    label: 'Только свои компании',
    description: 'Компании, где он участник, и их заявки',
    appliesTo: ['requests'],
  },
}

/** Человеческие названия системных ролей; новые роли показываем как есть */
export const ROLE_TITLE: Record<string, string> = {
  admin: 'Администратор',
  analyst: 'Кредитный аналитик',
  head: 'Руководитель',
  client: 'Клиент',
}

export function roleTitle(name: string): string {
  return ROLE_TITLE[name] ?? name
}
