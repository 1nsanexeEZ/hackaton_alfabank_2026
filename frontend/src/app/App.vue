<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { customer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { ROUTE_PATH } from '@/shared/config'
import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'
import { ApplyFlowModals, openCabinet, openLogin, startApplication, type CabinetSection } from '@/widgets/apply-flow'

const route = useRoute()
const router = useRouter()

/** Профиль — отдельная страница, остальные разделы кабинета пока модалками поверх сайта */
function openSection(section: CabinetSection) {
  if (section === 'profile') void router.push(ROUTE_PATH.profile)
  else openCabinet(section)
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
  <div v-else class="flex min-h-dvh flex-col">
    <AppHeader @apply="startApplication()" @login="openLogin" @open="openSection" />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
    <!-- Вход и заявка — модалки сайта, их открывают кнопки шапки и страниц -->
    <ApplyFlowModals />
  </div>
</template>
