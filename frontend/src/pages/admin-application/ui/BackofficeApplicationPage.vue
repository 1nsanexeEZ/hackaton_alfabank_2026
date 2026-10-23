<script setup lang="ts">
import { ADMIN_ROUTE } from '@/shared/config'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { UnderwriterCardView } from '@/widgets/underwriter-card'

/** Заявка в режиме real: карточка андеррайтера с бэкенда и решение по задаче */
defineProps<{ id: string }>()
</script>

<template>
  <AdminPageHeader title="Заявка" :back="{ name: ADMIN_ROUTE.applications }" back-label="Очередь" />
  <UnderwriterCardView :key="id" :application-id="id" />
</template>
