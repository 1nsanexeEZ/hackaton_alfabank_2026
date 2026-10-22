<script setup lang="ts">
import { Lightbulb } from 'lucide-vue-next'

import type { ClientDecisionDto } from '@/shared/api'
import { BaseButton } from '@/shared/ui'

/** Решение банка понятными словами: почему так, что улучшить, какой продукт подойдёт вместо */
defineProps<{
  decision: ClientDecisionDto
  /** Название альтернативного продукта из каталога */
  alternativeTitle: string | null
  tone: 'neutral' | 'negative'
}>()

const emit = defineEmits<{ applyProduct: [code: string] }>()
</script>

<template>
  <section class="rounded-2xl p-5" :class="tone === 'negative' ? 'bg-brand-soft' : 'bg-surface-soft'">
    <p class="text-sm text-ink">{{ decision.client_explanation }}</p>

    <div v-if="decision.improvement_hints.length" class="mt-4">
      <p class="flex items-center gap-2 text-sm font-semibold text-ink">
        <Lightbulb class="size-4 text-warning" aria-hidden="true" />
        Что поможет в следующий раз
      </p>
      <ul class="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
        <li v-for="hint in decision.improvement_hints" :key="hint">{{ hint }}</li>
      </ul>
    </div>

    <div v-if="decision.alternative_product_code" class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-3">
      <p class="text-sm text-ink">
        Банк советует продукт <b>«{{ alternativeTitle ?? decision.alternative_product_code }}»</b>
      </p>
      <BaseButton size="s" variant="secondary" @click="emit('applyProduct', decision.alternative_product_code)">
        Оформить его
      </BaseButton>
    </div>
  </section>
</template>
