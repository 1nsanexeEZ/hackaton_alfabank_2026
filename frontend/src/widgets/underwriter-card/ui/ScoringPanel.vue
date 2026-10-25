<script setup lang="ts">
import { AlertTriangle, CircleCheck } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { CATEGORY_LABEL, FACTOR_LABEL, FLAG_LABEL, GRADE_ZONE, gradeTone, label, qualityReasonLabel, SEGMENT_LABEL, ZONE_LABEL, type GradeZone } from '@/entities/underwriting'
import type { FactorDto, Grade, ScoringDto } from '@/shared/api'
import { formatPercent, formatProbability } from '@/shared/lib'
import { BaseBadge, PanelCard, SegmentedControl } from '@/shared/ui'

/**
 * Две оценки риска (policy_v5): экспертная PD-модель и обученная ML-модель на одной шкале A–J.
 * Совпали зоны — решает автоматика, разошлись — человек; поэтому итог «согласны / расходятся» сверху.
 * Вклад признаков — столбиками от нуля: плюсы вправо зелёным, минусы влево красным, в одной шкале.
 */
const props = defineProps<{ scoring: ScoringDto }>()

type ScoringModel = 'pd' | 'ml'
const MODEL_TABS: readonly { value: ScoringModel; label: string }[] = [
  { value: 'pd', label: 'PD-модель' },
  { value: 'ml', label: 'ML-модель' },
]
const factorsOf = ref<ScoringModel>('pd')

const completeness = computed(() => Number(props.scoring.data_completeness) * 100)
const description = computed(() =>
  [props.scoring.scorecard && `Скоркарта ${props.scoring.scorecard}`, props.scoring.segment && (SEGMENT_LABEL[props.scoring.segment] ?? props.scoring.segment)]
    .filter(Boolean)
    .join(' · ') || undefined,
)

const models = computed(() => {
  const list: { key: ScoringModel; title: string; version: string; score: number; grade: Grade; pd: string | null }[] = [
    { key: 'pd', title: 'PD-модель', version: props.scoring.model_version, score: props.scoring.score, grade: props.scoring.grade, pd: props.scoring.pd_12m ?? null },
  ]
  const ml = props.scoring.ml
  if (ml) list.push({ key: 'ml', title: 'ML-модель', version: ml.model_version, score: ml.score, grade: ml.grade, pd: ml.pd_12m })
  return list
})

/** «Модели согласны — обе в жёлтой зоне» / «Модели расходятся: PD — зелёная, ML — красная» */
const ZONE_WORD: Record<GradeZone, { one: string; both: string }> = {
  green: { one: 'зелёная', both: 'зелёной' },
  yellow: { one: 'жёлтая', both: 'жёлтой' },
  red: { one: 'красная', both: 'красной' },
}
const verdict = computed(() => {
  const [pd, ml] = models.value
  if (!pd || !ml) return null
  const pdZone = GRADE_ZONE[pd.grade]
  const mlZone = GRADE_ZONE[ml.grade]
  if (pdZone === mlZone) return { text: `Модели согласны — обе в ${ZONE_WORD[pdZone].both} зоне`, good: pdZone === 'green' }
  return { text: `Модели расходятся: PD — ${ZONE_WORD[pdZone].one}, ML — ${ZONE_WORD[mlZone].one}`, good: false }
})

const ZONE_DOT: Record<GradeZone, string> = { green: 'bg-success', yellow: 'bg-warning', red: 'bg-brand' }

/** Значение и корзина признака по-русски; совпали (у категорий) — одно, без значения — только корзина */
const factorDetail = (factor: FactorDto) =>
  [...new Set([factor.value, factor.bin].filter((part): part is string => Boolean(part)).map((part) => CATEGORY_LABEL[part] ?? part))].join(' · ')

/** Признаки по убыванию вклада, минусы внизу; ширина столбика — в единой шкале плюсов и минусов */
const factors = computed(() => {
  const list = factorsOf.value === 'ml' && props.scoring.ml ? props.scoring.ml.factors : props.scoring.factors
  const sorted = [...list].sort((a, b) => b.points - a.points)
  const maxPos = Math.max(0, ...sorted.map((factor) => factor.points))
  const maxNeg = Math.max(0, ...sorted.map((factor) => -factor.points))
  const span = Math.max(1, maxPos + maxNeg)
  return {
    leftWidth: (maxNeg / span) * 100,
    rows: sorted.map((factor) => ({
      ...factor,
      detail: factorDetail(factor),
      positive: factor.points > 0 ? (factor.points / Math.max(1, maxPos)) * 100 : 0,
      negative: factor.points < 0 ? (-factor.points / Math.max(1, maxNeg)) * 100 : 0,
    })),
  }
})

const reasons = computed(() => (factorsOf.value === 'ml' && props.scoring.ml ? props.scoring.ml.reason_codes : props.scoring.reason_codes) ?? [])
</script>

