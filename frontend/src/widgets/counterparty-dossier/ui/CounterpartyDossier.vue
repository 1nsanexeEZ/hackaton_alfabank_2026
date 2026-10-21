<script setup lang="ts">
import { CircleAlert, CircleCheck, CircleX } from 'lucide-vue-next'
import { computed } from 'vue'

import type { Dossier, GirBoPeriod } from '@/shared/api'
import { formatDate, formatMoney, formatMoneyShort } from '@/shared/lib'
import { PanelCard } from '@/shared/ui'

import { summarizeChecks, type CheckLevel } from '../model/checks'

/** Досье контрагента из внешних источников: ЕГРЮЛ/ЕГРИП, ФНС, ГИР БО, Контур */
const props = defineProps<{ dossier: Dossier }>()

const checks = computed(() => summarizeChecks(props.dossier))

const LEVEL_META: Record<CheckLevel, { icon: typeof CircleCheck; class: string; label: string }> = {
  ok: { icon: CircleCheck, class: 'text-success', label: 'В порядке' },
  warn: { icon: CircleAlert, class: 'text-warning', label: 'Есть замечания' },
  fail: { icon: CircleX, class: 'text-brand', label: 'Критично' },
}

const registry = computed(() => {
  const dossier = props.dossier
  if (dossier.kind === 'company') {
    const record = dossier.egrul
    return {
      title: 'ЕГРЮЛ',
      rows: [
        ['Полное название', record.name_full],
        ['ОГРН', record.ogrn],
        ['ИНН / КПП', `${record.inn} / ${record.kpp}`],
        ['Зарегистрировано', `${formatDate(record.registration_date)}, ${record.registration_authority}`],
        ['Адрес', record.address.full + (record.address.unreliable ? ' (недостоверно)' : '')],
        ['Уставный капитал', formatMoney(record.authorized_capital_rub)],
        [record.director.position, record.director.name],
        ['Учредители', record.founders.map((founder) => `${founder.name} — ${founder.share_percent}%`).join('\n')],
      ],
      okved: record.okved,
    }
  }
  const record = dossier.egrip
  return {
    title: 'ЕГРИП',
    rows: [
      ['ФИО', record.fio],
      ['ОГРНИП', record.ogrnip],
      ['ИНН', record.inn],
      ['Зарегистрирован', `${formatDate(record.registration_date)}, ${record.registration_authority}`],
      ['Гражданство', record.citizenship],
    ],
    okved: record.okved,
  }
})

const periods = computed(() => [...props.dossier.gir_bo.periods].sort((a, b) => a.year - b.year))

type Row = { label: string; value: (period: GirBoPeriod) => number; strong?: boolean }
const REPORT_ROWS: Row[] = [
  { label: 'Выручка', value: (period) => period.income['2110_revenue'], strong: true },
  { label: 'Прибыль от продаж', value: (period) => period.income['2200_sales_profit'] },
  { label: 'Чистая прибыль', value: (period) => period.income['2400_net_profit'], strong: true },
  { label: 'Активы', value: (period) => period.balance['1600_total_assets'] },
  { label: 'Собственный капитал', value: (period) => period.balance['1300_equity'] },
  { label: 'Долгосрочные обязательства', value: (period) => period.balance['1400_long_term_liabilities'] },
  { label: 'Краткосрочные обязательства', value: (period) => period.balance['1500_short_term_liabilities'] },
  { label: 'Денежные средства', value: (period) => period.balance['1250_cash'] },
]

/** Значения ГИР БО в тысячах рублей */
const thousands = (value: number) => formatMoneyShort(value * 1000)

function change(row: Row): { text: string; class: string } | null {
  const [prev, last] = [periods.value.at(-2), periods.value.at(-1)]
  if (!prev || !last || row.value(prev) === 0) return null
  // Делим на модуль, чтобы рост из убытка в прибыль считался ростом
  const percent = Math.round(((row.value(last) - row.value(prev)) / Math.abs(row.value(prev))) * 100)
  return { text: `${percent > 0 ? '+' : ''}${percent}%`, class: percent >= 0 ? 'text-success' : 'text-brand' }
}

