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

export interface PermissionSection {
  title: string
  items: { permission: Permission; label: string; description?: string }[]
}

/**
 * Права вне матрицы «раздел × действие»: у них нет четвёрки просмотр–создание–изменение–удаление.
 * Профиль и admin — отдельными переключателями в редакторе роли
 */
export const PERMISSION_SECTIONS: readonly PermissionSection[] = [
  {
    title: 'Рабочее место',
    items: [
      { permission: 'backoffice.read', label: 'Очередь, метрики, проверка по ИНН, скоринг', description: 'Экраны бэк-офиса' },
      { permission: 'tasks.read', label: 'Задачи и маршрут заявки', description: 'Видеть задачи андеррайтера и ход процесса' },
      { permission: 'tasks.update', label: 'Решать задачи', description: 'Взять задачу и вынести решение по заявке' },
      { permission: 'decisions.read', label: 'Решение с журналом правил', description: 'Полная трасса кредитной политики' },
    ],
  },
  {
    title: 'Модель и политика',
    items: [
      { permission: 'scoring.read', label: 'Версии: просмотр и примерка', description: 'PD-модель и кредитная политика' },
      { permission: 'scoring.update', label: 'Версии: черновики, активация, откат', description: 'Новая версия действует со следующей заявки' },
    ],
  },
  {
    title: 'Компании',
    items: [
      { permission: 'organizations.read', label: 'Просмотр компаний' },
      { permission: 'organizations.update', label: 'Изменение компаний', description: 'Участники, доверенности, сверка с ЕГРЮЛ, отчётность' },
    ],
  },
  {
    title: 'Поддержка и уведомления',
    items: [
      { permission: 'support.manage', label: 'Очередь обращений', description: 'Взять, ответить, решить, закрыть' },
      { permission: 'support.read', label: 'Свои обращения', description: 'Клиентам: список и переписка' },
      { permission: 'support.create', label: 'Задать вопрос', description: 'Клиентам: новое обращение и сообщения в своё' },
      { permission: 'feed.read', label: 'Лента уведомлений' },
      { permission: 'assistant.use', label: 'Умный помощник', description: 'Вопросы о своих заявках в окне на сайте' },
    ],
  },
]

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
  underwriter: 'Андеррайтер',
  analyst: 'Кредитный аналитик',
  head: 'Руководитель',
  client: 'Клиент',
}

export function roleTitle(name: string): string {
  return ROLE_TITLE[name] ?? name
}
