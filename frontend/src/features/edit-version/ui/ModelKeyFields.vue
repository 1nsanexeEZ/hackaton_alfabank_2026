<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { getAt, hasAt } from '@/entities/scoring-version'
import { CATEGORY_LABEL, FACTOR_LABEL, label, SEGMENT_LABEL } from '@/entities/underwriting'
import type { ModelCatalogDto, VersionBody } from '@/shared/api'
import { SegmentedControl } from '@/shared/ui'

import DocField from './DocField.vue'

/**
 * Ключевое в документе PD-модели (pd_model_v2.yaml): пороги сегмента и флага, верхние границы PD
 * по грейдам, калибровка и баллы бинов каждой скоркарты. Границы бинов и состав признаков — в JSON.
 */
const props = defineProps<{
  body: VersionBody
  catalog: ModelCatalogDto | null
  errors: Record<string, string>
  readonly: boolean
}>()

interface Bin {
  label?: string
  from?: string
  to?: string
  category?: string
}

/** JSONB переставляет ключи документа — порядок берём из справочника, неизвестные ключи — в конец */
function ordered(keys: string[], order: readonly string[] | undefined): string[] {
  if (!order) return keys
  return [...order.filter((key) => keys.includes(key)), ...keys.filter((key) => !order.includes(key))]
}

const grades = computed(() => props.catalog?.grades ?? Object.keys((getAt(props.body, ['grades']) as object) ?? {}))
const segments = computed(() =>
  ordered(Object.keys((getAt(props.body, ['scorecards']) as object) ?? {}), props.catalog?.segments),
)
const segment = ref('')
watch(
  segments,
  (list) => {
    if (!list.includes(segment.value)) segment.value = list[0] ?? ''
  },
  { immediate: true },
)
const segmentOptions = computed(() => segments.value.map((code) => ({ value: code, label: label(SEGMENT_LABEL, code) })))

const features = computed(() => {
  const all = (getAt(props.body, ['scorecards', segment.value, 'features']) as Record<string, { bins?: Bin[] }>) ?? {}
  return ordered(Object.keys(all), props.catalog?.features.map((feature) => feature.code)).map((code) => [code, all[code]!] as const)
})

function range(bin: Bin): string {
  if (bin.category) return label(CATEGORY_LABEL, bin.category)
  if (bin.from === undefined) return `< ${bin.to}`
  if (bin.to === undefined) return `≥ ${bin.from}`
  return `${bin.from} … ${bin.to}`
}

const field = (path: (string | number)[]) => ({ body: props.body, path, errors: props.errors, readonly: props.readonly })
</script>

<template>
  <div class="space-y-6">
    <section>
      <h3 class="mb-3 text-sm font-semibold text-ink">Общее</h3>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <DocField
          v-if="hasAt(body, ['min_turnover_months'])"
          v-bind="field(['min_turnover_months'])"
          kind="int"
          unit="мес."
          label="Обороты в банке для скоркарты ЮЛ / ИП"
        />
        <DocField
          v-if="hasAt(body, ['revenue_mismatch_share'])"
          v-bind="field(['revenue_mismatch_share'])"
          kind="percent"
          unit="%"
          label="Расхождение выручки с ФНС для флага"
        />
      </div>
    </section>

    <section v-if="hasAt(body, ['grades'])">
      <h3 class="text-sm font-semibold text-ink">Границы грейдов</h3>
      <p class="mb-3 text-xs text-ink-secondary">PD строго меньше границы; выше границы последнего — грейд {{ catalog?.worst_grade ?? 'J' }}</p>
      <div class="grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-9">
        <DocField v-for="grade in grades" :key="grade" v-bind="field(['grades', grade])" kind="percent" unit="%" :label="`${grade}: PD до`" />
      </div>
    </section>

    <section v-if="segments.length">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 class="text-sm font-semibold text-ink">Скоркарта</h3>
        <SegmentedControl v-model="segment" :options="segmentOptions" label="Скоркарта какого сегмента" small />
      </div>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DocField v-bind="field(['scorecards', segment, 'base'])" kind="int" label="Константа, баллов" />
        <DocField v-bind="field(['scorecards', segment, 'calibration', 'score'])" kind="int" label="Калибровка: балл" />
        <DocField v-bind="field(['scorecards', segment, 'calibration', 'odds'])" kind="decimal" label="Шансы «хороший : плохой» на балле" />
        <DocField v-bind="field(['scorecards', segment, 'calibration', 'pdo'])" kind="int" label="Удвоение шансов, баллов" />
      </div>

      <div class="mt-4 space-y-4">
        <div v-for="[code, feature] in features" :key="`${segment}-${code}`" class="overflow-x-auto rounded-xl ring-1 ring-line">
          <table class="w-full min-w-[30rem] text-sm">
            <caption class="bg-surface-soft px-3 py-2 text-left font-medium text-ink">
              {{ label(FACTOR_LABEL, code) }} <span class="text-xs font-normal text-ink-muted">{{ code }}</span>
            </caption>
            <thead class="text-xs text-ink-secondary">
              <tr>
                <th scope="col" class="px-3 py-1.5 text-left font-medium">Бин</th>
                <th scope="col" class="px-3 py-1.5 text-left font-medium">Значения</th>
                <th scope="col" class="w-28 px-2 py-1.5 text-left font-medium">WoE</th>
                <th scope="col" class="w-28 px-2 py-1.5 text-left font-medium">Баллы</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(bin, index) in feature.bins ?? []" :key="index" class="border-t border-line">
                <td class="px-3 py-1.5 text-ink">{{ bin.label }}</td>
                <td class="px-3 py-1.5 text-ink-secondary tabular-nums">{{ range(bin) }}</td>
                <td class="px-2 py-1.5">
                  <DocField v-bind="field(['scorecards', segment, 'features', code, 'bins', index, 'woe'])" kind="decimal" hide-label :label="`${code} ${bin.label}: WoE`" />
                </td>
                <td class="px-2 py-1.5">
                  <DocField v-bind="field(['scorecards', segment, 'features', code, 'bins', index, 'points'])" kind="int" hide-label :label="`${code} ${bin.label}: баллы`" />
                </td>
              </tr>
              <tr v-if="hasAt(body, ['scorecards', segment, 'features', code, 'missing'])" class="border-t border-line">
                <td class="px-3 py-1.5 text-ink">нет данных</td>
                <td class="px-3 py-1.5 text-ink-secondary">—</td>
                <td class="px-2 py-1.5">
                  <DocField v-bind="field(['scorecards', segment, 'features', code, 'missing', 'woe'])" kind="decimal" hide-label :label="`${code} нет данных: WoE`" />
                </td>
                <td class="px-2 py-1.5">
                  <DocField v-bind="field(['scorecards', segment, 'features', code, 'missing', 'points'])" kind="int" hide-label :label="`${code} нет данных: баллы`" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>
