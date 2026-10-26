<script setup lang="ts">
import { computed } from 'vue'

import { useSession } from '@/entities/session'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { ApplicationsBoard } from '@/widgets/applications-board'

/** Обзор: панель модулей с графиками — заявки, метрики и очередь с бэкенда */
const { me } = useSession()

const greeting = computed(() => {
  const name = me.value?.profile?.first_name
  return name ? `Здравствуйте, ${name}` : 'Обзор'
})
</script>

<template>
  <AdminPageHeader :title="greeting" description="Главное по кредитному конвейеру: заявки, решения, воронка и очередь специалиста" />
  <ApplicationsBoard />
</template>
