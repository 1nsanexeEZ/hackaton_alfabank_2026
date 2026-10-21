<script setup lang="ts">
import { CircleAlert, FileQuestion, OctagonX } from 'lucide-vue-next'
import { computed } from 'vue'

import type { ScoreResult } from '@/shared/api'
import { formatMoney } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import { DECISION_OUTCOME_META, RISK_CLASS_META } from '../model/review'

/**
 * Объяснение скоринга: итоговый балл, рекомендация, стоп-факторы и вклад каждого фактора.
 * Полоса фактора растёт от центра: вправо — снижает риск, влево — повышает.
 */
const props = defineProps<{ score: ScoreResult }>()

const risk = computed(() => RISK_CLASS_META[props.score.riskClass])
const recommendation = computed(() => DECISION_OUTCOME_META[props.score.recommendation])
const maxImpact = computed(() => Math.max(12, ...props.score.factors.map((factor) => Math.abs(factor.impact))))

// Дуга шкалы: полуокружность длиной 100 условных единиц
const gaugeDash = computed(() => `${props.score.score} 100`)
</script>

<template>
  <!-- Раскладка по ширине карточки, а не экрана: карточка бывает и широкой, и узкой колонкой -->
  <div class="@container">
    <div class="grid gap-6 @2xl:grid-cols-[13rem_1fr]">
      <div class="flex flex-col items-center text-center">
        <svg viewBox="0 0 120 70" class="w-48" aria-hidden="true">
          <path d="M10 60a50 50 0 0 1 100 0" fill="none" stroke="var(--color-surface-strong)" stroke-width="10" stroke-linecap="round" />
          <path
            d="M10 60a50 50 0 0 1 100 0"
            fill="none"
            :stroke="risk.color"
            stroke-width="10"
            stroke-linecap="round"
            pathLength="100"
            :stroke-dasharray="gaugeDash"
          />
        </svg>
        <p class="-mt-10 text-4xl font-bold text-ink tabular-nums">{{ score.score }}</p>
        <p class="mt-1 text-sm text-ink-secondary">из 100 · класс {{ score.riskClass }}</p>
        <BaseBadge :tone="risk.tone" class="mt-3">{{ risk.label }}</BaseBadge>
        <div class="mt-4 w-full rounded-xl bg-surface-soft p-3 text-sm">
          <p class="text-ink-secondary">Рекомендация</p>
          <p class="mt-0.5 font-semibold text-ink">{{ recommendation.action }}</p>
          <p v-if="score.suggestedAmount" class="mt-0.5 text-ink-secondary">на {{ formatMoney(score.suggestedAmount) }}</p>
        </div>
      </div>

      <div class="space-y-4">
        <div v-if="score.stopFactors.length" class="rounded-xl bg-brand-soft p-4">
          <p class="flex items-center gap-2 text-sm font-semibold text-brand">
            <OctagonX class="size-4" aria-hidden="true" />
            Стоп-факторы
          </p>
          <ul class="mt-2 space-y-1 text-sm text-ink">
            <li v-for="item in score.stopFactors" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div v-if="score.missingData.length" class="rounded-xl bg-info-soft p-4">
          <p class="flex items-center gap-2 text-sm font-semibold text-info">
            <FileQuestion class="size-4" aria-hidden="true" />
            Не хватает данных
          </p>
          <ul class="mt-2 space-y-1 text-sm text-ink">
            <li v-for="item in score.missingData" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div>
          <p class="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            <CircleAlert class="size-4 text-ink-secondary" aria-hidden="true" />
            Вклад факторов в балл
          </p>
          <ul class="space-y-2.5">
            <li v-for="factor in score.factors" :key="factor.id" class="grid grid-cols-[minmax(0,1fr)_6rem_2.5rem] items-center gap-3 text-sm @md:grid-cols-[minmax(0,1fr)_9rem_2.5rem]">
              <span class="min-w-0">
                <span class="block truncate font-medium text-ink">{{ factor.label }}</span>
                <span class="block truncate text-xs text-ink-secondary">{{ factor.detail }}</span>
              </span>
              <span class="relative h-2 rounded-full bg-surface" aria-hidden="true">
                <span class="absolute inset-y-0 left-1/2 w-px bg-ink-muted" />
                <span
                  class="absolute inset-y-0 rounded-full"
                  :class="factor.impact >= 0 ? 'left-1/2 bg-success' : 'right-1/2 bg-brand'"
                  :style="{ width: `${(Math.abs(factor.impact) / maxImpact) * 50}%` }"
                />
              </span>
              <span
                class="text-right font-semibold tabular-nums"
                :class="factor.impact > 0 ? 'text-success' : factor.impact < 0 ? 'text-brand' : 'text-ink-secondary'"
              >
                {{ factor.impact > 0 ? '+' : '' }}{{ factor.impact }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
