<script setup lang="ts">
import { computed } from 'vue'

import { getAt, hasAt, pathKey, setAt } from '@/entities/scoring-version'
import { ZONE_LABEL, type GradeZone } from '@/entities/underwriting'
import type { Grade, PolicyCatalogDto, VersionBody } from '@/shared/api'

import DocField from './DocField.vue'
import ReasonTextsField from './ReasonTextsField.vue'

/**
 * Ключевое в документе кредитной политики (policy_v10.yaml): стоп-факторы, две модели, матрица
 * грейд × сумма, лимиты и ставка, мягкие триггеры, тексты причин для клиента. У старых версий части разделов
 * нет — их не показываем. Требования закона и остальное — в JSON.
 */
const props = defineProps<{
  body: VersionBody
  catalog: PolicyCatalogDto | null
  errors: Record<string, string>
  readonly: boolean
}>()

const VERDICT_LABEL: Record<string, string> = {
  approve: 'одобрить',
  check: 'проверка',
  dispute: 'спорная',
  reject: 'отказ',
}

const STOP_NUMBERS: { key: string; label: string; kind: 'int' | 'money' | 'percent'; unit?: string }[] = [
  { key: 'overdue_days', label: 'Просрочка в БКИ за 12 мес. больше', kind: 'int', unit: 'дн.' },
  { key: 'current_overdue_days', label: 'Текущая просрочка больше', kind: 'int', unit: 'дн.' },
  { key: 'tax_arrears_above', label: 'Недоимка ФНС больше', kind: 'money', unit: '₽' },
  { key: 'enforcement_revenue_share', label: 'Долг у приставов от выручки больше', kind: 'percent', unit: '%' },
  { key: 'lawsuits_revenue_share', label: 'Иски ответчиком от выручки больше', kind: 'percent', unit: '%' },
]

const STOP_FLAGS: { key: string; label: string }[] = [
  { key: 'before_scoring', label: 'Проверять до модели, отдельным шагом' },
  { key: 'account_blocks', label: 'Блокировки счетов ФНС' },
  { key: 'bankruptcy_messages', label: 'Сообщения о банкротстве' },
  { key: 'negative_equity', label: 'Отрицательный капитал по ГИР БО' },
  { key: 'mass_address', label: 'Массовый адрес' },
  { key: 'unreliable_data', label: 'Недостоверные сведения ЕГРЮЛ' },
  { key: 'mass_head', label: 'Массовый руководитель' },
  { key: 'business_age', label: 'Срок работы меньше минимума продукта' },
  { key: 'bank_stop_list', label: 'Внутренний стоп-лист банка' },
]

const PRICING: { key: string; label: string; kind: 'decimal' | 'percent'; unit: string }[] = [
  { key: 'funding_spread', label: 'Спред фондирования к ключевой', kind: 'decimal', unit: 'п.п.' },
  { key: 'capital', label: 'Капитал', kind: 'decimal', unit: 'п.п.' },
  { key: 'margin', label: 'Маржа', kind: 'decimal', unit: 'п.п.' },
  { key: 'lgd_unsecured', label: 'LGD без залога', kind: 'percent', unit: '%' },
  { key: 'lgd_secured', label: 'LGD с залогом', kind: 'percent', unit: '%' },
  { key: 'pd_if_unknown', label: 'PD, если модель её не дала', kind: 'percent', unit: '%' },
]

const scale = computed<Grade[]>(() => props.catalog?.pd_scale ?? ((getAt(props.body, ['grades']) as Grade[]) ?? []))
const zoneNames = computed(() => props.catalog?.zones ?? ['green', 'yellow', 'red'])
const verdicts = computed(() => props.catalog?.zone_verdicts ?? Object.keys(VERDICT_LABEL))

const TWO_MODELS = ['strategy', 'two_models'] as const
const zones = computed(() => getAt(props.body, [...TWO_MODELS, 'zones']) as Record<string, Grade[]> | undefined)
const riskMatrix = computed(() => (getAt(props.body, ['strategy', 'risk_matrix']) as { label: string; grades: Grade[] }[]) ?? [])

const zoneOf = (grade: Grade) => Object.entries(zones.value ?? {}).find(([, list]) => list.includes(grade))?.[0]

/** Грейд — ровно в одной зоне: убираем из прежней, ставим в новую по порядку шкалы */
function moveGrade(grade: Grade, zone: string) {
  const current = zones.value
  if (!current || props.readonly) return
  for (const name of Object.keys(current)) current[name] = current[name]!.filter((item) => item !== grade)
  current[zone] = scale.value.filter((item) => item === grade || current[zone]?.includes(item))
}

