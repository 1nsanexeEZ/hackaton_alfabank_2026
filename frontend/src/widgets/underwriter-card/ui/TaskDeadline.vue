<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { formatDuration } from '@/shared/lib'

/** Срок задачи полосой: сколько прошло от создания и сколько осталось до срока; просрочка — красным */
const props = defineProps<{ createdAt: string; dueAt: string }>()

const now = ref(Date.now())
let timer: number | undefined
onMounted(() => {
  timer = window.setInterval(() => (now.value = Date.now()), 60_000)
})
onBeforeUnmount(() => window.clearInterval(timer))

const progress = computed(() => {
  const start = new Date(props.createdAt).getTime()
  const end = new Date(props.dueAt).getTime()
  const spent = Math.max(0, now.value - start)
  const left = end - now.value
  const total = Math.max(1, end - start)
  return { spent, left, width: Math.min(100, (spent / total) * 100), overdue: left < 0, late: left >= 0 && left < total * 0.2 }
})
</script>

<template>
  <div class="mb-4 rounded-xl bg-surface-soft px-3.5 py-3">
    <div
      class="h-2 overflow-hidden rounded-full bg-surface-strong"
      role="img"
      :aria-label="progress.overdue ? `Срок задачи прошёл ${formatDuration(-progress.left)} назад` : `Осталось ${formatDuration(progress.left)} до срока задачи`"
    >
      <div
        class="h-full rounded-full"
        :class="progress.overdue ? 'bg-brand' : progress.late ? 'bg-warning' : 'bg-info'"
        :style="{ width: `${progress.width}%` }"
      />
    </div>
    <div class="mt-1.5 flex justify-between gap-3 text-xs text-ink-secondary">
      <span>прошло {{ formatDuration(progress.spent) }}</span>
      <span v-if="progress.overdue" class="font-semibold text-brand">просрочено на {{ formatDuration(-progress.left) }}</span>
      <span v-else :class="progress.late && 'font-semibold text-warning'">осталось {{ formatDuration(progress.left) }}</span>
    </div>
  </div>
</template>
