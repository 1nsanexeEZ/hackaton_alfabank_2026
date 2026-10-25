<script setup lang="ts">
import type { BadgeTone } from '@/shared/ui'
import { BaseBadge } from '@/shared/ui'

/**
 * Подблок внешних источников в одном виде: заголовок, итог проверки бейджем и содержимое.
 * wide — на всю ширину сетки: таблицы, графики, сравнения.
 */
withDefaults(defineProps<{ title: string; status?: { tone: BadgeTone; label: string } | null; wide?: boolean }>(), {
  status: null,
  wide: false,
})
</script>

<template>
  <section class="min-w-0 rounded-2xl p-4 ring-1 ring-line" :class="wide && '@xl:col-span-2'">
    <header class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-[0.9375rem] font-bold text-ink">{{ title }}</h3>
      <div class="flex flex-wrap items-center gap-1.5">
        <slot name="badges" />
        <BaseBadge v-if="status" :tone="status.tone">{{ status.label }}</BaseBadge>
      </div>
    </header>
    <slot />
  </section>
</template>
