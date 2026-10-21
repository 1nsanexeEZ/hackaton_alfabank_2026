import { createRouter, createWebHistory } from 'vue-router'

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
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, top: HEADER_OFFSET, behavior: 'smooth' }
    return { top: 0 }
  },
})
