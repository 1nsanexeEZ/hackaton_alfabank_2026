<script setup lang="ts">
import { ADMIN_ROUTE } from '@/shared/config'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { UnderwriterCardView } from '@/widgets/underwriter-card'

/** Заявка в режиме real: карточка андеррайтера с бэкенда и решение по задаче */
defineProps<{ id: string }>()

// «Назад» — в тот список, откуда пришли: очередь или все заявки (?view=all)
const from = typeof window !== 'undefined' ? window.history.state?.back : null
const back = typeof from === 'string' && from.startsWith('/admin/applications?') ? from : { name: ADMIN_ROUTE.applications }
</script>

<template>
  <AdminPageHeader title="Заявка" :back="back" back-label="Заявки" />
  <UnderwriterCardView :key="id" :application-id="id" />
</template>
