<script setup lang="ts">
import { CircleCheck, CircleX } from 'lucide-vue-next'
import { computed } from 'vue'

import { GUARANTEE_LABEL } from '@/entities/underwriting'
import type { StartupProjectDto } from '@/shared/api'
import { formatDate, formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { BaseBadge, PanelCard } from '@/shared/ui'

/**
 * Проект стартапа (UnderwriterCard.startup): проектная оценка банка до заявки с цифрами модели, которых
 * клиент не видит, и бизнес-план с финмоделью. Форма проектной оценки открывается с startup.form.
 */
const props = defineProps<{ project: StartupProjectDto }>()

const money = (value: string | number | null | undefined) => (value === null || value === undefined ? '—' : formatMoney(Number(value)))
const share = (value: string) => formatPercent(Number(value) * 100)

const assessment = computed(() => props.project.assessment)
const figures = computed(() => assessment.value.figures)
const model = computed(() => props.project.business_plan?.financial_model ?? null)

/** Выручка и расходы по годам финмодели: 24 месяца — два года */
const years = computed(() => {
  const months = model.value?.months ?? []
  return [0, 1]
    .map((year) => months.slice(year * 12, year * 12 + 12))
    .filter((chunk) => chunk.length)
    .map((chunk, index) => ({
      title: `${index + 1}-й год`,
      revenue: chunk.reduce((sum, month) => sum + Number(month.revenue), 0),
      expenses: chunk.reduce((sum, month) => sum + Number(month.expenses), 0),
    }))
})
</script>

<template>
  <PanelCard title="Проект стартапа" :description="`Проектная оценка ${formatDate(assessment.checked_at)} · ${assessment.version}`">
    <div class="flex flex-wrap items-center gap-2">
      <BaseBadge :tone="assessment.status === 'passed' ? 'success' : 'brand'">
        {{ assessment.status === 'passed' ? 'Оценка пройдена' : 'Оценка не пройдена' }}
      </BaseBadge>
      <span class="text-xs text-ink-secondary">
        {{ assessment.valid ? `действует до ${formatDate(assessment.valid_until)}` : 'срок оценки истёк' }}
      </span>
    </div>
    <p v-if="assessment.status === 'passed' && assessment.max_amount" class="mt-2 text-sm text-ink">
      Предодобрено до <b>{{ money(assessment.max_amount) }}</b>
    </p>
    <p v-if="!project.valid_at_submission" class="mt-2 rounded-lg bg-warning-soft p-2.5 text-sm text-ink">
      На дату подачи заявки оценка не действовала
    </p>
    <p v-if="project.plan_changed" class="mt-2 rounded-lg bg-warning-soft p-2.5 text-sm text-ink">
      Бизнес-план уточнили после оценки — цифры ниже по прежней редакции
    </p>

    <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
      <div class="rounded-lg bg-surface-soft p-2">
        <dt class="text-xs text-ink-secondary">Запрошено</dt>
        <dd class="font-semibold">{{ money(figures.requested_amount) }}</dd>
        <dd class="text-xs text-ink-secondary">{{ formatTerm(figures.term_months) }} под {{ formatPercent(Number(figures.rate)) }}</dd>
      </div>
      <div class="rounded-lg bg-surface-soft p-2">
        <dt class="text-xs text-ink-secondary">Проект выдерживает</dt>
        <dd class="font-semibold">{{ money(figures.capacity) }}</dd>
      </div>
      <div class="rounded-lg bg-surface-soft p-2">
        <dt class="text-xs text-ink-secondary">DSCR</dt>
        <dd class="font-semibold tabular-nums">{{ figures.dscr ?? '—' }}</dd>
        <dd class="text-xs text-ink-secondary">поток {{ money(figures.cash_flow) }} / платежи {{ money(figures.debt_service) }} за 24 мес.</dd>
      </div>
      <div class="rounded-lg bg-surface-soft p-2">
        <dt class="text-xs text-ink-secondary">Свои средства · покрытие</dt>
        <dd class="font-semibold tabular-nums">{{ share(figures.own_share) }} · {{ share(figures.coverage) }}</dd>
      </div>
    </dl>

    <ul class="mt-3 space-y-1.5 text-sm">
      <li v-for="reason in assessment.reasons" :key="reason.code" class="flex items-start gap-2">
        <CircleCheck v-if="reason.passed" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <CircleX v-else class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
        {{ reason.message }}
      </li>
    </ul>

    <div v-if="project.business_plan && model" class="mt-4 border-t border-line pt-3 text-sm">
      <p class="font-semibold text-ink">Бизнес-план · редакция {{ project.business_plan.revision }}</p>
      <p class="mt-1 text-ink">{{ project.business_plan.summary }}</p>
      <ul class="mt-2 space-y-0.5 text-ink-secondary">
        <li>Свои средства: {{ money(model.own_funds) }}</li>
        <li>Кредит в плане: {{ money(model.loan_amount) }} на {{ formatTerm(model.loan_term_months) }}</li>
        <li>
          Гарантия: {{ GUARANTEE_LABEL[model.guarantee] ?? model.guarantee
          }}<template v-if="model.guarantee !== 'none'">, {{ share(model.guarantee_share) }} кредита</template>
        </li>
        <li v-if="Number(model.collateral_value) > 0 || model.collateral_description">
          Обеспечение: {{ model.collateral_description ?? '—' }}<template v-if="Number(model.collateral_value) > 0">, {{ money(model.collateral_value) }}</template>
        </li>
        <li v-for="year in years" :key="year.title">
          {{ year.title }}: выручка {{ money(year.revenue) }}, расходы {{ money(year.expenses) }}
        </li>
      </ul>
    </div>
  </PanelCard>
</template>
