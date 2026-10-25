<script setup lang="ts">
import { CircleCheck, CircleX } from 'lucide-vue-next'
import { computed } from 'vue'

import type { UnderwriterCardDto } from '@/shared/api'
import { BaseBadge, PanelCard } from '@/shared/ui'

/** Соответствие продукту: сколько требований выполнено полосой и чек-лист — непройденные сверху */
const props = defineProps<{ fit: NonNullable<UnderwriterCardDto['product_fit']> }>()

const reasons = computed(() => [...props.fit.reasons].sort((a, b) => Number(a.passed) - Number(b.passed)))
const passed = computed(() => props.fit.reasons.filter((reason) => reason.passed).length)
const total = computed(() => props.fit.reasons.length)
</script>

<template>
  <PanelCard title="Соответствие продукту">
    <template #actions>
      <BaseBadge :tone="passed === total ? 'success' : 'brand'">{{ passed }} из {{ total }}</BaseBadge>
    </template>
    <div class="h-1.5 overflow-hidden rounded-full bg-surface-strong" aria-hidden="true">
      <div class="h-full rounded-full" :class="passed === total ? 'bg-success' : 'bg-brand'" :style="{ width: `${total ? (passed / total) * 100 : 0}%` }" />
    </div>
    <ul class="mt-2">
      <li v-for="reason in reasons" :key="reason.code" class="flex items-start gap-2 border-t border-line/60 py-2 text-sm first:border-t-0">
        <CircleCheck v-if="reason.passed" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <CircleX v-else class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
        <span :class="reason.passed ? 'text-ink' : 'font-semibold text-brand'">{{ reason.message }}</span>
      </li>
    </ul>
  </PanelCard>
</template>
