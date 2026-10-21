<script setup lang="ts">
import { ArrowRight, RotateCcw, Save } from 'lucide-vue-next'
import { computed, ref, shallowRef, watch } from 'vue'

import { DECISION_OUTCOME_META } from '@/entities/application'
import {
  creditApi,
  DEFAULT_SCORING_CONFIG,
  SCORING_FACTOR_LABEL,
  STOP_FACTOR_LABEL,
  type ScoringConfig,
  type ScoringFactorId,
  type ScoringPreviewRow,
  type StopFactorId,
} from '@/shared/api'
import { errorMessage, onlyDigits } from '@/shared/lib'
import { BaseBadge, BaseButton, PanelCard, SegmentedControl, TextField, ToggleSwitch } from '@/shared/ui'

/**
 * Настройки скоринга с примеркой: пока черновик не сохранён, видно,
 * у каких заявок поменяется рекомендация.
 */
const props = defineProps<{ config: ScoringConfig; readonly?: boolean }>()
const emit = defineEmits<{ saved: [config: ScoringConfig] }>()

const WEIGHT_OPTIONS = [
  { value: '0', label: 'Выкл' },
  { value: '0.5', label: '×0,5' },
  { value: '1', label: '×1' },
  { value: '1.5', label: '×1,5' },
  { value: '2', label: '×2' },
] as const

type WeightValue = (typeof WEIGHT_OPTIONS)[number]['value']

const FACTORS = Object.keys(SCORING_FACTOR_LABEL) as ScoringFactorId[]
const STOPS = Object.keys(STOP_FACTOR_LABEL) as StopFactorId[]

const draft = ref<ScoringConfig>(structuredClone(props.config))
watch(() => props.config, (config) => (draft.value = structuredClone(config)))

const thresholds = ref({ approve: '', counter: '', percent: '' })
watch(
  draft,
  (value) => {
    thresholds.value = {
      approve: String(value.approveFrom),
      counter: String(value.counterFrom),
      percent: String(value.counterAmountPercent),
    }
  },
  { immediate: true },
)

function setThreshold(key: 'approve' | 'counter' | 'percent', raw: string) {
  thresholds.value[key] = raw
  const value = Math.min(100, Number(onlyDigits(raw)) || 0)
  if (key === 'approve') draft.value.approveFrom = value
  if (key === 'counter') draft.value.counterFrom = value
  if (key === 'percent') draft.value.counterAmountPercent = value
}

function weightModel(id: ScoringFactorId) {
  return computed<WeightValue>({
    get: () => String(draft.value.weights[id]) as WeightValue,
    set: (value) => (draft.value.weights[id] = Number(value)),
  })
}
const weights = Object.fromEntries(FACTORS.map((id) => [id, weightModel(id)])) as Record<
  ScoringFactorId,
  ReturnType<typeof weightModel>
>

const isDirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(props.config))
const error = ref<string | null>(null)
const pending = ref(false)

const preview = shallowRef<ScoringPreviewRow[]>([])
let previewTimer: ReturnType<typeof setTimeout> | undefined
watch(
  draft,
  () => {
    clearTimeout(previewTimer)
    previewTimer = setTimeout(async () => {
      try {
        preview.value = await creditApi.previewScoring(draft.value)
      } catch {
        preview.value = []
      }
    }, 200)
  },
  { deep: true, immediate: true },
)

const changed = computed(() => preview.value.filter((row) => row.before.recommendation !== row.after.recommendation))

