import { START_LOCATION, createRouter, createWebHistory, type RouteLocationRaw } from 'vue-router'

import { canEnterAdmin, onSessionExpired, session } from '@/entities/session'
import { LandingPage } from '@/pages/landing'
import type { Permission } from '@/shared/api'
import { ADMIN_ROUTE, APP_NAME, ROUTE_PATH } from '@/shared/config'
import { ADMIN_NAVIGATION, AdminLayout } from '@/widgets/admin-layout'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** Страница без шапки и подвала сайта */
    bare?: boolean
    /** Раздел только для сотрудников с доступом в админку */
    admin?: boolean
    permission?: Permission
  }
}

/** Высота липкой шапки + небольшой зазор */
const HEADER_OFFSET = 80

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: ROUTE_PATH.home, name: 'landing', component: LandingPage },
    {
      // Публичная проверка договора по QR из PDF: без входа, без шапки сайта
      path: `${ROUTE_PATH.verify}/:id`,
      name: 'verify-contract',
      props: true,
      component: () => import('@/pages/verify-contract').then((module) => module.VerifyContractPage),
      meta: { title: 'Проверка договора', bare: true },
    },
    {
      path: ROUTE_PATH.profile,
      name: 'profile',
      component: () => import('@/pages/client-profile').then((module) => module.ClientProfilePage),
      meta: { title: 'Профиль' },
    },
    {
      path: ROUTE_PATH.support,
      name: 'support',
      component: () => import('@/pages/client-support').then((module) => module.ClientSupportPage),
      meta: { title: 'Поддержка' },
    },
    {
      path: `${ROUTE_PATH.support}/:id`,
      name: 'support-ticket',
      props: true,
      component: () => import('@/pages/client-support').then((module) => module.ClientSupportPage),
      meta: { title: 'Поддержка' },
    },
    // Ссылки ленты банка (link) в формате бэкенда: /backoffice/support/{id} и /backoffice/applications/{id} — в рабочее место
    {
      path: '/backoffice/support/:id',
      redirect: (to) => ({ name: ADMIN_ROUTE.supportTicket, params: { id: to.params.id } }),
    },
    {
      path: '/backoffice/applications/:id',
      redirect: (to) => ({ name: ADMIN_ROUTE.application, params: { id: to.params.id } }),
    },
    {
      path: `${ROUTE_PATH.admin}/login`,
      name: ADMIN_ROUTE.login,
      component: () => import('@/pages/admin-login').then((module) => module.AdminLoginPage),
      meta: { title: 'Вход для сотрудников', bare: true },
    },
    {
      path: ROUTE_PATH.admin,
      component: AdminLayout,
      meta: { bare: true, admin: true },
      children: [
        { path: '', redirect: { name: ADMIN_ROUTE.dashboard } },
        {
          path: 'dashboard',
          name: ADMIN_ROUTE.dashboard,
          component: () => import('@/pages/admin-dashboard').then((module) => module.BackofficeDashboardPage),
          meta: { title: 'Обзор', permission: 'requests.read' },
        },
        {
          path: 'applications',
          name: ADMIN_ROUTE.applications,
          component: () => import('@/pages/admin-applications').then((module) => module.BackofficeApplicationsPage),
          meta: { title: 'Заявки', permission: 'requests.read' },
        },
        {
          path: 'applications/:id',
          name: ADMIN_ROUTE.application,
          props: true,
          component: () => import('@/pages/admin-application').then((module) => module.BackofficeApplicationPage),
          meta: { title: 'Заявка', permission: 'requests.read' },
        },
        {
          path: 'inn-check',
          name: ADMIN_ROUTE.innCheck,
          component: () => import('@/pages/admin-inn-check').then((module) => module.AdminInnCheckPage),
          meta: { title: 'Проверка по ИНН', permission: 'backoffice.read' },
        },
        {
          path: 'support',
          name: ADMIN_ROUTE.support,
          component: () => import('@/pages/admin-support').then((module) => module.AdminSupportPage),
          meta: { title: 'Поддержка', permission: 'support.manage' },
        },
        {
          path: 'support/:id',
          name: ADMIN_ROUTE.supportTicket,
          props: true,
          component: () => import('@/pages/admin-support').then((module) => module.AdminSupportTicketPage),
          meta: { title: 'Обращение', permission: 'support.manage' },
        },
        {
          path: 'products',
          name: ADMIN_ROUTE.products,
          component: () => import('@/pages/admin-products').then((module) => module.AdminProductsPage),
          meta: { title: 'Продукты', permission: 'credits.read' },
        },
        {
          path: 'scoring',
          name: ADMIN_ROUTE.scoring,
          component: () => import('@/pages/admin-scoring').then((module) => module.AdminScoringPage),
          meta: { title: 'Скоринг', permission: 'backoffice.read' },
        },
        {
          path: 'versions',
          name: ADMIN_ROUTE.versions,
          component: () => import('@/pages/admin-versions').then((module) => module.AdminVersionsPage),
          meta: { title: 'Модель и политика', permission: 'scoring.read' },
        },
        {
          path: 'key-rate',
          name: ADMIN_ROUTE.keyRate,
          component: () => import('@/pages/admin-key-rate').then((module) => module.AdminKeyRatePage),
          meta: { title: 'Ключевая ставка', permission: 'scoring.read' },
        },
        {
          path: 'versions/:kind(model|policy)/:version',
          name: ADMIN_ROUTE.version,
          props: true,
          component: () => import('@/pages/admin-versions').then((module) => module.AdminVersionPage),
          meta: { title: 'Версия', permission: 'scoring.read' },
        },
        {
          path: 'users',
          name: ADMIN_ROUTE.users,
          component: () => import('@/pages/admin-users').then((module) => module.AdminUsersPage),
          meta: { title: 'Пользователи', permission: 'accounts.read' },
        },
        {
          path: 'roles',
          name: ADMIN_ROUTE.roles,
          component: () => import('@/pages/admin-roles').then((module) => module.AdminRolesPage),
          meta: { title: 'Роли и права', permission: 'roles.read' },
        },
        {
          path: 'profile',
          name: ADMIN_ROUTE.profile,
          component: () => import('@/pages/admin-profile').then((module) => module.AdminProfilePage),
          meta: { title: 'Профиль' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/pages/not-found').then((module) => module.NotFoundPage),
    },
  ],
  scrollBehavior(to, from, savedPosition) {
    // Первая загрузка и перезагрузка страницы — всегда с самого верха,
    // даже если в адресе остался якорь секции или сохранённая позиция
    if (from === START_LOCATION) return { top: 0 }
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, top: HEADER_OFFSET, behavior: 'smooth' }
    return { top: 0 }
  },
})

