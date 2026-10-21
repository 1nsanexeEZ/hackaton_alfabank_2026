import { START_LOCATION, createRouter, createWebHistory } from 'vue-router'

import { LandingPage } from '@/pages/landing'
import { ROUTE_PATH } from '@/shared/config'

/** Высота липкой шапки + небольшой зазор */
const HEADER_OFFSET = 80

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: ROUTE_PATH.home, name: 'landing', component: LandingPage },
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

// Якорь секции в адресе после первой загрузки не нужен: убираем, чтобы F5 не прыгал вниз
router.isReady().then(() => {
  if (router.currentRoute.value.hash) router.replace({ ...router.currentRoute.value, hash: '' })
})
