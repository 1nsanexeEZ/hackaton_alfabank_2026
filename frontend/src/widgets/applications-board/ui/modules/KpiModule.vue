<script setup lang="ts">
import { BadgeCheck, Clock3, FileStack, Hourglass, type LucideIcon } from 'lucide-vue-next'
import { computed } from 'vue'

import { formatMoneyShort } from '@/shared/lib'

import { toAmount, useBoard } from '../../model/useBoardData'

const { overview, metrics } = useBoard()

const REVIEW = ['submitted', 'in_review', 'info_requested']

function duration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} с`
  if (seconds < 3600) return `${Math.round(seconds / 60)} мин`
  return `${(seconds / 3600).toFixed(1)} ч`
}

/**
 * Четыре плитки, а не шесть: в узкие подписи переносились. Сумма запросов — в подписи к заявкам,
 * доля автоматики — к времени решения.
 */
const tiles = computed<{ icon: LucideIcon; label: string; value: string; hint: string; accent?: boolean }[]>(() => {
  const data = overview.value
  const decided = data?.decided ?? 0
  const approved = data?.approved ?? 0
  const inReview = (data?.statuses ?? []).filter((item) => REVIEW.includes(item.key)).reduce((sum, item) => sum + item.count, 0)
  const requested = toAmount(data?.requested_amount)
  const share = metrics.value?.auto_decision_share
  return [
    {
      icon: FileStack,
      label: 'Заявок',
      value: String(data?.total ?? 0),
      hint: `подано ${data?.submitted ?? 0}${requested ? ` на ${formatMoneyShort(requested)}` : ''}`,
    },
    { icon: Hourglass, label: 'На рассмотрении', value: String(inReview), hint: 'ждут решения или данных' },
    {
      icon: BadgeCheck,
      label: 'Одобрено',
      value: decided ? `${Math.round((approved / decided) * 100)}%` : '—',
      hint: `${approved} из ${decided} решённых`,
      accent: true,
    },
    {
      icon: Clock3,
      label: 'Время до решения',
      value: duration(metrics.value?.avg_time_to_decision_sec),
      hint: share != null ? `автоматикой — ${Math.round(share * 100)}% решений` : 'в среднем за период',
    },
  ]
})
</script>

<template>
  <ul class="grid grid-cols-2 gap-4 xl:grid-cols-4" aria-label="Ключевые показатели">
    <li
      v-for="tile in tiles"
      :key="tile.label"
      class="rounded-2xl p-5"
      :class="tile.accent ? 'bg-night text-on-night' : 'bg-white ring-1 ring-line'"
    >
      <p class="flex items-center gap-2 text-sm font-medium" :class="tile.accent ? 'text-on-night' : 'text-ink'">
        <component :is="tile.icon" class="size-4 shrink-0" :class="tile.accent ? 'text-signal-ok' : 'text-brand'" aria-hidden="true" />
        {{ tile.label }}
      </p>
      <p class="mt-3 text-3xl font-bold whitespace-nowrap tabular-nums">{{ tile.value }}</p>
      <p class="mt-1 truncate text-xs" :class="tile.accent ? 'text-on-night-secondary' : 'text-ink-secondary'">{{ tile.hint }}</p>
    </li>
  </ul>
</template>
