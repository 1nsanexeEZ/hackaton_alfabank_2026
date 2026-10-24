<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { GRADE_ZONE, gradeTone, label, OUTCOME_LABEL, REASON_LABEL, ZONE_LABEL, type GradeZone } from '@/entities/underwriting'
import type { Grade } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatMoney, formatProbability } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'

import { useScoredApplications, type ScoredApplication } from '../model/useScoredApplications'

/**
 * Скоринг по заявкам: как PD- и ML-модель оценили поданные заявки, согласны ли они, хватило ли
 * данных и что решили. Политика и модели — версиями, по которым считали
 */
const { items, total, loading, error, reload } = useScoredApplications()
const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

const GRADES: readonly Grade[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
const ZONES: readonly GradeZone[] = ['green', 'yellow', 'red']
const FINAL: readonly string[] = ['APPROVE', 'COUNTER_OFFER', 'REJECT']

const scored = computed(() => items.value.filter((item) => item.card.scoring))
const zonesOf = (item: ScoredApplication) => {
  const scoring = item.card.scoring!
  return { pd: GRADE_ZONE[scoring.grade], ml: scoring.ml ? GRADE_ZONE[scoring.ml.grade] : null }
}
const disagree = (item: ScoredApplication) => {
  const zones = zonesOf(item)
  return zones.ml !== null && zones.ml !== zones.pd
}
const degraded = (item: ScoredApplication) => item.card.scoring?.quality === 'degraded'

/** Стоп-фактор сработал до моделей: решение есть, скоринга нет */
const stoppedBefore = computed(() =>
  items.value.filter((item) => !item.card.scoring && item.card.decision?.reason_codes.some((code) => code.startsWith('STOP_'))),
)

const tiles = computed(() => {
  const list = scored.value
  const withMl = list.filter((item) => item.card.scoring?.ml)
  // Решение — одобрение, контрпредложение или отказ; ручная проверка и дозапрос — ещё не решение
  const final = items.value.filter((item) => FINAL.includes(item.card.decision?.outcome ?? ''))
  const auto = final.filter((item) => item.card.decision!.decided_by_type === 'auto')
  const share = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : '—')
  return [
    { label: `Оценено из ${total.value} последних поданных`, value: String(list.length) },
    { label: 'Отказ по стоп-фактору до моделей', value: String(stoppedBefore.value.length) },
    { label: 'Модели согласны по зоне', value: share(withMl.filter((item) => !disagree(item)).length, withMl.length) },
    { label: 'Неполные данные — решает человек', value: String(list.filter(degraded).length) },
    { label: 'Ушли специалисту', value: String(items.value.filter((item) => item.card.decision?.outcome === 'MANUAL_REVIEW').length) },
    { label: 'Решено автоматически', value: share(auto.length, final.length) },
  ]
})

/** Версии, по которым считали: модели и политика решения */
const versions = computed(() => {
  const count = (values: (string | undefined)[]) => {
    const map = new Map<string, number>()
    for (const value of values) if (value) map.set(value, (map.get(value) ?? 0) + 1)
    return [...map.entries()]
  }
  return [
    ...count(scored.value.map((item) => item.card.scoring!.model_version)).map(([version, n]) => ({ title: 'PD-модель', version, n })),
    ...count(scored.value.map((item) => item.card.scoring!.ml?.model_version)).map(([version, n]) => ({ title: 'ML-модель', version, n })),
    ...count(items.value.map((item) => item.card.decision?.policy_version)).map(([version, n]) => ({ title: 'Политика', version, n })),
  ]
})

/** Сколько заявок у каждого грейда — у PD- и у ML-модели */
const byGrade = computed(() => {
  const rows = GRADES.map((grade) => ({
    grade,
    pd: scored.value.filter((item) => item.card.scoring!.grade === grade).length,
    ml: scored.value.filter((item) => item.card.scoring!.ml?.grade === grade).length,
  }))
  const max = Math.max(1, ...rows.map((row) => Math.max(row.pd, row.ml)))
  return rows.map((row) => ({ ...row, pdWidth: (row.pd / max) * 100, mlWidth: (row.ml / max) * 100 }))
})

