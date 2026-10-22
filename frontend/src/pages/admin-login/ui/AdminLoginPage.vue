<script setup lang="ts">
import { ChartNoAxesCombined, FileSearch, ShieldCheck } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import { LoginForm } from '@/features/auth-by-login'
import { ADMIN_ROUTE, ROUTE_PATH } from '@/shared/config'
import { AppLogo, PatternBackground } from '@/shared/ui'

const route = useRoute()
const router = useRouter()

const FEATURES = [
  { icon: FileSearch, text: 'Проверки по ЕГРЮЛ, ФНС, ГИР БО и Контуру в одной карточке' },
  { icon: ChartNoAxesCombined, text: 'Объяснимый скоринг: видно, что повлияло на балл' },
  { icon: ShieldCheck, text: 'Доступ по ролям: аналитик, руководитель, администратор' },
]

function onSuccess() {
  // Возвращаем туда, куда сотрудник шёл до входа, но только внутри админки
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  if (redirect.startsWith(`${ROUTE_PATH.admin}/`)) void router.replace(redirect)
  else void router.replace({ name: ADMIN_ROUTE.dashboard })
}
</script>

<template>
  <div class="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
    <section class="relative flex flex-col overflow-hidden bg-night px-6 py-8 text-on-night sm:px-10 lg:px-14 lg:py-12">
      <PatternBackground />
      <!-- Рабочее место не связано с сайтом для клиентов: логотип без ссылки на него -->
      <AppLogo inverted class="relative self-start" />
      <div class="relative my-10 max-w-lg lg:my-auto">
        <p class="text-sm font-semibold tracking-wider text-brand uppercase">Для сотрудников банка</p>
        <h1 class="mt-3 text-3xl font-bold tracking-tight lg:text-5xl lg:leading-[1.1]">Рабочее место кредитного аналитика</h1>
        <ul class="mt-8 hidden space-y-4 sm:block">
          <li v-for="item in FEATURES" :key="item.text" class="flex items-start gap-3 text-on-night-secondary">
            <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-night-glass text-on-night">
              <component :is="item.icon" class="size-[18px]" aria-hidden="true" />
            </span>
            <span class="pt-1.5">{{ item.text }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section class="flex items-center justify-center px-4 py-10 sm:px-10">
      <div class="w-full max-w-md">
        <h2 class="text-2xl font-bold text-ink">Вход</h2>
        <p class="mt-1 mb-6 text-sm text-ink-secondary">Используйте учётную запись сотрудника</p>
        <LoginForm @success="onSuccess" />
      </div>
    </section>
  </div>
</template>