const cell = (row: string, column: string) => getAt(props.body, [...TWO_MODELS, 'matrix', row, column]) as string | undefined
const setCell = (row: string, column: string, verdict: string) => setAt(props.body, [...TWO_MODELS, 'matrix', row, column], verdict)

const zoneTitle = (zone: string) => ZONE_LABEL[zone as GradeZone]?.label ?? zone
const field = (path: (string | number)[]) => ({ body: props.body, path, errors: props.errors, readonly: props.readonly })
</script>

<template>
  <div class="space-y-6">
    <section v-if="hasAt(body, ['stop_factors'])">
      <h3 class="mb-3 text-sm font-semibold text-ink">Стоп-факторы</h3>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <template v-for="item in STOP_NUMBERS" :key="item.key">
          <DocField
            v-if="hasAt(body, ['stop_factors', item.key])"
            v-bind="field(['stop_factors', item.key])"
            :kind="item.kind"
            :unit="item.unit"
            :label="item.label"
          />
        </template>
      </div>
      <div class="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        <template v-for="item in STOP_FLAGS" :key="item.key">
          <DocField v-if="hasAt(body, ['stop_factors', item.key])" v-bind="field(['stop_factors', item.key])" kind="bool" :label="item.label" />
        </template>
      </div>
    </section>

    <section v-if="zones">
      <h3 class="text-sm font-semibold text-ink">Две модели</h3>
      <p class="mb-3 text-xs text-ink-secondary">Зона по грейду одинакова для PD- и ML-модели; строка — зона PD-модели, столбец — ML-модели</p>
      <div class="flex flex-wrap gap-2">
        <div v-for="grade in scale" :key="grade" class="rounded-lg bg-surface-soft p-2 text-center">
          <p class="text-sm font-semibold text-ink">{{ grade }}</p>
          <select
            :value="zoneOf(grade)"
            :disabled="readonly"
            :aria-label="`Зона грейда ${grade}`"
            class="mt-1 h-8 rounded-md bg-white px-1.5 text-xs text-ink ring-1 ring-line"
            @change="moveGrade(grade, ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="zone in zoneNames" :key="zone" :value="zone">{{ zoneTitle(zone) }}</option>
          </select>
        </div>
      </div>
      <p v-if="errors[pathKey([...TWO_MODELS, 'zones'])]" class="mt-1 text-xs text-brand">{{ errors[pathKey([...TWO_MODELS, 'zones'])] }}</p>

      <div class="mt-4 overflow-x-auto">
        <table class="text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="px-2 py-1.5 text-left font-medium">PD \ ML</th>
              <th v-for="column in zoneNames" :key="column" scope="col" class="px-2 py-1.5 text-left font-medium">{{ zoneTitle(column) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in zoneNames" :key="row" class="border-t border-line">
              <th scope="row" class="px-2 py-1.5 text-left font-medium text-ink">{{ zoneTitle(row) }}</th>
              <td v-for="column in zoneNames" :key="column" class="px-2 py-1.5">
                <select
                  :value="cell(row, column)"
                  :disabled="readonly"
                  :aria-label="`PD ${zoneTitle(row)}, ML ${zoneTitle(column)}`"
                  class="h-9 rounded-lg bg-surface px-2 text-sm text-ink"
                  @change="setCell(row, column, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="verdict in verdicts" :key="verdict" :value="verdict">{{ VERDICT_LABEL[verdict] ?? verdict }}</option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="riskMatrix.length">
      <h3 class="text-sm font-semibold text-ink">Матрица грейд × сумма</h3>
      <p class="mb-3 text-xs text-ink-secondary">До «авто» — может одобрить автоматика, до «вручную» — проверка, выше — отказ</p>
      <div class="grid gap-3 sm:grid-cols-2">
        <div v-for="(bucket, index) in riskMatrix" :key="bucket.label" class="rounded-xl bg-surface-soft p-3">
          <p class="mb-2 text-sm font-medium text-ink">{{ bucket.label }} <span class="text-xs font-normal text-ink-muted">{{ bucket.grades.join(', ') }}</span></p>
          <div class="grid grid-cols-2 gap-2">
            <DocField v-bind="field(['strategy', 'risk_matrix', index, 'approve_up_to'])" kind="money" unit="₽" label="Авто до" />
            <DocField
              v-if="hasAt(body, ['strategy', 'risk_matrix', index, 'manual_up_to'])"
              v-bind="field(['strategy', 'risk_matrix', index, 'manual_up_to'])"
              kind="money"
              unit="₽"
              label="Вручную до"
            />
          </div>
        </div>
      </div>
    </section>

    <section v-if="hasAt(body, ['limits'])">
      <h3 class="mb-3 text-sm font-semibold text-ink">Лимиты</h3>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DocField v-if="hasAt(body, ['limits', 'payment_share'])" v-bind="field(['limits', 'payment_share'])" kind="percent" unit="%" label="Платёж от свободного потока" />
        <DocField v-if="hasAt(body, ['limits', 'turnover_multiplier'])" v-bind="field(['limits', 'turnover_multiplier'])" kind="percent" unit="%" label="Не больше доли оборотов за год" />
        <DocField v-if="hasAt(body, ['limits', 'group_exposure_max'])" v-bind="field(['limits', 'group_exposure_max'])" kind="money" unit="₽" label="Потолок на группу заёмщика" />
        <DocField v-if="hasAt(body, ['limits', 'amount_step'])" v-bind="field(['limits', 'amount_step'])" kind="money" unit="₽" label="Шаг суммы" />
      </div>
      <div v-if="hasAt(body, ['limits', 'revenue_multiplier'])" class="mt-4 overflow-x-auto">
        <table class="text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="px-2 py-1.5 text-left font-medium">Грейд</th>
              <th v-for="grade in scale" :key="grade" scope="col" class="px-1 py-1.5 font-medium">{{ grade }}</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t border-line">
              <th scope="row" class="px-2 py-1.5 text-left font-normal whitespace-nowrap text-ink">Доля годовой выручки</th>
              <td v-for="grade in scale" :key="grade" class="w-20 px-1 py-1.5">
                <DocField v-if="hasAt(body, ['limits', 'revenue_multiplier', grade])" v-bind="field(['limits', 'revenue_multiplier', grade])" kind="decimal" hide-label :label="`${grade}: доля выручки`" />
              </td>
            </tr>
            <tr v-if="hasAt(body, ['limits', 'grade_max_amount'])" class="border-t border-line">
              <th scope="row" class="px-2 py-1.5 text-left font-normal whitespace-nowrap text-ink">Сумма на грейд, ₽</th>
              <td v-for="grade in scale" :key="grade" class="w-28 px-1 py-1.5">
                <DocField v-if="hasAt(body, ['limits', 'grade_max_amount', grade])" v-bind="field(['limits', 'grade_max_amount', grade])" kind="money" hide-label :label="`${grade}: сумма`" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="hasAt(body, ['pricing', 'components'])">
      <h3 class="text-sm font-semibold text-ink">Ставка</h3>
      <p class="mb-3 text-xs text-ink-secondary">Ключевая + спред + PD × LGD + капитал + маржа, в коридоре ставки продукта</p>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DocField v-if="hasAt(body, ['key_rate_reference'])" v-bind="field(['key_rate_reference'])" kind="decimal" unit="%" label="Ключевая, под которую каталог" />
        <template v-for="item in PRICING" :key="item.key">
          <DocField
            v-if="hasAt(body, ['pricing', 'components', item.key])"
            v-bind="field(['pricing', 'components', item.key])"
            :kind="item.kind"
            :unit="item.unit"
            :label="item.label"
          />
        </template>
      </div>
    </section>

    <section v-if="hasAt(body, ['strategy', 'soft_triggers']) || hasAt(body, ['routing', 'data_quality'])">
      <h3 class="mb-3 text-sm font-semibold text-ink">Ручная проверка</h3>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DocField
          v-if="hasAt(body, ['strategy', 'soft_triggers', 'head_change_months'])"
          v-bind="field(['strategy', 'soft_triggers', 'head_change_months'])"
          kind="int"
          unit="мес."
          label="Смена руководителя моложе"
        />
        <DocField
          v-if="hasAt(body, ['strategy', 'soft_triggers', 'turnover_spike', 'ratio'])"
          v-bind="field(['strategy', 'soft_triggers', 'turnover_spike', 'ratio'])"
          kind="decimal"
          unit="×"
          label="Разгон оборотов во столько раз"
        />
        <DocField
          v-if="hasAt(body, ['strategy', 'soft_triggers', 'turnover_spike', 'recent_months'])"
          v-bind="field(['strategy', 'soft_triggers', 'turnover_spike', 'recent_months'])"
          kind="int"
          unit="мес."
          label="…за последние"
        />
      </div>
      <div class="mt-3 grid gap-2.5 sm:grid-cols-2">
        <DocField
          v-if="hasAt(body, ['strategy', 'soft_triggers', 'tax_arrears'])"
          v-bind="field(['strategy', 'soft_triggers', 'tax_arrears'])"
          kind="bool"
          label="Недоимка ниже стоп-фактора — на проверку"
        />
        <DocField
          v-if="hasAt(body, ['routing', 'data_quality'])"
          v-bind="field(['routing', 'data_quality'])"
          kind="bool"
          label="Неполные данные скоринга — спорная, решает человек"
        />
      </div>
    </section>

    <ReasonTextsField :body="body" :catalog="catalog" :errors="errors" :readonly="readonly" />
  </div>
</template>
