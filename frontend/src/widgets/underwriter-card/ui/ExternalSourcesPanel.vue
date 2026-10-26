<script setup lang="ts">
import { CircleCheck, CircleMinus, CircleX, Waves } from 'lucide-vue-next'
import { computed } from 'vue'

import { label, REGISTRY_STATUS_LABEL, RELIABILITY, SOURCE_LABEL, UNRELIABLE_LABEL, type AmlRiskGroup } from '@/entities/underwriting'
import type { EnrichmentDto, UnderwriterCardDto } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney } from '@/shared/lib'
import { BaseBadge, PanelCard } from '@/shared/ui'

import AmlCheckSection from './AmlCheckSection.vue'
import BankDataSection from './BankDataSection.vue'
import BureauCard from './BureauCard.vue'
import CashflowCard from './CashflowCard.vue'
import FactRow from './FactRow.vue'
import GirBoCard from './GirBoCard.vue'
import SourceCard from './SourceCard.vue'
import StatTile from './StatTile.vue'

/**
 * Что ответили внешние источники. Сверху — кто ответил, кто нет и кого не запрашивали; ниже подблоки
 * в одном виде: заголовок, итог бейджем, строки «показатель — значение», где нужно — плитки и графики.
 */
const props = defineProps<{
  enrichment: EnrichmentDto
  snapshot: UnderwriterCardDto['application']['org_snapshot']
  riskGroup: AmlRiskGroup | null
}>()

const money = (value: string | number) => formatMoney(Number(value))

const answered = computed(() => {
  const ok = props.enrichment.sources_ok.length
  return { ok, total: ok + props.enrichment.sources_failed.length }
})

const egrul = computed(() => {
  const value = props.enrichment.egrul
  if (!value) return null
  const status =
    value.status !== 'active' || value.unreliable?.length
      ? { tone: 'brand' as const, label: 'Есть замечания' }
      : value.mass_address
        ? { tone: 'warning' as const, label: 'Массовый адрес' }
        : { tone: 'success' as const, label: 'Без замечаний' }
  const head = [value.head_last_name, value.head_first_name, value.head_middle_name].filter(Boolean).join(' ')
  return { value, status, head }
})

/** ФНС рядом с анкетой: выручка за тот же год и численность — расхождение видно в строке */
const fns = computed(() => {
  const value = props.enrichment.fns
  if (!value) return null
  const blocked = Boolean(value.account_blocks?.length)
  const status =
    Number(value.tax_arrears) > 0 || value.disqualified_head || blocked
      ? { tone: 'brand' as const, label: 'Есть замечания' }
      : value.mass_head
        ? { tone: 'warning' as const, label: 'Массовый руководитель' }
        : { tone: 'success' as const, label: 'Без замечаний' }
  const declared = props.snapshot?.financial_reports.find(
    (report) => report.source === 'declared' && report.period_year === value.report_year && !report.period_quarter,
  )
  const revenueHint =
    declared && value.reported_revenue
      ? `заявлено ${money(declared.revenue)} · расхождение ${Math.round((Math.abs(Number(declared.revenue) - Number(value.reported_revenue)) / Number(declared.revenue)) * 100)}%`
      : null
  const flags = [
    { ok: !value.disqualified_head, text: value.disqualified_head ? 'Руководитель дисквалифицирован' : 'Дисквалификации нет' },
    ...(typeof value.mass_head === 'boolean' ? [{ ok: !value.mass_head, text: value.mass_head ? 'Массовый руководитель' : 'Не массовый руководитель' }] : []),
    { ok: value.in_msp_registry, neutral: !value.in_msp_registry, text: value.in_msp_registry ? 'В реестре МСП' : 'Нет в реестре МСП' },
    { ok: !blocked, text: blocked ? 'Счета приостановлены' : 'Счета не приостановлены' },
  ]
  return { value, status, revenueHint, flags, employees: props.snapshot?.employees_count ?? null }
})

const kontur = computed(() => props.enrichment.kontur ?? null)
/** Выписки нет: прогноз разрыва не строили — ни данных, ни ошибки источника */
const noStatement = computed(() => !props.enrichment.cashflow && !props.enrichment.sources_failed.some((item) => item.source === 'statement'))
</script>