async function save() {
  error.value = null
  if (draft.value.counterFrom > draft.value.approveFrom) {
    error.value = 'Порог встречного предложения не может быть выше порога одобрения'
    return
  }
  pending.value = true
  try {
    emit('saved', await creditApi.updateScoringConfig(draft.value))
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}

function resetToDefaults() {
  draft.value = structuredClone(DEFAULT_SCORING_CONFIG)
}
</script>

<template>
  <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_26rem]">
    <div class="min-w-0 space-y-6">
      <PanelCard title="Веса факторов" description="Базовый балл 50, каждый фактор добавляет или снимает баллы; вес усиливает его влияние">
        <fieldset :disabled="readonly" class="@container">
          <ul class="divide-y divide-line">
            <li v-for="id in FACTORS" :key="id" class="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 @lg:flex-row @lg:items-center @lg:justify-between">
              <span class="text-sm font-medium text-ink">{{ SCORING_FACTOR_LABEL[id] }}</span>
              <SegmentedControl v-model="weights[id].value" :options="WEIGHT_OPTIONS" :label="`Вес: ${SCORING_FACTOR_LABEL[id]}`" small />
            </li>
          </ul>
        </fieldset>
      </PanelCard>

      <PanelCard title="Стоп-факторы" description="Любой включённый стоп-фактор ведёт к отказу независимо от балла">
        <div class="space-y-4">
          <ToggleSwitch v-for="id in STOPS" :key="id" v-model="draft.stopFactors[id]" :label="STOP_FACTOR_LABEL[id]" :disabled="readonly" />
        </div>
      </PanelCard>

      <PanelCard title="Пороги решения">
        <fieldset :disabled="readonly" class="grid gap-3 sm:grid-cols-3">
          <TextField
            :model-value="thresholds.approve"
            label="Одобрить от, баллов"
            inputmode="numeric"
            dense
            @update:model-value="setThreshold('approve', $event)"
          />
          <TextField
            :model-value="thresholds.counter"
            label="Другие условия от"
            inputmode="numeric"
            dense
            hint="Ниже — отказ"
            @update:model-value="setThreshold('counter', $event)"
          />
          <TextField
            :model-value="thresholds.percent"
            label="Доля суммы во встречном, %"
            inputmode="numeric"
            dense
            @update:model-value="setThreshold('percent', $event)"
          />
        </fieldset>
      </PanelCard>
    </div>

    <aside class="space-y-4 xl:sticky xl:top-8">
      <PanelCard title="Примерка на заявках" :description="isDirty ? 'Черновик не сохранён' : 'Совпадает с текущими настройками'" flush>
        <p class="px-5 pb-3 text-sm text-ink">
          Рекомендация изменится у <b class="font-semibold">{{ changed.length }}</b> из {{ preview.length }} заявок
        </p>
        <ul v-if="changed.length" class="max-h-80 divide-y divide-line overflow-y-auto border-t border-line">
          <li v-for="row in changed" :key="row.applicationId" class="px-5 py-3 text-sm">
            <p class="flex justify-between gap-2">
              <span class="truncate font-medium text-ink">{{ row.applicantName }}</span>
              <span class="shrink-0 text-ink-secondary tabular-nums">{{ row.before.score }} → {{ row.after.score }}</span>
            </p>
            <p class="mt-1.5 flex flex-wrap items-center gap-1.5">
              <BaseBadge :tone="DECISION_OUTCOME_META[row.before.recommendation].tone">{{ DECISION_OUTCOME_META[row.before.recommendation].action }}</BaseBadge>
              <ArrowRight class="size-3.5 text-ink-muted" aria-hidden="true" />
              <BaseBadge :tone="DECISION_OUTCOME_META[row.after.recommendation].tone">{{ DECISION_OUTCOME_META[row.after.recommendation].action }}</BaseBadge>
            </p>
          </li>
        </ul>
      </PanelCard>

      <p v-if="error" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>

      <div v-if="!readonly" class="flex flex-wrap gap-2">
        <BaseButton :disabled="!isDirty" :loading="pending" @click="save">
          <Save class="size-4" aria-hidden="true" />
          Сохранить
        </BaseButton>
        <BaseButton variant="secondary" @click="resetToDefaults">
          <RotateCcw class="size-4" aria-hidden="true" />
          По умолчанию
        </BaseButton>
      </div>
      <p v-else class="rounded-xl bg-white px-4 py-3 text-sm text-ink-secondary ring-1 ring-line">
        Только просмотр: настройки скоринга меняет администратор. Примерка работает и без сохранения.
      </p>
    </aside>
  </div>
</template>
