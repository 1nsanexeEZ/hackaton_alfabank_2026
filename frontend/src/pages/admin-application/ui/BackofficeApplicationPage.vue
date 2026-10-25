<script setup lang="ts">
import { computed, ref } from 'vue'

import { ADMIN_ROUTE } from '@/shared/config'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { UnderwriterCardView } from '@/widgets/underwriter-card'

/** Заявка в режиме real: карточка андеррайтера с бэкенда и решение по задаче */
defineProps<{ id: string }>()

// «Назад» — в тот список, откуда пришли: очередь или все заявки (?view=all)
const from = typeof window !== 'undefined' ? window.history.state?.back : null
const back = typeof from === 'string' && from.startsWith('/admin/applications?') ? from : { name: ADMIN_ROUTE.applications }

/** Номер заявки приходит с карточкой — до этого в заголовке просто «Заявка» */
const number = ref<string | null>(null)
const title = computed(() => (number.value ? `Заявка ${number.value}` : 'Заявка'))
</script>

<template>
  <AdminPageHeader :title="title" :back="back" back-label="Заявки" />
  <UnderwriterCardView :key="id" :application-id="id" @loaded="number = $event" />
</template>
