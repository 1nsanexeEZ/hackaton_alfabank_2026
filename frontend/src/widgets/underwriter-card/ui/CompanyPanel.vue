<script setup lang="ts">
import { computed } from 'vue'

import { REGISTRY_STATUS_LABEL } from '@/entities/underwriting'
import type { UnderwriterCardDto } from '@/shared/api'
import { formatDate, formatMoney, formatTerm } from '@/shared/lib'
import { BaseBadge, PanelCard, type BadgeTone } from '@/shared/ui'

import { amount, change, millions, share } from '../model/figures'
import FactRow from './FactRow.vue'
import StatTile from './StatTile.vue'

/**
 * Компания на момент подачи: реквизиты одной строкой, статус и сверка бейджами, факты плитками,
 * отчётность со слов клиента — выручка по периодам столбиками и цифры последнего периода.
 */
const props = defineProps<{ snapshot: NonNullable<UnderwriterCardDto['application']['org_snapshot']> }>()

const TAX_REGIME: Record<string, string> = { osn: 'ОСН', usn: 'УСН', ausn: 'АУСН', eshn: 'ЕСХН', patent: 'Патент' }
const REPORT_SOURCE: Record<string, string> = { declared: 'со слов клиента', fns: 'ФНС', bank_statement: 'по выпискам' }

const REGISTRY_TONE: Record<string, BadgeTone> = {
  active: 'success',
  liquidating: 'warning',
  reorganizing: 'warning',
  liquidated: 'brand',
  bankrupt: 'brand',
  excluded: 'brand',
}
const VERIFICATION: Record<string, { tone: BadgeTone; label: string }> = {
  verified: { tone: 'success', label: 'Сверена с ЕГРЮЛ' },
  mismatch: { tone: 'warning', label: 'Расхождения с ЕГРЮЛ' },
  unverified: { tone: 'neutral', label: 'С ЕГРЮЛ не сверяли' },
}

