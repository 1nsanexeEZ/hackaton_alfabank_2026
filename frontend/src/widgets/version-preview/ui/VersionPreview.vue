<script setup lang="ts">
import { ArrowRight, Play } from 'lucide-vue-next'
import { computed, ref, shallowRef } from 'vue'

import type { VersionKind } from '@/entities/scoring-version'
import { gradeTone, OUTCOME_LABEL, REASON_LABEL, SEGMENT_LABEL, label } from '@/entities/underwriting'
import {
  backofficeApi,
  type ModelEstimateDto,
  type ModelPreviewDto,
  type PolicyPreviewDto,
  type PolicyVerdictDto,
} from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime, formatProbability } from '@/shared/lib'
import { BaseBadge, BaseButton, SegmentedControl } from '@/shared/ui'

/**
 * Примерка (POST …/preview): версия-кандидат пересчитывает последние заявки и ничего не пишет.
 * Модель — по снимку входа последнего результата PD-модели; политика — заново на текущих данных заявки,
 * поэтому «стало» у политики может отличаться и при той же версии.
 */
const props = defineProps<{ kind: VersionKind; version: string }>()

const LIMITS = ['20', '50', '100', '200'].map((value) => ({ value, label: value }))
const limit = ref('50')
const pending = ref(false)
const error = ref<string | null>(null)
const model = shallowRef<ModelPreviewDto | null>(null)
const policy = shallowRef<PolicyPreviewDto | null>(null)
/** Номера заявок — из списка заявок сотрудника: в ответе примерки только id */
const numbers = shallowRef(new Map<string, string>())
const onlyChanged = ref(true)

