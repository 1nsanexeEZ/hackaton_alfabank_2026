/** Якоря секций лендинга: на них ссылаются шапка, футер и кнопки внутри страницы */
export const SECTION_ID = {
  picker: 'picker',
  products: 'products',
  calculator: 'calculator',
  process: 'process',
  faq: 'faq',
} as const

export type SectionId = (typeof SECTION_ID)[keyof typeof SECTION_ID]

/**
 * Ссылка на секцию лендинга с любой страницы.
 * На главной браузер просто прокрутит к якорю, с других страниц — откроет главную.
 */
export function sectionHref(id: SectionId): string {
  return `${import.meta.env.BASE_URL}#${id}`
}

/** Пункты навигации по лендингу — общие для шапки и футера */
export const LANDING_NAV: readonly { label: string; section: SectionId }[] = [
  { label: 'Продукты', section: SECTION_ID.products },
  { label: 'Калькулятор', section: SECTION_ID.calculator },
  { label: 'Как это работает', section: SECTION_ID.process },
  { label: 'Вопросы', section: SECTION_ID.faq },
]

export const ROUTE_PATH = {
  home: '/',
  login: '/login',
  admin: '/admin',
  /** Публичная проверка договора по QR: /verify/<id документа> */
  verify: '/verify',
} as const

/** Имена маршрутов рабочего места сотрудника */
export const ADMIN_ROUTE = {
  login: 'admin-login',
  dashboard: 'admin-dashboard',
  applications: 'admin-applications',
  application: 'admin-application',
  innCheck: 'admin-inn-check',
  products: 'admin-products',
  scoring: 'admin-scoring',
  users: 'admin-users',
  roles: 'admin-roles',
  profile: 'admin-profile',
} as const

export type AdminRouteName = (typeof ADMIN_ROUTE)[keyof typeof ADMIN_ROUTE]

export const APP_NAME = 'Кредитный кабинет'
export const APP_TAGLINE = 'для малого бизнеса'
