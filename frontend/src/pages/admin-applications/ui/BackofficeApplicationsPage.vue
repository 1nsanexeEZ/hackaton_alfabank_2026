<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { SegmentedControl } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { AllApplications } from '@/widgets/all-applications'
import { UnderwriterQueue } from '@/widgets/underwriter-queue'

/**
 * Заявки в режиме real: очередь специалиста — то, что не решилось автоматически, — и все заявки банка,
 * включая черновики и решённые автоматикой. Выбранный вид — в адресе (?view=all), чтобы «Назад» из
 * карточки возвращал туда же.
 */
type View = 'queue' | 'all'
const VIEWS: readonly { value: View; label: string }[] = [
  { value: 'queue', label: 'Очередь задач' },
  { value: 'all', label: 'Все заявки' },
]

const route = useRoute()
const router = useRouter()
const view = computed<View>({
  get: () => (route.query.view === 'all' ? 'all' : 'queue'),
  set: (next) => void router.replace({ query: { ...route.query, view: next === 'all' ? 'all' : undefined } }),
})
</script>

<template>
  <AdminPageHeader
    title="Заявки"
    :description="
      view === 'all'
        ? 'Все заявки банка: черновики, на рассмотрении, решённые автоматикой и специалистом'
        : 'Очередь специалиста: заявки, которые конвейер передал на ручное рассмотрение'
    "
  >
    <template #actions>
      <SegmentedControl v-model="view" :options="VIEWS" label="Что показать" />
    </template>
  </AdminPageHeader>
  <AllApplications v-if="view === 'all'" />
  <UnderwriterQueue v-else />
</template>
