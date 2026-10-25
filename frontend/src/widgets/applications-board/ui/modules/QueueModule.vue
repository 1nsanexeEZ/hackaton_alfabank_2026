<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { REASON_LABEL } from '@/entities/underwriting'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatRelativeTime } from '@/shared/lib'

import { useBoard } from '../../model/useBoardData'

const SHOWN = 3

const { queue } = useBoard()

const items = computed(() => queue.value?.items ?? [])
const overdue = computed(() => items.value.filter((item) => item.overdue).length)
const unassigned = computed(() => items.value.filter((item) => !item.assignee_id).length)

/** Ближайшие по сроку — их разбирать первыми; без срока — в конце */
const nearest = computed(() =>
  [...items.value].sort((a, b) => (a.due_at ?? '9999').localeCompare(b.due_at ?? '9999')).slice(0, SHOWN),
)
</script>

<template>
  <div>
    <div class="grid grid-cols-3 gap-2 text-center">
      <div class="rounded-xl bg-surface-soft px-2 py-3">
        <p class="text-xl font-bold tabular-nums">{{ queue?.total ?? 0 }}</p>
        <p class="text-xs text-ink-secondary">ждут решения</p>
      </div>
      <div class="rounded-xl px-2 py-3" :class="overdue ? 'bg-brand-soft text-brand' : 'bg-surface-soft'">
        <p class="text-xl font-bold tabular-nums">{{ overdue }}</p>
        <p class="text-xs" :class="overdue ? 'text-brand' : 'text-ink-secondary'">просрочено по SLA</p>
      </div>
      <div class="rounded-xl bg-surface-soft px-2 py-3">
        <p class="text-xl font-bold tabular-nums">{{ unassigned }}</p>
        <p class="text-xs text-ink-secondary">никто не взял</p>
      </div>
    </div>

    <ul v-if="nearest.length" class="mt-4 divide-y divide-line">
      <li v-for="item in nearest" :key="item.task_id">
        <RouterLink :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }" class="group flex items-center gap-3 py-2.5">
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-ink group-hover:text-brand">{{ item.company_name }}</span>
            <span class="block truncate text-xs text-ink-secondary">
              {{ item.routing_reasons[0] ? (REASON_LABEL[item.routing_reasons[0]] ?? item.routing_reasons[0]) : item.number }}
            </span>
          </span>
          <span v-if="item.due_at" class="shrink-0 text-xs" :class="item.overdue ? 'font-semibold text-brand' : 'text-ink-secondary'">
            {{ formatRelativeTime(item.due_at) }}
          </span>
        </RouterLink>
      </li>
    </ul>
    <p v-else class="mt-4 text-sm text-ink-secondary">Очередь пуста — всё решила автоматика</p>

    <RouterLink :to="{ name: ADMIN_ROUTE.applications }" class="mt-3 flex items-center gap-1 text-sm font-medium text-ink-secondary hover:text-brand">
      Открыть очередь
      <ChevronRight class="size-4" aria-hidden="true" />
    </RouterLink>
  </div>
</template>
