<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { computed } from 'vue'

import { useSession } from '@/entities/session'
import { creditApi } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { useAsyncData } from '@/shared/lib'
import { AsyncState, BaseButton, PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { ApplicationsTable } from '@/widgets/applications-table'
import { DashboardOverview } from '@/widgets/dashboard-overview'

const { me } = useSession()

const stats = useAsyncData(() => creditApi.getDashboard())
const queue = useAsyncData(() => creditApi.listApplications({ status: 'active' }))

// Сначала просроченные, затем самые старые
const queueItems = computed(() =>
  [...(queue.data.value ?? [])].sort((a, b) => a.dueAt.localeCompare(b.dueAt)).slice(0, 6),
)

const greeting = computed(() => {
  const hour = new Date().getHours()
  const name = me.value?.profile?.first_name
  const base = hour < 12 ? 'Доброе утро' : hour < 18 ? 'Добрый день' : 'Добрый вечер'
  return name && name !== 'Admin' ? `${base}, ${name}` : base
})

function reload() {
  void stats.reload()
  void queue.reload()
}
</script>

<template>
  <AdminPageHeader :title="greeting" description="Сводка по кредитным заявкам малого бизнеса" />

  <AsyncState :loading="stats.loading.value" :error="stats.error.value" @retry="reload">
    <DashboardOverview v-if="stats.data.value" :stats="stats.data.value" />
  </AsyncState>

  <PanelCard title="Очередь на рассмотрение" description="Просроченные по SLA и самые старые сверху" flush class="mt-6">
    <template #actions>
      <BaseButton variant="secondary" size="s" :to="{ name: ADMIN_ROUTE.applications }">
        Все заявки
        <ArrowRight class="size-4" aria-hidden="true" />
      </BaseButton>
    </template>
    <AsyncState
      :loading="queue.loading.value"
      :error="queue.error.value"
      :empty="!queueItems.length"
      empty-text="Очередь пуста — все заявки рассмотрены"
      @retry="queue.reload"
    >
      <ApplicationsTable :items="queueItems" compact />
    </AsyncState>
  </PanelCard>
</template>