/** Первый раздел, который сотруднику разрешено открыть */
function firstAllowedRoute(): RouteLocationRaw | null {
  for (const group of ADMIN_NAVIGATION) {
    const item = group.items.find((entry) => session.can(entry.permission))
    if (item) return { name: item.route }
  }
  return null
}

router.beforeEach(async (to) => {
  if (to.name === ADMIN_ROUTE.login) {
    const me = await session.restore()
    return me && canEnterAdmin(me) ? (firstAllowedRoute() ?? true) : true
  }
  if (!to.meta.admin) return true

  const me = await session.restore()
  if (!me || !canEnterAdmin(me)) {
    return { name: ADMIN_ROUTE.login, query: { redirect: to.fullPath } }
  }
  if (to.meta.permission && !session.can(to.meta.permission)) {
    return firstAllowedRoute() ?? { name: ADMIN_ROUTE.login }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — ${APP_NAME}` : 'Кредитный кабинет для бизнеса'
})

// Токен истёк посреди работы — отправляем на вход и возвращаем обратно после него
onSessionExpired(() => {
  const current = router.currentRoute.value
  if (current.meta.admin) void router.push({ name: ADMIN_ROUTE.login, query: { redirect: current.fullPath } })
})

// Якорь секции в адресе после первой загрузки не нужен: убираем, чтобы F5 не прыгал вниз
router.isReady().then(() => {
  if (router.currentRoute.value.hash) router.replace({ ...router.currentRoute.value, hash: '' })
})