<template>
  <PanelCard title="Внешние источники" :description="`Собрано ${formatDateTime(enrichment.collected_at)}`">
    <template #actions>
      <BaseBadge :tone="answered.ok === answered.total ? 'success' : 'warning'">Ответили {{ answered.ok }} из {{ answered.total }}</BaseBadge>
    </template>

    <ul class="flex flex-wrap gap-1.5">
      <li v-for="source in enrichment.sources_ok" :key="source" class="inline-flex items-center gap-1.5 rounded-full bg-surface-soft py-1 pr-2.5 pl-2 text-xs font-semibold text-ink">
        <CircleCheck class="size-3.5 text-success" aria-hidden="true" />{{ label(SOURCE_LABEL, source) }}
      </li>
      <li v-for="failed in enrichment.sources_failed" :key="failed.source" class="inline-flex items-center gap-1.5 rounded-full bg-brand-soft py-1 pr-2.5 pl-2 text-xs font-semibold text-brand" :title="failed.message">
        <CircleX class="size-3.5" aria-hidden="true" />{{ label(SOURCE_LABEL, failed.source) }}: не ответил
      </li>
      <li
        v-for="skipped in enrichment.sources_skipped ?? []"
        :key="`skip-${skipped.source}`"
        class="inline-flex items-center gap-1.5 rounded-full bg-surface py-1 pr-2.5 pl-2 text-xs font-semibold text-ink-secondary"
        :title="skipped.message"
      >
        <CircleMinus class="size-3.5" aria-hidden="true" />{{ label(SOURCE_LABEL, skipped.source) }}: не запрашивали
      </li>
    </ul>
    <ul v-if="enrichment.sources_skipped?.length" class="mt-2 space-y-0.5 text-xs text-ink-secondary">
      <li v-for="skipped in enrichment.sources_skipped" :key="`why-${skipped.source}`">{{ label(SOURCE_LABEL, skipped.source) }} — {{ skipped.message }}</li>
    </ul>

    <div class="mt-4 grid grid-cols-1 gap-3.5 @xl:grid-cols-2">
      <SourceCard v-if="egrul" title="ЕГРЮЛ / ЕГРИП" :status="egrul.status">
        <dl>
          <FactRow label="Статус" :tone="egrul.value.status === 'active' ? 'success' : 'brand'">
            {{ REGISTRY_STATUS_LABEL[egrul.value.status] ?? egrul.value.status }}
          </FactRow>
          <FactRow label="Регистрация">{{ formatDate(egrul.value.registered_at) }}</FactRow>
          <FactRow v-if="egrul.value.kpp" label="КПП"><span class="tabular-nums">{{ egrul.value.kpp }}</span></FactRow>
          <FactRow
            label="Руководитель"
            :hint="`${egrul.value.head_position}${egrul.value.head_since ? ` с ${formatDate(egrul.value.head_since)}` : ''}`"
          >
            {{ egrul.head }}
          </FactRow>
          <FactRow v-if="egrul.value.founders.length" label="Учредители">
            <span v-for="founder in egrul.value.founders" :key="founder.name" class="block">
              {{ founder.name }}{{ founder.inn ? `, ИНН ${founder.inn}` : '' }} — {{ Number(founder.share_percent) }}%
              <span class="mt-1 ml-auto block h-1.5 w-full max-w-40 overflow-hidden rounded-full bg-surface-strong" aria-hidden="true">
                <span class="block h-full rounded-full bg-night" :style="{ width: `${Math.min(100, Number(founder.share_percent))}%` }" />
              </span>
            </span>
          </FactRow>
          <FactRow label="Адрес" :hint="egrul.value.mass_address ? 'массовый адрес' : 'не массовый'" :tone="egrul.value.mass_address ? 'warning' : 'default'">
            {{ egrul.value.address }}
          </FactRow>
          <FactRow label="Недостоверность" :tone="egrul.value.unreliable?.length ? 'brand' : 'default'">
            {{ egrul.value.unreliable?.length ? egrul.value.unreliable.map((item) => label(UNRELIABLE_LABEL, item)).join(', ') : 'отметок нет' }}
          </FactRow>
        </dl>
      </SourceCard>

      <SourceCard v-if="fns" title="ФНС" :status="fns.status">
        <dl>
          <FactRow label="Недоимка" :tone="Number(fns.value.tax_arrears) > 0 ? 'brand' : 'default'">
            <span class="tabular-nums">{{ money(fns.value.tax_arrears) }}</span>
          </FactRow>
          <FactRow v-if="fns.value.reported_revenue" :label="`Выручка ${fns.value.report_year ?? ''}`" :hint="fns.revenueHint">
            <span class="tabular-nums">{{ money(fns.value.reported_revenue) }}</span>
          </FactRow>
          <FactRow v-if="fns.value.reported_expenses" :label="`Расходы ${fns.value.report_year ?? ''}`">
            <span class="tabular-nums">{{ money(fns.value.reported_expenses) }}</span>
          </FactRow>
          <FactRow
            label="Численность"
            :hint="fns.employees !== null && fns.employees !== fns.value.avg_headcount ? `в анкете ${fns.employees}` : null"
          >
            {{ fns.value.avg_headcount }}
          </FactRow>
          <FactRow label="Режим по ФНС">{{ fns.value.tax_regime }}</FactRow>
        </dl>
        <ul class="mt-2 grid grid-cols-2 gap-1.5">
          <li
            v-for="flag in fns.flags"
            :key="flag.text"
            class="flex items-start gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold"
            :class="flag.ok ? 'bg-success-soft text-success' : flag.neutral ? 'bg-surface text-ink-secondary' : 'bg-brand-soft text-brand'"
          >
            <CircleCheck v-if="flag.ok" class="mt-px size-3.5 shrink-0" aria-hidden="true" />
            <CircleX v-else class="mt-px size-3.5 shrink-0" aria-hidden="true" />
            {{ flag.text }}
          </li>
        </ul>
        <ul v-if="fns.value.account_blocks?.length" class="mt-2 space-y-0.5 text-xs text-brand">
          <li v-for="block in fns.value.account_blocks" :key="block.decision_number">
            № {{ block.decision_number }} от {{ formatDate(block.date) }}, ИФНС {{ block.authority_code }} — {{ block.reason }}
          </li>
        </ul>
      </SourceCard>

      <BureauCard v-if="enrichment.bki" title="Бюро кредитных историй — компания" :history="enrichment.bki" />
      <BureauCard v-if="enrichment.bki_head" title="БКИ руководителя" :history="enrichment.bki_head" />

      <SourceCard
        v-if="kontur"
        title="Контур"
        :status="{ tone: RELIABILITY[kontur.reliability]?.tone ?? 'neutral', label: RELIABILITY[kontur.reliability]?.label ?? kontur.reliability }"
        wide
      >
        <div class="grid grid-cols-2 gap-2.5 @xl:grid-cols-4">
          <StatTile label="Суды — ответчик" :tone="kontur.arbitration.as_defendant > 0 ? 'warning' : 'default'" :hint="`на ${money(kontur.arbitration.defendant_sum)} · истец — ${kontur.arbitration.as_plaintiff}`">
            {{ kontur.arbitration.as_defendant }}
          </StatTile>
          <StatTile label="Исп. производства" :tone="kontur.enforcement.active > 0 ? 'warning' : 'default'" :hint="`на ${money(kontur.enforcement.sum)}`">
            {{ kontur.enforcement.active }}
          </StatTile>
          <StatTile label="Сообщения о банкротстве" :tone="kontur.bankruptcy_messages.length ? 'brand' : 'default'">
            {{ kontur.bankruptcy_messages.length }}
          </StatTile>
          <StatTile label="Госконтракты · залоги" :hint="`контракты на ${money(kontur.gov_contracts.sum)}`">
            {{ kontur.gov_contracts.count }} · {{ kontur.active_pledges }}
          </StatTile>
        </div>
        <ul v-if="kontur.notes.length" class="mt-2 space-y-0.5 text-xs text-ink-secondary">
          <li v-for="note in kontur.notes" :key="note">{{ note }}</li>
        </ul>
      </SourceCard>

      <GirBoCard v-if="enrichment.gir_bo" :gir-bo="enrichment.gir_bo" />

      <CashflowCard v-if="enrichment.cashflow" :cashflow="enrichment.cashflow" />
      <div v-else-if="noStatement" class="flex items-center gap-3.5 rounded-2xl border border-dashed border-line bg-surface-soft p-4 @xl:col-span-2">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white text-ink-secondary" aria-hidden="true">
          <Waves class="size-4" />
        </span>
        <p class="text-sm">
          <span class="block font-semibold text-ink">Денежный поток по выпискам</span>
          <span class="text-ink-secondary">Клиент не загружал выписку по счёту — прогноз кассового разрыва не строили.</span>
        </p>
      </div>

      <AmlCheckSection v-if="enrichment.aml" :aml="enrichment.aml" :risk-group="riskGroup" />
      <BankDataSection v-if="enrichment.bank_stop_list || enrichment.bank_turnover" :stop-list="enrichment.bank_stop_list" :turnover="enrichment.bank_turnover" />
    </div>
  </PanelCard>
</template>