/** Строка — зона PD-модели, столбец — зона ML-модели */
const matrix = computed(() =>
  ZONES.map((pd) => ({
    pd,
    cells: ZONES.map((ml) => scored.value.filter((item) => zonesOf(item).pd === pd && zonesOf(item).ml === ml).length),
  })),
)

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
    if (filter.value === 'disagree') return item.card.scoring && disagree(item)
    if (filter.value === 'degraded') return degraded(item)
    if (filter.value === 'manual') return item.card.decision?.outcome === 'MANUAL_REVIEW' || item.card.decision?.decided_by_type === 'underwriter'
    return true
  }),
)

const pd = (value: string | null | undefined) => (value ? formatProbability(Number(value)) : '')
</script>

<template>
  <AsyncState :loading="loading && !items.length" :error="items.length ? null : error" :empty="!loading && !items.length" empty-text="Поданных заявок пока нет — оценивать нечего" @retry="reload">
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
        <p v-if="loading" class="text-xs text-ink-secondary">Загружаем карточки: {{ items.length }} из {{ total }}</p>
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
              <tr v-for="item in rows" :key="item.application.id" class="align-top">
                <td class="px-4 py-3">
                  <RouterLink
                    :to="{ name: ADMIN_ROUTE.application, params: { id: item.application.id } }"
                    class="font-semibold text-ink hover:text-brand"
                  >
                    {{ item.application.number }}
                  </RouterLink>
                  <p class="text-xs text-ink-secondary">{{ item.card.application.org_snapshot?.name ?? '' }}</p>
                  <p class="text-xs text-ink-secondary">
                    {{ productTitle(item.application.product_code) }}{{ item.application.amount ? ` · ${formatMoney(Number(item.application.amount))}` : '' }}
                  </p>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.card.scoring">
                    <BaseBadge :tone="gradeTone(item.card.scoring.grade)">{{ item.card.scoring.grade }}</BaseBadge>
                    <span class="ml-2 text-ink tabular-nums">{{ item.card.scoring.score }}</span>
                    <p class="text-xs text-ink-secondary">PD {{ pd(item.card.scoring.pd_12m) }}</p>
                  </template>
                  <span v-else class="text-xs text-ink-secondary">не считали</span>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.card.scoring?.ml">
                    <BaseBadge :tone="gradeTone(item.card.scoring.ml.grade)">{{ item.card.scoring.ml.grade }}</BaseBadge>
                    <span class="ml-2 text-ink tabular-nums">{{ item.card.scoring.ml.score }}</span>
                    <p class="text-xs" :class="disagree(item) ? 'text-warning' : 'text-ink-secondary'">
                      PD {{ pd(item.card.scoring.ml.pd_12m) }}{{ disagree(item) ? ' · зоны расходятся' : '' }}
                    </p>
                  </template>
                  <span v-else-if="item.card.scoring?.ml_not_applicable === 'no_revenue'" class="text-xs text-ink-secondary">
                    не применяется — нет выручки
                  </span>
                  <span v-else class="text-xs text-ink-secondary">—</span>
                </td>
                <td class="px-4 py-3 text-xs">
                  <span v-if="!item.card.scoring" class="text-ink-secondary">—</span>
                  <span v-else-if="degraded(item)" class="text-warning">неполные</span>
                  <span v-else class="text-ink-secondary">полные</span>
                </td>
                <td class="px-4 py-3">
                  <template v-if="item.card.decision">
                    <BaseBadge :tone="OUTCOME_LABEL[item.card.decision.outcome]?.tone ?? 'neutral'">
                      {{ OUTCOME_LABEL[item.card.decision.outcome]?.label ?? item.card.decision.outcome }}
                    </BaseBadge>
                    <span v-if="FINAL.includes(item.card.decision.outcome)" class="ml-2 text-xs text-ink-secondary">
                      {{ item.card.decision.decided_by_type === 'auto' ? 'автоматика' : 'специалист' }}
                    </span>
                    <p v-if="item.card.decision.reason_codes.length" class="mt-1 text-xs text-ink-secondary">
                      {{ item.card.decision.reason_codes.slice(0, 2).map((code) => label(REASON_LABEL, code)).join('; ') }}
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
