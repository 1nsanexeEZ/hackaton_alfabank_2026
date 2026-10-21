<script setup lang="ts">
import type { ScoreResult } from '@/shared/api'

import { RISK_CLASS_META } from '../model/review'

/** Балл и класс риска одной плашкой: «72 · B» */
defineProps<{ score: Pick<ScoreResult, 'score' | 'riskClass'> }>()
</script>

<template>
  <span
    class="inline-flex h-7 items-center gap-1.5 rounded-full bg-surface px-2.5 text-xs font-semibold text-ink tabular-nums"
    :title="RISK_CLASS_META[score.riskClass].label"
  >
    <span class="size-2 rounded-full" :style="{ background: RISK_CLASS_META[score.riskClass].color }" aria-hidden="true" />
    {{ score.score }} · {{ score.riskClass }}
    <span class="sr-only">{{ RISK_CLASS_META[score.riskClass].label }}</span>
  </span>
</template>
