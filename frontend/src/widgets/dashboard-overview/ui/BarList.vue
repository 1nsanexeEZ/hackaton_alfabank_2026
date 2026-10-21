<script setup lang="ts">
import { computed } from 'vue'

export interface BarItem {
  key: string
  label: string
  value: number
  /** Подпись справа вместо значения, например «4 · 12 млн ₽» */
  caption?: string
  /** Цвет полосы; по умолчанию — одна серия */
  color?: string
}

/** Горизонтальные полосы с подписями: одна серия, значение у конца полосы */
const props = defineProps<{ items: readonly BarItem[] }>()

const max = computed(() => Math.max(1, ...props.items.map((item) => item.value)))
</script>

<template>
  <ul class="space-y-3">
    <li v-for="item in items" :key="item.key" class="grid grid-cols-[11.5rem_1fr] items-center gap-3 text-sm" :title="`${item.label}: ${item.caption ?? item.value}`">
      <span class="flex min-w-0 items-center gap-2 text-ink">
        <span v-if="item.color" class="size-2 shrink-0 rounded-full" :style="{ background: item.color }" aria-hidden="true" />
        <span class="truncate">{{ item.label }}</span>
      </span>
      <span class="flex min-w-0 items-center gap-2">
        <span
          class="h-3 rounded-r"
          :style="{ width: `${(item.value / max) * 75}%`, minWidth: item.value ? '4px' : '0', background: item.color ?? 'var(--color-info)' }"
          aria-hidden="true"
        />
        <span class="shrink-0 font-semibold whitespace-nowrap text-ink tabular-nums">{{ item.caption ?? item.value }}</span>
      </span>
    </li>
  </ul>
</template>
