import {
  FileSearch,
  Inbox,
  LayoutDashboard,
  MessagesSquare,
  Package,
  ShieldCheck,
  SlidersHorizontal,
  Users,
} from 'lucide-vue-next'
import type { Component } from 'vue'

import type { Permission } from '@/shared/api'
import { ADMIN_ROUTE, type AdminRouteName } from '@/shared/config'

export interface NavItem {
  route: AdminRouteName
  label: string
  icon: Component
  /** Без этого права пункт не показываем; страница проверяет то же право в роутере */
  permission: Permission
}

export interface NavGroup {
  title: string
  items: NavItem[]
}

export const ADMIN_NAVIGATION: readonly NavGroup[] = [
  {
    title: 'Кредиты',
    items: [
      { route: ADMIN_ROUTE.dashboard, label: 'Обзор', icon: LayoutDashboard, permission: 'requests.read' },
      { route: ADMIN_ROUTE.applications, label: 'Заявки', icon: Inbox, permission: 'requests.read' },
      { route: ADMIN_ROUTE.innCheck, label: 'Проверка по ИНН', icon: FileSearch, permission: 'backoffice.read' },
      { route: ADMIN_ROUTE.support, label: 'Поддержка', icon: MessagesSquare, permission: 'support.manage' },
    ],
  },
  {
    title: 'Настройки',
    items: [
      { route: ADMIN_ROUTE.products, label: 'Продукты', icon: Package, permission: 'credits.read' },
      { route: ADMIN_ROUTE.scoring, label: 'Скоринг', icon: SlidersHorizontal, permission: 'backoffice.read' },
    ],
  },
  {
    title: 'Доступ',
    items: [
      { route: ADMIN_ROUTE.users, label: 'Пользователи', icon: Users, permission: 'accounts.read' },
      { route: ADMIN_ROUTE.roles, label: 'Роли и права', icon: ShieldCheck, permission: 'roles.read' },
    ],
  },
]
