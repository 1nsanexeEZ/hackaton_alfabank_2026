<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'

import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'

const route = useRoute()
</script>

<template>
  <!-- Админка рисует свой каркас, шапка и подвал сайта ей не нужны -->
  <RouterView v-if="route.meta.bare" />
  <div v-else class="flex min-h-dvh flex-col">
    <AppHeader />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
  </div>
</template>
