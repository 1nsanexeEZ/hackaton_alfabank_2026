<script setup lang="ts">
import { RouterView } from 'vue-router'

import { AppFooter } from '@/widgets/app-footer'
import { AppHeader } from '@/widgets/app-header'
</script>

<template>
  <div class="flex min-h-dvh flex-col">
    <AppHeader />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
  </div>
</template>
