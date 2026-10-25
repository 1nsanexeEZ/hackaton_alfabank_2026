<script setup lang="ts">
import { computed } from 'vue'

import type { VersionKind } from '@/entities/scoring-version'
import { CATEGORY_LABEL, FACTOR_LABEL, label, REGISTRY_STATUS_LABEL, SEGMENT_LABEL } from '@/entities/underwriting'
import type { ModelCatalogDto, PolicyCatalogDto } from '@/shared/api'
import { BaseBadge } from '@/shared/ui'

/** Справочник для правки документа (GET …/catalog): из чего он собирается и какие коды допустимы */
const props = defineProps<{ kind: VersionKind; catalog: ModelCatalogDto | PolicyCatalogDto }>()

const model = computed(() => (props.kind === 'model' ? (props.catalog as ModelCatalogDto) : null))
const policy = computed(() => (props.kind === 'policy' ? (props.catalog as PolicyCatalogDto) : null))

const policyLists = computed(() => {
  const catalog = policy.value
  if (!catalog) return []
  return [
    { title: 'Шкала PD-модели', items: catalog.pd_scale },
    { title: 'Шкала scorecard_v1', items: catalog.legacy_scale },
    { title: 'Ключи stop_factors', items: catalog.stop_factors },
    { title: 'Статусы ЕГРЮЛ', items: catalog.registry_statuses.map((code) => `${code} — ${label(REGISTRY_STATUS_LABEL, code)}`) },
    { title: 'Флаги routing.flags', items: catalog.routing_flags },
    { title: 'Зоны двух моделей', items: catalog.zones },
    { title: 'Клетки матрицы', items: catalog.zone_verdicts },
    { title: 'Уровни ЗСК', items: catalog.zsk_levels },
    { title: 'Формы для согласия на авторешение', items: catalog.legal_forms },
    { title: 'Виды залога (limits.ltv)', items: catalog.collateral_types.map((item) => `${item.code} — ${item.name}`) },
    { title: 'Продукты для alternatives', items: catalog.products.map((item) => `${item.code} — ${item.name}`) },
  ]
})
</script>

<template>
  <div v-if="model" class="space-y-5 text-sm">
    <p class="text-ink-secondary">
      Встроенная версия — <b class="font-semibold text-ink">{{ model.builtin }}</b>. Сегменты:
      {{ model.segments.map((code) => label(SEGMENT_LABEL, code)).join(', ') }}. Грейды с границей PD: {{ model.grades.join(', ') }}, выше —
      {{ model.worst_grade }}. Отраслевые секции: {{ model.industry_sections.join(', ') }}.
    </p>
    <div class="overflow-x-auto rounded-xl ring-1 ring-line">
      <table class="w-full min-w-[36rem]">
        <thead class="bg-surface-soft text-xs text-ink-secondary">
          <tr>
            <th scope="col" class="px-3 py-2 text-left font-medium">Признак</th>
            <th scope="col" class="px-3 py-2 text-left font-medium">Бины</th>
            <th scope="col" class="px-3 py-2 text-left font-medium">Категории с обязательным бином</th>
            <th scope="col" class="px-3 py-2 text-left font-medium">Обязателен</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="feature in model.features" :key="feature.code" class="border-t border-line">
            <td class="px-3 py-2">
              <p class="text-ink">{{ label(FACTOR_LABEL, feature.code) }}</p>
              <code class="text-xs text-ink-muted">{{ feature.code }}</code>
            </td>
            <td class="px-3 py-2 text-ink-secondary">{{ feature.kind === 'numeric' ? 'интервалы [from; to)' : 'категории' }}</td>
            <td class="px-3 py-2 text-ink-secondary">
              {{ feature.categories.length ? feature.categories.map((code) => `${code} (${label(CATEGORY_LABEL, code)})`).join(', ') : '—' }}
            </td>
            <td class="px-3 py-2">{{ feature.required ? 'в каждой скоркарте' : 'нет' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div v-else-if="policy" class="space-y-5 text-sm">
    <p class="text-ink-secondary">Встроенная версия — <b class="font-semibold text-ink">{{ policy.builtin }}</b>.</p>
    <dl class="grid gap-4 sm:grid-cols-2">
      <div v-for="list in policyLists" :key="list.title">
        <dt class="mb-1 text-xs font-medium text-ink-secondary">{{ list.title }}</dt>
        <dd class="flex flex-wrap gap-1.5">
          <BaseBadge v-for="item in list.items" :key="item">{{ item }}</BaseBadge>
        </dd>
      </div>
    </dl>
    <div>
      <p class="mb-2 text-xs font-medium text-ink-secondary">Исходы и тексты для клиента</p>
      <ul class="space-y-1">
        <li v-for="item in policy.outcomes" :key="item.code"><code class="text-xs text-ink-muted">{{ item.code }}</code> — {{ item.name }}</li>
      </ul>
    </div>
    <div class="overflow-x-auto rounded-xl ring-1 ring-line">
      <table class="w-full min-w-[36rem]">
        <caption class="bg-surface-soft px-3 py-2 text-left text-xs font-medium text-ink-secondary">
          Коды причин: код без текста в документе — ошибка 422, тексты через API не правятся
        </caption>
        <tbody>
          <tr v-for="reason in policy.reasons" :key="reason.code" class="border-t border-line align-top">
            <td class="px-3 py-2"><code class="text-xs text-ink">{{ reason.code }}</code></td>
            <td class="px-3 py-2 text-ink">
              {{ reason.text }}
              <p v-if="reason.hint" class="text-xs text-ink-secondary">{{ reason.hint }}</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
