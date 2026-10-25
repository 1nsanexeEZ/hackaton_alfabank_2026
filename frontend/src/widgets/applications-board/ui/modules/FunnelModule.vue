<script setup lang="ts">
import { computed } from 'vue'

import { FUNNEL } from '../../model/status'
import { useBoard } from '../../model/useBoardData'

const { applications } = useBoard()

/** Этап: сколько дошли, доля от начатых и переход с предыдущего этапа */
const stages = computed(() => {
  const all = applications.value.length
  return FUNNEL.map((stage, index) => {
    const count = index === 0 ? all : applications.value.filter((item) => stage.reached.includes(item.status)).length
    return { label: stage.label, count, share: all ? count / all : 0 }
  }).map((stage, index, list) => {
    const previous = list[index - 1]
    return { ...stage, conversion: previous && previous.count ? Math.round((stage.count / previous.count) * 100) : null }
  })
})
</script>

<template>
  <ol class="space-y-2.5">
    <li v-for="(stage, index) in stages" :key="stage.label" class="grid grid-cols-[8.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
      <span class="truncate text-ink-secondary">{{ stage.label }}</span>
      <div class="flex h-9 items-center justify-center rounded-lg bg-surface">
        <div
          class="funnel__bar flex h-full items-center justify-center rounded-lg text-xs font-semibold text-white"
          :style="{ width: `${Math.max(stage.share * 100, stage.count ? 8 : 0)}%`, background: index === stages.length - 1 ? 'var(--color-success)' : `rgb(239 49 36 / ${1 - index * 0.13})` }"
        >
          {{ stage.count || '' }}
        </div>
      </div>
      <span class="text-right text-xs tabular-nums" :class="stage.conversion === null ? 'text-ink-muted' : 'text-ink-secondary'">
        {{ stage.conversion === null ? '' : `${stage.conversion}%` }}
      </span>
    </li>
  </ol>
  <p class="mt-3 text-xs text-ink-secondary">Справа — сколько заявок перешли с предыдущего этапа</p>
</template>

<style scoped>
.funnel__bar {
  transition: width 0.6s ease;
}

@media (prefers-reduced-motion: reduce) {
  .funnel__bar {
    transition: none;
  }
}
</style>