const fnsRows = computed(() => {
  const { fns } = props.dossier
  return [
    ['Налоговый режим', fns.tax_regime],
    ['Сотрудников', String(fns.average_headcount)],
    ['Реестр МСП', fns.msp_register.included ? (fns.msp_register.category ?? 'да') : 'не входит'],
    ['Налоги уплачены', fns.taxes_paid.map((item) => `${item.year}: ${formatMoneyShort(item.paid_rub)}`).join(' · ')],
    ['Недоимка', fns.tax_arrears_rub ? formatMoney(fns.tax_arrears_rub) : 'нет'],
    ['Массовый адрес', fns.mass_registration_address ? 'да' : 'нет'],
    ['Дисквалифицированные лица', fns.disqualified_persons ? 'есть' : 'нет'],
  ]
})

const RELIABILITY = {
  green: { label: 'Высокая надёжность', class: 'bg-success-soft text-success' },
  yellow: { label: 'Есть риски', class: 'bg-warning-soft text-warning' },
  red: { label: 'Высокий риск', class: 'bg-brand-soft text-brand' },
} as const

const konturRows = computed(() => {
  const { kontur } = props.dossier
  return [
    [
      'Арбитраж, ответчик',
      kontur.arbitration.as_defendant
        ? `${kontur.arbitration.as_defendant} дел на ${formatMoneyShort(kontur.arbitration.defendant_sum_rub)}`
        : 'нет',
    ],
    ['Арбитраж, истец', kontur.arbitration.as_plaintiff ? `${kontur.arbitration.as_plaintiff} дел` : 'нет'],
    [
      'Исполнительные производства',
      kontur.enforcement_proceedings.active
        ? `${kontur.enforcement_proceedings.active} на ${formatMoneyShort(kontur.enforcement_proceedings.sum_rub)}`
        : 'нет',
    ],
    ['Госконтракты', kontur.gov_contracts.count ? `${kontur.gov_contracts.count} на ${formatMoneyShort(kontur.gov_contracts.sum_rub)}` : 'нет'],
    ['Действующие залоги', String(kontur.active_pledges)],
    ['Связанные компании', String(kontur.affiliated_companies)],
  ]
})
</script>

