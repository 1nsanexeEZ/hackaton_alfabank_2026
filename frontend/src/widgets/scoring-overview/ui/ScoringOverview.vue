<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { gradeTone, label, OUTCOME_LABEL, REASON_LABEL, ZONE_LABEL, type GradeZone } from '@/entities/underwriting'
import type { ScoredApplicationDto } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatMoney, formatProbability } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'

import { useScoringOverview } from '../model/useScoringOverview'

/**
 * Скоринг по заявкам: как PD- и ML-модель оценили поданные заявки, согласны ли они, хватило ли
 * данных и что решили. Политика и модели — версиями, по которым считали. Всё считает бэкенд одной ручкой
 */
const { data, loading, error, reload } = useScoringOverview()
const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

const ZONES: readonly GradeZone[] = ['green', 'yellow', 'red']
const FINAL: readonly string[] = ['APPROVE', 'COUNTER_OFFER', 'REJECT']
const VERSION_TITLE = { pd: 'PD-модель', ml: 'ML-модель', policy: 'Политика' } as const

const items = computed(() => data.value?.items ?? [])
const degraded = (item: ScoredApplicationDto) => item.quality === 'degraded'

const tiles = computed(() => {
  const overview = data.value
  if (!overview) return []
  const share = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : '—')
  return [
    { label: `Оценено из ${overview.considered} последних поданных`, value: String(overview.scored) },
    { label: 'Отказ по стоп-фактору до моделей', value: String(overview.stopped_before_models) },
    { label: 'Модели согласны по зоне', value: share(overview.models_agree, overview.with_ml) },
    { label: 'Неполные данные — решает человек', value: String(overview.degraded) },
    { label: 'Ушли специалисту', value: String(overview.manual_review) },
    { label: 'Решено автоматически', value: share(overview.decided_auto, overview.decided) },
  ]
})

/** Версии, по которым считали: модели и политика решения */
const versions = computed(() =>
  (data.value?.versions ?? []).map((item) => ({ title: VERSION_TITLE[item.kind], version: item.version, n: item.count })),
)

/** Сколько заявок у каждого грейда — у PD- и у ML-модели */
const byGrade = computed(() => {
  const rows = data.value?.by_grade ?? []
  const max = Math.max(1, ...rows.map((row) => Math.max(row.pd, row.ml)))
  return rows.map((row) => ({ ...row, pdWidth: (row.pd / max) * 100, mlWidth: (row.ml / max) * 100 }))
})

/** Строка — зона PD-модели, столбец — зона ML-модели */
const matrix = computed(() => {
  const zones = data.value?.zones ?? []
  return ZONES.map((pd) => ({
    pd,
    cells: ZONES.map((ml) => zones.find((pair) => pair.pd_zone === pd && pair.ml_zone === ml)?.count ?? 0),
  }))
})

type Filter = 'all' | 'disagree' | 'degraded' | 'manual'
const filter = ref<Filter>('all')
const FILTERS: readonly { value: Filter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'disagree', label: 'Модели расходятся' },
  { value: 'degraded', label: 'Неполные данные' },
  { value: 'manual', label: 'Ручная проверка' },
]
const rows = computed(() =>
  items.value.filter((item) => {
    if (filter.value === 'disagree') return item.models_disagree
    if (filter.value === 'degraded') return degraded(item)
    if (filter.value === 'manual') return item.outcome === 'MANUAL_REVIEW' || item.decided_by_type === 'underwriter'
    return true
  }),
)

const pd = (value: string | null | undefined) => (value ? formatProbability(Number(value)) : '')
</script>

