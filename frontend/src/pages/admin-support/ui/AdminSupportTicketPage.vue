<script setup lang="ts">
import { StaffTicketView } from '@/features/handle-support-ticket'
import { ADMIN_ROUTE } from '@/shared/config'
import { AdminPageHeader } from '@/widgets/admin-layout'

/** Обращение в поддержку: сюда ведут и очередь, и записи ленты банка (/backoffice/support/{id}) */
defineProps<{ id: string }>()

// «Назад» — в тот вид очереди, откуда пришли
const from = typeof window !== 'undefined' ? window.history.state?.back : null
const back = typeof from === 'string' && from.startsWith('/admin/support') ? from : { name: ADMIN_ROUTE.support }
</script>

<template>
  <AdminPageHeader title="Обращение" :back="back" back-label="Поддержка" />
  <StaffTicketView :key="id" :ticket-id="id" />
</template>
