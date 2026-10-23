<script setup lang="ts">
import { computed } from 'vue'

import { useSession } from '@/entities/session'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { BackofficeOverview } from '@/widgets/backoffice-overview'

/** Обзор в режиме real: метрики и очередь с бэкенда */
const { me } = useSession()

const greeting = computed(() => {
  const name = me.value?.profile?.first_name
  return name ? `Здравствуйте, ${name}` : 'Обзор'
})
</script>

<template>
  <AdminPageHeader :title="greeting" description="Кредитный конвейер: поданные заявки, авторешения и очередь специалиста" />
  <BackofficeOverview />
</template>