const initial = computed(() => props.snapshot.name.replace(/^(ООО|АО|ПАО|ИП)\s*/u, '').replace(/[«"]/gu, '').charAt(0) || '·')

/** Периоды отчётности по порядку, последние четыре: выручка столбиком, изменение к прошлому */
const reports = computed(() => {
  const sorted = [...props.snapshot.financial_reports].sort(
    (a, b) => a.period_year - b.period_year || (a.period_quarter ?? 5) - (b.period_quarter ?? 5),
  )
  const recent = sorted.slice(-4)
  const max = Math.max(1, ...recent.map((report) => Number(report.revenue)))
  return recent.map((report, index) => {
    const revenue = Number(report.revenue)
    const previous = recent[index - 1]
    return {
      key: `${report.period_year}-${report.period_quarter}-${report.source}`,
      period: report.period_quarter ? `${report.period_quarter} кв. ${report.period_year}` : String(report.period_year),
      source: REPORT_SOURCE[report.source] ?? report.source,
      revenue,
      height: Math.max(4, share(revenue, max)),
      delta: previous ? change(revenue, Number(previous.revenue)) : null,
      last: index === recent.length - 1,
    }
  })
})

/** Цифры последнего периода, какие клиент указал */
const latest = computed(() => {
  const report = [...props.snapshot.financial_reports].sort(
    (a, b) => b.period_year - a.period_year || (b.period_quarter ?? 5) - (a.period_quarter ?? 5),
  )[0]
  if (!report) return null
  const rows = [
    { label: 'Расходы', value: amount(report.expenses) },
    { label: 'Чистая прибыль', value: amount(report.net_profit) },
    { label: 'Обязательства', value: amount(report.total_liabilities) },
    { label: 'Платежи по долгам', value: amount(report.monthly_debt_payments), suffix: ' / мес.' },
  ].filter((row) => row.value !== null)
  return { period: report.period_quarter ? `${report.period_quarter} кв. ${report.period_year}` : `${report.period_year} год`, rows }
})
</script>

<template>
  <PanelCard title="Компания" description="Снимок на момент подачи">
    <div class="flex flex-wrap items-center gap-3.5">
      <span class="flex size-12 shrink-0 items-center justify-center rounded-xl bg-night text-xl font-extrabold text-white" aria-hidden="true">
        {{ initial }}
      </span>
      <div class="min-w-0 flex-[1_1_16rem]">
        <p class="text-[1.0625rem] font-bold text-ink">{{ snapshot.name }}</p>
        <p class="mt-0.5 text-sm text-ink-secondary tabular-nums">
          ИНН {{ snapshot.inn }} · ОГРН {{ snapshot.ogrn }}<template v-if="snapshot.kpp"> · КПП {{ snapshot.kpp }}</template>
        </p>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <BaseBadge :tone="REGISTRY_TONE[snapshot.registry_status] ?? 'neutral'">
          {{ REGISTRY_STATUS_LABEL[snapshot.registry_status] ?? snapshot.registry_status }}
        </BaseBadge>
        <BaseBadge :tone="VERIFICATION[snapshot.verification_status]?.tone ?? 'neutral'">
          {{ VERIFICATION[snapshot.verification_status]?.label ?? snapshot.verification_status }}
        </BaseBadge>
      </div>
    </div>

    <div class="mt-4 grid grid-cols-2 gap-2.5 @xl:grid-cols-4">
      <StatTile label="Возраст бизнеса" :hint="`с ${formatDate(snapshot.registered_at)}`">{{ formatTerm(snapshot.business_age_months) }}</StatTile>
      <StatTile label="ОКВЭД" hint="основной">{{ snapshot.okved_main }}</StatTile>
      <StatTile label="Сотрудников" hint="по анкете">{{ snapshot.employees_count }}</StatTile>
      <StatTile label="Налоговый режим">{{ TAX_REGIME[snapshot.tax_regime] ?? snapshot.tax_regime }}</StatTile>
    </div>
    <dl class="mt-1.5">
      <FactRow label="Руководитель">{{ snapshot.head_name ?? '—' }}</FactRow>
    </dl>

    <div v-if="snapshot.verification_status === 'mismatch'" class="mt-3 rounded-xl bg-warning-soft p-3 text-sm text-ink">
      <p class="font-semibold">Расхождения с ЕГРЮЛ</p>
      <ul class="mt-1 space-y-0.5 text-ink-secondary">
        <li v-for="item in snapshot.discrepancies" :key="item.field">
          {{ item.field }}: в кабинете «{{ item.declared ?? '—' }}», в реестре «{{ item.registry ?? '—' }}»
        </li>
      </ul>
    </div>

    <template v-if="reports.length">
      <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Отчётность клиента</h3>
      <div class="mt-3 flex flex-wrap items-start gap-6">
        <figure class="m-0 min-w-0 flex-[1_1_14rem]">
          <div
            class="flex h-40 items-end gap-5 border-b border-line px-2"
            role="img"
            :aria-label="`Выручка: ${reports.map((report) => `${report.period} — ${millions(report.revenue)} млн ₽`).join(', ')}`"
          >
            <div v-for="report in reports" :key="report.key" class="flex h-full min-w-0 flex-1 flex-col items-center justify-end" :title="report.source">
              <span class="text-xs font-semibold text-ink tabular-nums">{{ millions(report.revenue) }} млн</span>
              <span v-if="report.delta" class="text-[11px] font-semibold" :class="report.delta.sign < 0 ? 'text-brand' : 'text-success'">
                {{ report.delta.text }}
              </span>
              <span
                class="mt-1 w-full max-w-16 rounded-t-lg"
                :class="report.last ? 'bg-night' : 'bg-surface-strong'"
                :style="{ height: `${report.height * 0.78}%` }"
              />
            </div>
          </div>
          <div class="flex gap-5 px-2 pt-1.5 text-center text-xs text-ink-secondary">
            <span v-for="report in reports" :key="report.key" class="min-w-0 flex-1 truncate">{{ report.period }}</span>
          </div>
          <figcaption class="mt-1 text-center text-xs text-ink-secondary">Выручка, ₽</figcaption>
        </figure>
        <div v-if="latest && latest.rows.length" class="min-w-0 flex-[1_1_15rem]">
          <p class="text-sm font-semibold text-ink">{{ latest.period }}</p>
          <dl class="mt-0.5">
            <FactRow v-for="row in latest.rows" :key="row.label" :label="row.label">
              <span class="tabular-nums">{{ formatMoney(row.value!) }}{{ row.suffix ?? '' }}</span>
            </FactRow>
          </dl>
        </div>
      </div>
    </template>
  </PanelCard>
</template>
