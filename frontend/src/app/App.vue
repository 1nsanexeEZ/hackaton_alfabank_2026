<script setup lang="ts">
import { watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import { customer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'
import { ApplyFlowModals, openCabinet, openLogin, startApplication } from '@/widgets/apply-flow'

const route = useRoute()

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
    <AppHeader @apply="startApplication()" @login="openLogin" @open="openCabinet" />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
    <!-- Вход и заявка — модалки сайта, их открывают кнопки шапки и страниц -->
    <ApplyFlowModals />
  </div>
</template>