async function run() {
  pending.value = true
  error.value = null
  try {
    const [result, applications] = await Promise.all([
      props.kind === 'model'
        ? backofficeApi.scoringModels.preview(props.version, Number(limit.value))
        : backofficeApi.decisionPolicies.preview(props.version, Number(limit.value)),
      numbers.value.size ? Promise.resolve(null) : backofficeApi.applications({ limit: 100 }).catch(() => null),
    ])
    if (applications) numbers.value = new Map(applications.items.map((item) => [item.id, item.number]))
    if (props.kind === 'model') model.value = result as ModelPreviewDto
    else policy.value = result as PolicyPreviewDto
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}

const number = (id: string) => numbers.value.get(id) ?? id.slice(0, 8)

const sameEstimate = (before: ModelEstimateDto, after: ModelEstimateDto) => before.grade === after.grade && before.score === after.score
const sameVerdict = (before: PolicyVerdictDto, after: PolicyVerdictDto) =>
  before.outcome === after.outcome && before.reason_codes.join() === after.reason_codes.join()

const modelItems = computed(() =>
  (model.value?.items ?? []).filter((item) => !onlyChanged.value || !sameEstimate(item.before, item.after)),
)
const policyItems = computed(() =>
  (policy.value?.items ?? []).filter((item) => !onlyChanged.value || !sameVerdict(item.before, item.after)),
)

const pd = (value: string | null) => (value === null ? '—' : formatProbability(Number(value)))
const outcome = (code: string) => OUTCOME_LABEL[code] ?? { label: code, tone: 'neutral' as const }
const reasons = (codes: string[]) => (codes.length ? codes.map((code) => label(REASON_LABEL, code)).join('; ') : 'без причин')
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-end gap-4">
      <div>
        <p class="mb-1 text-xs font-medium text-ink-secondary">Сколько последних заявок</p>
        <SegmentedControl v-model="limit" :options="LIMITS" label="Сколько последних заявок пересчитать" small />
      </div>
      <BaseButton :loading="pending" @click="run">
        <Play class="size-4" aria-hidden="true" />
        Примерить
      </BaseButton>
      <p class="max-w-xl text-xs text-ink-secondary">
        <template v-if="kind === 'model'">Пересчёт по снимку входа последнего результата PD-модели каждой заявки. Ничего не сохраняется.</template>
        <template v-else>Заявки с автоматическим решением решаются заново на текущих данных и ключевой ставке. Ничего не сохраняется.</template>
      </p>
    </div>

    <p v-if="error" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>

    <template v-if="kind === 'model' && model">
      <dl class="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div v-for="item in [
          { label: 'Пересчитано', value: model.total },
          { label: 'Грейд тот же', value: model.same },
          { label: 'Лучше', value: model.better },
          { label: 'Хуже', value: model.worse },
          { label: 'Пропущено', value: model.skipped },
        ]" :key="item.label" class="rounded-xl bg-surface-soft p-3">
          <dt class="text-xs text-ink-secondary">{{ item.label }}</dt>
          <dd class="text-xl font-bold text-ink tabular-nums">{{ item.value }}</dd>
        </div>
      </dl>
      <div v-if="model.transitions.length">
        <p class="mb-2 text-xs font-medium text-ink-secondary">Переходы грейдов</p>
        <ul class="flex flex-wrap gap-2">
          <li v-for="shift in model.transitions" :key="`${shift.from}-${shift.to}`" class="flex items-center gap-1.5 rounded-lg bg-surface-soft px-2.5 py-1.5 text-sm">
            <BaseBadge :tone="gradeTone(shift.from)">{{ shift.from }}</BaseBadge>
            <ArrowRight class="size-3.5 text-ink-muted" aria-hidden="true" />
            <BaseBadge :tone="gradeTone(shift.to)">{{ shift.to }}</BaseBadge>
            <span class="text-ink tabular-nums">× {{ shift.count }}</span>
          </li>
        </ul>
      </div>
    </template>

    <template v-if="kind === 'policy' && policy">
      <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div v-for="item in [
          { label: 'Решено заново', value: policy.total },
          { label: 'Изменилось', value: policy.changed },
          { label: 'Другой исход', value: policy.outcome_changed },
          { label: 'Пропущено', value: policy.skipped },
        ]" :key="item.label" class="rounded-xl bg-surface-soft p-3">
          <dt class="text-xs text-ink-secondary">{{ item.label }}</dt>
          <dd class="text-xl font-bold text-ink tabular-nums">{{ item.value }}</dd>
        </div>
      </dl>
      <div v-if="policy.transitions.length">
        <p class="mb-2 text-xs font-medium text-ink-secondary">Переходы исходов</p>
        <ul class="flex flex-wrap gap-2">
          <li v-for="shift in policy.transitions" :key="`${shift.from}-${shift.to}`" class="flex items-center gap-1.5 rounded-lg bg-surface-soft px-2.5 py-1.5 text-sm">
            <BaseBadge :tone="outcome(shift.from).tone">{{ outcome(shift.from).label }}</BaseBadge>
            <ArrowRight class="size-3.5 text-ink-muted" aria-hidden="true" />
            <BaseBadge :tone="outcome(shift.to).tone">{{ outcome(shift.to).label }}</BaseBadge>
            <span class="text-ink tabular-nums">× {{ shift.count }}</span>
          </li>
        </ul>
      </div>
    </template>

    <template v-if="model || policy">
      <label class="flex items-center gap-2 text-sm text-ink">
        <input v-model="onlyChanged" type="checkbox" class="size-4 accent-brand" />
        Только заявки, где что-то изменилось
      </label>

      <div v-if="kind === 'model' && model" class="overflow-x-auto rounded-xl ring-1 ring-line">
        <table class="w-full min-w-[40rem] text-sm">
          <thead class="bg-surface-soft text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="px-3 py-2 text-left font-medium">Заявка</th>
              <th scope="col" class="px-3 py-2 text-left font-medium">Сегмент</th>
              <th scope="col" class="px-3 py-2 text-left font-medium">Было</th>
              <th scope="col" class="px-3 py-2 text-left font-medium">Стало</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in modelItems" :key="item.result_id" class="border-t border-line">
              <td class="px-3 py-2">
                <RouterLink :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }" class="font-medium text-ink hover:text-brand">
                  {{ number(item.application_id) }}
                </RouterLink>
                <p class="text-xs text-ink-muted">{{ formatDateTime(item.computed_at) }}</p>
              </td>
              <td class="px-3 py-2 text-ink-secondary">{{ item.after.segment ? label(SEGMENT_LABEL, item.after.segment) : '—' }}</td>
              <td v-for="(side, index) in [item.before, item.after]" :key="index" class="px-3 py-2">
                <span class="flex items-center gap-2">
                  <BaseBadge :tone="gradeTone(side.grade)">{{ side.grade }}</BaseBadge>
                  <span class="text-ink tabular-nums">{{ side.score }}</span>
                  <span class="text-xs text-ink-secondary tabular-nums">PD {{ pd(side.pd_12m) }}</span>
                </span>
                <span class="text-[11px] text-ink-muted">{{ side.model_version }}</span>
              </td>
            </tr>
            <tr v-if="!modelItems.length">
              <td colspan="4" class="px-3 py-6 text-center text-ink-secondary">Изменений нет</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="kind === 'policy' && policy" class="overflow-x-auto rounded-xl ring-1 ring-line">
        <table class="w-full min-w-[40rem] text-sm">
          <thead class="bg-surface-soft text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="px-3 py-2 text-left font-medium">Заявка</th>
              <th scope="col" class="px-3 py-2 text-left font-medium">Было</th>
              <th scope="col" class="px-3 py-2 text-left font-medium">Стало</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in policyItems" :key="item.result_id" class="border-t border-line align-top">
              <td class="px-3 py-2">
                <RouterLink :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }" class="font-medium text-ink hover:text-brand">
                  {{ number(item.application_id) }}
                </RouterLink>
                <p class="text-xs text-ink-muted">{{ formatDateTime(item.decided_at) }}</p>
              </td>
              <td v-for="(side, index) in [item.before, item.after]" :key="index" class="px-3 py-2">
                <BaseBadge :tone="outcome(side.outcome).tone">{{ outcome(side.outcome).label }}</BaseBadge>
                <p class="mt-1 text-xs text-ink-secondary">{{ reasons(side.reason_codes) }}</p>
                <p class="text-[11px] text-ink-muted">{{ side.policy_version }}</p>
              </td>
            </tr>
            <tr v-if="!policyItems.length">
              <td colspan="3" class="px-3 py-6 text-center text-ink-secondary">Изменений нет</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