<template>
  <!-- Сетки считаются от ширины досье: оно стоит и на всю страницу, и в узкой колонке карточки заявки -->
  <div class="@container space-y-6">
    <ul class="grid gap-3 @lg:grid-cols-2 @4xl:grid-cols-4">
      <li v-for="check in checks" :key="check.source" class="flex items-start gap-3 rounded-2xl bg-white p-4 ring-1 ring-line">
        <component :is="LEVEL_META[check.level].icon" class="mt-0.5 size-5 shrink-0" :class="LEVEL_META[check.level].class" aria-hidden="true" />
        <div class="min-w-0">
          <p class="text-sm font-semibold text-ink">
            {{ check.source }}
            <span class="sr-only">: {{ LEVEL_META[check.level].label }}</span>
          </p>
          <p class="mt-0.5 text-sm text-ink-secondary first-letter:uppercase">{{ check.summary }}</p>
        </div>
      </li>
    </ul>

    <div class="grid gap-6 @4xl:grid-cols-2">
      <PanelCard :title="registry.title" description="Регистрационные данные">
        <dl class="divide-y divide-line text-sm">
          <div v-for="[label, value] in registry.rows" :key="label" class="grid gap-1 py-2.5 first:pt-0 @lg:grid-cols-[11rem_1fr] @lg:gap-4">
            <dt class="text-ink-secondary">{{ label }}</dt>
            <dd class="whitespace-pre-line text-ink">{{ value }}</dd>
          </div>
          <div class="grid gap-1 py-2.5 pb-0 @lg:grid-cols-[11rem_1fr] @lg:gap-4">
            <dt class="text-ink-secondary">ОКВЭД</dt>
            <dd class="text-ink">
              <p><b class="font-semibold tabular-nums">{{ registry.okved.main.code }}</b> {{ registry.okved.main.name }}</p>
              <p v-for="item in registry.okved.additional" :key="item.code" class="mt-1 text-ink-secondary">
                <span class="tabular-nums">{{ item.code }}</span> {{ item.name }}
              </p>
            </dd>
          </div>
        </dl>
      </PanelCard>

      <div class="space-y-6">
        <PanelCard title="ФНС «Прозрачный бизнес»" :description="`Проверено ${formatDate(dossier.fns.checked_at)}`">
          <dl class="divide-y divide-line text-sm">
            <div v-for="[label, value] in fnsRows" :key="label" class="flex justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
              <dt class="text-ink-secondary">{{ label }}</dt>
              <dd class="text-right text-ink">{{ value }}</dd>
            </div>
          </dl>
          <ul v-if="dossier.fns.account_blocks.length" class="mt-4 space-y-2">
            <li v-for="block in dossier.fns.account_blocks" :key="block.decision_number" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-ink">
              <b class="font-semibold text-brand">Операции по счетам приостановлены</b>
              — решение № {{ block.decision_number }} от {{ formatDate(block.date) }}, {{ block.reason.toLowerCase() }}
            </li>
          </ul>
        </PanelCard>

        <PanelCard title="Контур" description="Надёжность, суды, взыскания">
          <template #actions>
            <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="RELIABILITY[dossier.kontur.reliability].class">
              {{ RELIABILITY[dossier.kontur.reliability].label }}
            </span>
          </template>
          <ul v-if="dossier.kontur.reliability_notes.length" class="mb-4 flex flex-wrap gap-2">
            <li v-for="note in dossier.kontur.reliability_notes" :key="note" class="rounded-full bg-surface px-3 py-1 text-xs text-ink">
              {{ note }}
            </li>
          </ul>
          <dl class="divide-y divide-line text-sm">
            <div v-for="[label, value] in konturRows" :key="label" class="flex justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
              <dt class="text-ink-secondary">{{ label }}</dt>
              <dd class="text-right text-ink">{{ value }}</dd>
            </div>
          </dl>
          <p v-for="message in dossier.kontur.bankruptcy_messages" :key="message.case" class="mt-4 rounded-xl bg-brand-soft px-4 py-3 text-sm text-ink">
            <b class="font-semibold text-brand">{{ message.type }}</b> — дело {{ message.case }} от {{ formatDate(message.date) }}
          </p>
        </PanelCard>
      </div>
    </div>

    <PanelCard title="ГИР БО" description="Бухгалтерская отчётность" flush>
      <div v-if="periods.length" class="overflow-x-auto">
        <table class="w-full min-w-[32rem] text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr class="border-b border-line">
              <th scope="col" class="py-3 pr-4 pl-5 text-left font-medium">Показатель</th>
              <th v-for="period in periods" :key="period.year" scope="col" class="px-4 py-3 text-right font-medium">{{ period.year }}</th>
              <th scope="col" class="py-3 pr-5 pl-4 text-right font-medium">Изменение</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in REPORT_ROWS" :key="row.label" class="border-b border-line last:border-0">
              <th scope="row" class="py-2.5 pr-4 pl-5 text-left" :class="row.strong ? 'font-semibold text-ink' : 'font-normal text-ink-secondary'">
                {{ row.label }}
              </th>
              <td
                v-for="period in periods"
                :key="period.year"
                class="px-4 py-2.5 text-right tabular-nums"
                :class="[row.strong ? 'font-semibold' : '', row.value(period) < 0 ? 'text-brand' : 'text-ink']"
              >
                {{ thousands(row.value(period)) }}
              </td>
              <td class="py-2.5 pr-5 pl-4 text-right font-medium tabular-nums" :class="change(row)?.class">
                {{ change(row)?.text ?? '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="px-5 pb-5 text-sm text-ink-secondary">
        {{ dossier.gir_bo.reason ?? 'Отчётности в ГИР БО нет: компания зарегистрирована недавно или не сдавала отчёт' }}
      </p>
    </PanelCard>
  </div>
</template>