<template>
  <PanelCard title="Скоринг" :description="description">
    <div>
      <div class="flex justify-between text-sm">
        <span class="text-ink-secondary">Полнота данных</span>
        <span class="font-semibold text-ink tabular-nums">{{ formatPercent(completeness) }}</span>
      </div>
      <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-strong" aria-hidden="true">
        <div class="h-full rounded-full bg-night" :style="{ width: `${Math.min(100, completeness)}%` }" />
      </div>
    </div>

    <p v-if="scoring.quality === 'degraded'" class="mt-3 flex items-start gap-2 rounded-xl bg-warning-soft p-3 text-sm text-ink">
      <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
      <span>
        <span class="font-semibold">Данные неполные — решает специалист</span>
        <template v-if="scoring.quality_reasons?.length">: {{ scoring.quality_reasons.map(qualityReasonLabel).join(', ') }}</template>
      </span>
    </p>

    <p
      v-if="verdict"
      class="mt-3 flex items-center gap-2 rounded-xl p-3 text-sm font-semibold"
      :class="verdict.good ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'"
    >
      <CircleCheck v-if="verdict.good" class="size-4 shrink-0" aria-hidden="true" />
      <AlertTriangle v-else class="size-4 shrink-0" aria-hidden="true" />
      {{ verdict.text }}
    </p>
    <p v-else-if="scoring.ml_not_applicable === 'no_revenue'" class="mt-3 text-xs text-ink-secondary">
      <span class="font-semibold text-ink">ML-модель не применяется</span> — у компании нет выручки ни в заявке, ни по ФНС. Модель обучена на действующих
      компаниях, и её оценка здесь была бы недостоверной. Риск оценивают PD-модель и андеррайтер.
    </p>
    <p v-else class="mt-3 text-xs text-ink-secondary">Оценки ML-модели нет: заявку оценили до того, как появилась вторая модель</p>

    <div class="mt-3 grid grid-cols-2 gap-2.5">
      <div v-for="model in models" :key="model.key" class="min-w-0 rounded-xl bg-surface-soft px-3.5 py-3">
        <p class="text-xs text-ink-secondary">{{ model.title }}</p>
        <p class="mt-1 flex flex-wrap items-center gap-2">
          <span class="text-2xl font-extrabold text-ink tabular-nums">{{ model.score }}</span>
          <BaseBadge :tone="gradeTone(model.grade)">{{ model.grade }}</BaseBadge>
        </p>
        <p v-if="model.pd" class="mt-1 text-xs text-ink-secondary">PD 12 мес. — {{ formatProbability(Number(model.pd)) }}</p>
        <p class="mt-1 flex items-center gap-1.5 text-xs text-ink">
          <span class="size-2 shrink-0 rounded-full" :class="ZONE_DOT[GRADE_ZONE[model.grade]]" aria-hidden="true" />
          {{ ZONE_LABEL[GRADE_ZONE[model.grade]]?.label ?? '—' }}
        </p>
        <p class="mt-1 truncate text-[11px] text-ink-secondary" :title="model.version">{{ model.version }}</p>
      </div>
    </div>

    <div v-if="scoring.flags.length" class="mt-3 flex flex-wrap gap-1.5">
      <BaseBadge v-for="flag in scoring.flags" :key="flag" tone="warning">{{ label(FLAG_LABEL, flag) }}</BaseBadge>
    </div>

    <div class="mt-5 flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-xs font-bold tracking-wide text-ink-secondary uppercase">Вклад признаков в балл</h3>
      <SegmentedControl v-if="models.length === 2" v-model="factorsOf" :options="MODEL_TABS" label="Признаки какой модели показать" small />
    </div>
    <p v-if="reasons.length" class="mt-2 text-xs text-ink-secondary">
      Сильнее всего снизили балл: <span class="font-semibold text-brand">{{ reasons.map((code) => label(FACTOR_LABEL, code)).join(', ') }}</span>
    </p>
    <ul class="mt-2">
      <li
        v-for="factor in factors.rows"
        :key="factor.code"
        class="grid grid-cols-[minmax(0,1fr)_6rem_2.25rem] items-center gap-2 border-t border-line/60 py-2 first:border-t-0"
      >
        <span class="min-w-0">
          <span class="block text-sm text-ink">{{ label(FACTOR_LABEL, factor.code) }}</span>
          <span v-if="factor.detail" class="block text-xs text-ink-secondary">{{ factor.detail }}</span>
          <span v-if="factor.client_hint" class="mt-0.5 block text-xs text-info">Клиенту: {{ factor.client_hint }}</span>
        </span>
        <span class="flex h-2.5" aria-hidden="true">
          <span class="flex justify-end border-r border-ink-muted" :style="{ width: `${factors.leftWidth}%` }">
            <span class="h-full rounded-l-sm bg-brand" :style="{ width: `${factor.negative}%` }" />
          </span>
          <span class="flex flex-1">
            <span class="h-full rounded-r-sm bg-success" :style="{ width: `${factor.positive}%` }" />
          </span>
        </span>
        <span
          class="text-right text-sm font-bold tabular-nums"
          :class="factor.points > 0 ? 'text-success' : factor.points < 0 ? 'text-brand' : 'text-ink-secondary'"
        >
          {{ factor.points > 0 ? '+' : factor.points < 0 ? '−' : '' }}{{ Math.abs(factor.points) }}
        </span>
      </li>
    </ul>
  </PanelCard>
</template>