<template>
  <AsyncState :loading="loading && !data" :error="data ? null : error" :empty="!loading && !data?.considered" empty-text="Поданных заявок пока нет — оценивать нечего" @retry="reload">
    <div class="space-y-4">
      <ul class="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <li v-for="tile in tiles" :key="tile.label" class="rounded-card bg-white p-4 ring-1 ring-line">
          <p class="text-2xl font-bold text-ink tabular-nums">{{ tile.value }}</p>
          <p class="mt-1 text-xs text-ink-secondary">{{ tile.label }}</p>
        </li>
      </ul>

      <div v-if="versions.length" class="flex flex-wrap gap-2">
        <BaseBadge v-for="item in versions" :key="`${item.title}${item.version}`" tone="info">
          {{ item.title }} {{ item.version }} · {{ item.n }}
        </BaseBadge>
      </div>

      <div class="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
        <PanelCard title="Грейды" description="Сколько заявок получили грейд — у PD- и у ML-модели, шкала A–J общая">
          <ul class="space-y-1.5" role="img" aria-label="Распределение заявок по грейдам у двух моделей">
            <li v-for="row in byGrade" :key="row.grade" class="grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-3">
              <BaseBadge :tone="gradeTone(row.grade)" class="justify-center">{{ row.grade }}</BaseBadge>
              <div class="space-y-0.5">
                <div class="flex items-center gap-2">
                  <span class="h-2.5 rounded-full bg-ink" :style="{ width: `${row.pdWidth}%` }" />
                  <span class="text-xs text-ink-secondary tabular-nums">{{ row.pd }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="h-2.5 rounded-full bg-brand" :style="{ width: `${row.mlWidth}%` }" />
                  <span class="text-xs text-ink-secondary tabular-nums">{{ row.ml }}</span>
                </div>
              </div>
            </li>
          </ul>
          <p class="mt-3 flex gap-4 text-xs text-ink-secondary">
            <span class="flex items-center gap-1.5"><span class="size-2.5 rounded-full bg-ink" aria-hidden="true" />PD-модель</span>
            <span class="flex items-center gap-1.5"><span class="size-2.5 rounded-full bg-brand" aria-hidden="true" />ML-модель</span>
          </p>
        </PanelCard>

        <PanelCard title="Зоны двух моделей" description="Строка — зона PD-модели, столбец — ML-модели. Расходятся — заявка уходит специалисту">
          <div class="overflow-x-auto">
            <table class="w-full min-w-[20rem] text-sm">
              <thead class="text-xs text-ink-secondary">
                <tr>
                  <th class="py-2 text-left font-medium">PD \ ML</th>
                  <th v-for="zone in ZONES" :key="zone" class="py-2 font-medium">{{ ZONE_LABEL[zone].label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in matrix" :key="row.pd" class="border-t border-line">
                  <th scope="row" class="py-3 text-left font-medium text-ink">{{ ZONE_LABEL[row.pd].label }}</th>
                  <td v-for="(count, index) in row.cells" :key="index" class="py-3 text-center tabular-nums">
                    <span
                      class="inline-flex min-w-9 justify-center rounded-lg px-2 py-1 font-semibold"
                      :class="count ? (ZONES[index] === row.pd ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning') : 'text-ink-muted'"
                    >
                      {{ count }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </PanelCard>
      </div>

      <PanelCard flush>
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <SegmentedControl v-model="filter" :options="FILTERS" label="Какие заявки показать" small />
          <BaseButton size="s" variant="secondary" :loading="loading" @click="reload">Обновить</BaseButton>
        </div>
        <p v-if="!rows.length" class="p-4 text-sm text-ink-secondary">Таких заявок нет</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[56rem] text-left text-sm">
            <thead class="text-xs text-ink-secondary">
              <tr class="border-b border-line">
                <th class="px-4 py-3 font-medium">Заявка</th>
                <th class="px-4 py-3 font-medium">PD-модель</th>
                <th class="px-4 py-3 font-medium">ML-модель</th>
                <th class="px-4 py-3 font-medium">Данные</th>
                <th class="px-4 py-3 font-medium">Решение</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="item in rows" :key="item.application_id" class="align-top">
                <td class="px-4 py-3">
                  <RouterLink
                    :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }"
                    class="font-semibold text-ink hover:text-brand"
                  >
                    {{ item.number }}
                  </RouterLink>
                  <p class="text-xs text-ink-secondary">{{ item.company_name ?? '' }}</p>
                  <p class="text-xs text-ink-secondary">
                    {{ productTitle(item.product_code) }}{{ item.amount ? ` · ${formatMoney(Number(item.amount))}` : '' }}
                  </p>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.grade">
                    <BaseBadge :tone="gradeTone(item.grade)">{{ item.grade }}</BaseBadge>
                    <span class="ml-2 text-ink tabular-nums">{{ item.score }}</span>
                    <p class="text-xs text-ink-secondary">PD {{ pd(item.pd_12m) }}</p>
                  </template>
                  <span v-else class="text-xs text-ink-secondary">не считали</span>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.ml_grade">
                    <BaseBadge :tone="gradeTone(item.ml_grade)">{{ item.ml_grade }}</BaseBadge>
                    <span class="ml-2 text-ink tabular-nums">{{ item.ml_score }}</span>
                    <p class="text-xs" :class="item.models_disagree ? 'text-warning' : 'text-ink-secondary'">
                      PD {{ pd(item.ml_pd_12m) }}{{ item.models_disagree ? ' · зоны расходятся' : '' }}
                    </p>
                  </template>
                  <span v-else-if="item.ml_not_applicable === 'no_revenue'" class="text-xs text-ink-secondary">
                    не применяется — нет выручки
                  </span>
                  <span v-else class="text-xs text-ink-secondary">—</span>
                </td>
                <td class="px-4 py-3 text-xs">
                  <span v-if="!item.grade" class="text-ink-secondary">—</span>
                  <span v-else-if="degraded(item)" class="text-warning">неполные</span>
                  <span v-else class="text-ink-secondary">полные</span>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.outcome">
                    <BaseBadge :tone="OUTCOME_LABEL[item.outcome]?.tone ?? 'neutral'">
                      {{ OUTCOME_LABEL[item.outcome]?.label ?? item.outcome }}
                    </BaseBadge>
                    <span v-if="FINAL.includes(item.outcome)" class="ml-2 text-xs text-ink-secondary">
                      {{ item.decided_by_type === 'auto' ? 'автоматика' : 'специалист' }}
                    </span>
                    <p v-if="item.reason_codes.length" class="mt-1 text-xs text-ink-secondary">
                      {{ item.reason_codes.slice(0, 2).map((code) => label(REASON_LABEL, code)).join('; ') }}
                    </p>
                  </template>
                  <span v-else class="text-xs text-ink-secondary">ещё нет</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PanelCard>
    </div>
  </AsyncState>
</template>
