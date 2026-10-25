<script setup lang="ts">
import { BadgeCheck, Banknote, Bot, Clock3, FileStack, Hourglass, type LucideIcon } from 'lucide-vue-next'
import { computed } from 'vue'

import { formatMoneyShort } from '@/shared/lib'

import { amountOf, isSubmitted, useBoard } from '../../model/useBoardData'
import { FUNNEL } from '../../model/status'

const { applications, metrics } = useBoard()

const REVIEW = ['submitted', 'in_review', 'info_requested']

function duration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} с`
  if (seconds < 3600) return `${Math.round(seconds / 60)} мин`
  return `${(seconds / 3600).toFixed(1)} ч`
}

const tiles = computed<{ icon: LucideIcon; label: string; value: string; hint: string; accent?: boolean }[]>(() => {
  const list = applications.value
  const submitted = list.filter((item) => isSubmitted(item.status))
  const decided = list.filter((item) => FUNNEL[2]!.reached.includes(item.status)).length
  const approved = list.filter((item) => FUNNEL[3]!.reached.includes(item.status)).length
  const share = metrics.value?.auto_decision_share
  return [
    { icon: FileStack, label: 'Заявок', value: String(list.length), hint: `подано ${submitted.length}` },
    { icon: Hourglass, label: 'На рассмотрении', value: String(list.filter((item) => REVIEW.includes(item.status)).length), hint: 'ждут решения или данных' },
    { icon: Banknote, label: 'Запрошено', value: formatMoneyShort(submitted.reduce((sum, item) => sum + amountOf(item), 0)), hint: 'по поданным заявкам' },
    { icon: BadgeCheck, label: 'Одобрено', value: decided ? `${Math.round((approved / decided) * 100)}%` : '—', hint: `${approved} из ${decided} решённых`, accent: true },
    { icon: Bot, label: 'Решения автоматики', value: share != null ? `${Math.round(share * 100)}%` : '—', hint: 'от принятых за период' },
    { icon: Clock3, label: 'Время до решения', value: duration(metrics.value?.avg_time_to_decision_sec), hint: 'в среднем за период' },
  ]
})
</script>

<template>
  <ul class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
    <li
      v-for="tile in tiles"
      :key="tile.label"
      class="rounded-2xl p-4"
      :class="tile.accent ? 'bg-night text-on-night' : 'bg-surface-soft'"
    >
      <component :is="tile.icon" class="size-5" :class="tile.accent ? 'text-signal-ok' : 'text-brand'" aria-hidden="true" />
      <p class="mt-3 text-xl font-bold whitespace-nowrap tabular-nums">{{ tile.value }}</p>
      <p class="mt-0.5 text-sm font-medium" :class="tile.accent ? 'text-on-night' : 'text-ink'">{{ tile.label }}</p>
      <p class="text-xs" :class="tile.accent ? 'text-on-night-secondary' : 'text-ink-secondary'">{{ tile.hint }}</p>
    </li>
  </ul>
</template>
