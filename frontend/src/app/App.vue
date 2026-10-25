<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { assistant } from '@/entities/assistant'
import { customer } from '@/entities/customer'
import { LogoutTransition } from '@/features/customer-logout'
import { liveFeed } from '@/entities/notification'
import { ROUTE_PATH } from '@/shared/config'
import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'
import { ApplyFlowModals, openApplicationCard, openCabinet, openLogin, startApplication, type CabinetSection } from '@/widgets/apply-flow'
import { AssistantChat } from '@/widgets/assistant-chat'

const route = useRoute()
const router = useRouter()

/** Профиль и поддержка — отдельные страницы, остальные разделы кабинета пока модалками поверх сайта */
function openSection(section: CabinetSection | 'support') {
  if (section === 'profile') void router.push(ROUTE_PATH.profile)
  else if (section === 'support') void router.push(ROUTE_PATH.support)
  else openCabinet(section)
}

/** Вход из окна помощника: окно закрыто, поверх сайта — модалка входа */
function loginFromAssistant() {
  assistant.close()
  openLogin()
}

/** Ссылка на заявку в ответе помощника: окно закрываем, открывается карточка заявки */
function openApplicationFromAssistant(id: string) {
  assistant.close()
  openApplicationCard(id)
}

// Живая лента клиента — пока он вошёл на сайт; в рабочем месте сотрудника она не нужна
watch(
  () => (route.meta.bare ? null : (customer.state.me?.id ?? null)),
  (id) => (id ? liveFeed.start() : liveFeed.stop()),
  { immediate: true },
)
</script>

<template>
  <!-- Админка рисует свой каркас, шапка и подвал сайта ей не нужны -->
  <RouterView v-if="route.meta.bare" />
  <!-- data-app-shell: анимация входа поднимает сайт над красной заливкой и открывает его кругом -->
  <div v-else class="flex min-h-dvh flex-col" data-app-shell>
    <AppHeader @apply="startApplication()" @login="openLogin" @open="openSection" />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
    <!-- Вход и заявка — модалки сайта, их открывают кнопки шапки и страниц -->
    <ApplyFlowModals />
    <!-- Окно «Умного помощника» открывается кнопкой в шапке поверх любой страницы сайта -->
    <AssistantChat @login="loginFromAssistant" @open-application="openApplicationFromAssistant" />
  </div>
  <!-- Выход «чёрной дырой»: поверх всего и вне data-app-shell — сайт под ней гаснет и раскрывается главной -->
  <LogoutTransition />
</template>
