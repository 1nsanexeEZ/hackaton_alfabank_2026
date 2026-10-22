<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'

import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'
import { ApplyFlowModals, openLogin, startApplication } from '@/widgets/apply-flow'

const route = useRoute()
</script>

<template>
  <!-- Админка рисует свой каркас, шапка и подвал сайта ей не нужны -->
  <RouterView v-if="route.meta.bare" />
  <div v-else class="flex min-h-dvh flex-col">
    <AppHeader @apply="startApplication()" @login="openLogin" />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
    <!-- Вход и заявка — модалки сайта, их открывают кнопки шапки и страниц -->
    <ApplyFlowModals />
  </div>
</template>
