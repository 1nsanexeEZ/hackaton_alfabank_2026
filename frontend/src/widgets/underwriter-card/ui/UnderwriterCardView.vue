<script setup lang="ts">
import { CircleCheck, CircleX, Download, Waves } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { beneficiaryLine, CLIENT_STATUS_META, collateralOwnerLine, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL, PURPOSE_LABEL, useProductCatalog } from '@/entities/credit-product'
import { ProcessMap } from '@/entities/process'
import {
  CATEGORY_LABEL,
  FACTOR_LABEL,
  FLAG_LABEL,
  GRADE_ZONE,
  gradeTone,
  label,
  LIMIT_LABEL,
  OUTCOME_LABEL,
  qualityReasonLabel,
  REASON_LABEL,
  RELIABILITY,
  REVIEW_LABEL,
  SEGMENT_LABEL,
  SOURCE_LABEL,
  TASK_TYPE_LABEL,
  UNRELIABLE_LABEL,
  ZONE_LABEL,
  type GradeZone,
} from '@/entities/underwriting'
import { TaskDecisionForm } from '@/features/complete-underwriter-task'
import { backofficeApi, type FactorDto, type Grade, type LoanPurpose } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney, formatPercent, formatProbability, formatTerm, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, PanelCard, SegmentedControl } from '@/shared/ui'

import { usePrelude } from '../model/usePrelude'
import AmlCheckSection from './AmlCheckSection.vue'
import BankDataSection from './BankDataSection.vue'
import ProcessStageDetails from './ProcessStageDetails.vue'
import StartupProjectPanel from './StartupProjectPanel.vue'

/**
 * Карточка заявки для андеррайтера (GET /bff/backoffice/applications/{id}): что просит клиент,
 * что ответили внешние источники, как посчитал скоринг и почему движок принял такое решение.
 * Если заявка ждёт специалиста — здесь же задача и форма решения. Сверху — маршрут заявки
 * в реальном времени: продвинулся процесс — карточку перечитываем, чтобы подробности этапов были свежими.
 */
const props = defineProps<{ applicationId: string }>()

const card = useAsyncData(() => backofficeApi.card(props.applicationId))
const data = computed(() => card.data.value)
const processMap = ref<{ refresh: () => Promise<void> } | null>(null)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

/** Этапы до подачи на схеме маршрута: согласия и предскоринг, у стартапа — проверка учредителя и проектная оценка */
const isStartup = computed(() => Boolean(products.value?.find((product) => product.code === data.value?.application.product_code)?.startupOnly))
const prelude = usePrelude(data, isStartup)
const money = (value: string | null | undefined) => (value === null || value === undefined ? '—' : formatMoney(Number(value)))

const REGISTRY_STATUS: Record<string, string> = {
  active: 'Действует',
  liquidating: 'Ликвидируется',
  liquidated: 'Ликвидирована',
  bankrupt: 'Банкротство',
  reorganizing: 'Реорганизуется',
  excluded: 'Исключена из реестра',
}
const REPORT_SOURCE: Record<string, string> = { declared: 'Заявлено', fns: 'ФНС', bank_statement: 'Выписки' }

/**
 * Согласия заявки: когда даны и откуда — галочка в черновике или из профиля. Согласие на решение только
 * автоматикой (ст. 16 152-ФЗ) важно у ИП: без него отказ и встречное предложение принимает человек.
 */
const consents = computed(() => {
  const value = data.value?.application.consents
  if (!value) return []
  const given = (at: string | null | undefined, source: string | null | undefined) =>
    at ? `${source === 'profile' ? 'из профиля' : 'в заявке'}, ${formatDate(at)}` : 'нет'
  const list = [
    { title: 'Обработка ПДн', value: given(value.personal_data_at, value.personal_data_source) },
    { title: 'БКИ компании', value: given(value.credit_bureau_at, value.credit_bureau_source) },
  ]
  if (data.value?.application.org_snapshot?.legal_form === 'IE') {
    list.push({
      title: 'Решение автоматикой',
      value: value.automated_decision_at ? `дано, ${formatDate(value.automated_decision_at)}` : 'нет — неблагоприятное решение примет специалист',
    })
  }
  return list
})

/** Решение по задаче процесс применяет асинхронно — перечитываем, пока задача не закроется */
async function refreshAfterDecision() {
  void processMap.value?.refresh()
  for (let attempt = 0; attempt < 8; attempt++) {
    await card.reload()
    const task = card.data.value?.task
    if (!task || task.status === 'done' || task.status === 'cancelled') return
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}

async function download(documentId: string) {
  const { url } = await backofficeApi.downloadDocument(props.applicationId, documentId)
  window.open(url, '_blank', 'noopener')
}

/**
 * Две оценки риска (policy_v5): экспертная PD-модель и обученная ML-модель на одной шкале A–J.
 * Совпали зоны — решает автоматика, разошлись — человек; поэтому итог «согласны / расходятся» сверху.
 */
type ScoringModel = 'pd' | 'ml'
const MODEL_TABS: readonly { value: ScoringModel; label: string }[] = [
  { value: 'pd', label: 'PD-модель' },
  { value: 'ml', label: 'ML-модель' },
]
const factorsOf = ref<ScoringModel>('pd')

const models = computed(() => {
  const scoring = data.value?.scoring
  if (!scoring) return []
  const list: { key: ScoringModel; title: string; version: string; score: number; grade: Grade; pd: string | null }[] = [
    { key: 'pd', title: 'PD-модель', version: scoring.model_version, score: scoring.score, grade: scoring.grade, pd: scoring.pd_12m ?? null },
  ]
  if (scoring.ml) {
    list.push({ key: 'ml', title: 'ML-модель', version: scoring.ml.model_version, score: scoring.ml.score, grade: scoring.ml.grade, pd: scoring.ml.pd_12m })
  }
  return list
})
const modelsAgree = computed(() => {
  const [pd, ml] = models.value
  return Boolean(pd && ml && GRADE_ZONE[pd.grade] === GRADE_ZONE[ml.grade])
})
/** «Модели согласны — обе в жёлтой зоне» / «Модели расходятся: PD — зелёная, ML — красная» */
const ZONE_WORD: Record<GradeZone, { one: string; both: string }> = {
  green: { one: 'зелёная', both: 'зелёной' },
  yellow: { one: 'жёлтая', both: 'жёлтой' },
  red: { one: 'красная', both: 'красной' },
}
const modelsVerdict = computed(() => {
  const [pd, ml] = models.value
  if (!pd || !ml) return null
  const pdZone = GRADE_ZONE[pd.grade]
  const mlZone = GRADE_ZONE[ml.grade]
  return pdZone === mlZone
    ? `Модели согласны — обе в ${ZONE_WORD[pdZone].both} зоне`
    : `Модели расходятся: PD — ${ZONE_WORD[pdZone].one}, ML — ${ZONE_WORD[mlZone].one}`
})

const shownFactors = computed(() => {
  const scoring = data.value?.scoring
  const factors = factorsOf.value === 'ml' && scoring?.ml ? scoring.ml.factors : (scoring?.factors ?? [])
  return [...factors].sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
})
/** Значение и корзина признака по-русски; совпали (у категорий) — одно, без значения — только корзина */
const factorDetail = (factor: FactorDto) =>
  [...new Set([factor.value, factor.bin].filter((part): part is string => Boolean(part)).map((part) => CATEGORY_LABEL[part] ?? part))].join(' · ')

const shownReasons = computed(() => {
  const scoring = data.value?.scoring
  return (factorsOf.value === 'ml' && scoring?.ml ? scoring.ml.reason_codes : scoring?.reason_codes) ?? []
})

/** Учредитель по реестру: у юрлица — с ИНН */
const founderLine = (founder: { name: string; share_percent: string; inn?: string | null }) =>
  `${founder.name}${founder.inn ? `, ИНН ${founder.inn}` : ''} (${Number(founder.share_percent)}%)`

/** Кредитные истории: компании и руководителя (вторая — только с его личным согласием) */
const bureaus = computed(() => {
  const enrichment = data.value?.enrichment
  return [
    { key: 'bki', title: 'Бюро кредитных историй', history: enrichment?.bki ?? null },
    { key: 'bki_head', title: 'БКИ руководителя', history: enrichment?.bki_head ?? null },
  ].filter((item) => item.history)
})

/** Бухотчётность ГИР БО — последние годы сверху */
const accountingPeriods = computed(() => [...(data.value?.enrichment?.gir_bo?.periods ?? [])].sort((a, b) => b.year - a.year).slice(0, 3))

/** Лимиты движка, какие посчитаны; binding — тот, что дал итоговую сумму */
const limits = computed(() => {
  const value = data.value?.decision?.limits
  if (!value) return []
  return Object.entries(LIMIT_LABEL)
    .map(([key, title]) => ({ key, title, amount: value[key as keyof typeof value] ?? null, binding: value.binding === key }))
    .filter((item) => item.amount !== null)
})

const RATE_PARTS = [
  { key: 'funding', title: 'Фондирование' },
  { key: 'expected_loss', title: 'Ожидаемые потери' },
  { key: 'capital', title: 'Капитал' },
  { key: 'margin', title: 'Маржа' },
] as const
</script>

<template>
  <AsyncState :loading="card.loading.value && !data" :error="data ? null : card.error.value" @retry="card.reload">
    <div v-if="data" class="space-y-4">
      <ProcessMap
        ref="processMap"
        :application-id="applicationId"
        :prelude="prelude.stages.value"
        :fallback-workflow="data.application.product_terms.workflow_code ?? null"
        @advance="card.reload"
      >
        <template #details="stage">
          <ProcessStageDetails v-bind="stage" :card="data" :pre="prelude.data.value" />
        </template>
        <template v-if="data.timeline.length" #footer>
          <details class="mt-4 text-sm">
            <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Все события заявки ({{ data.timeline.length }})</summary>
            <ol class="relative mt-3 space-y-3 border-l border-line pl-5">
              <li v-for="entry in data.timeline" :key="entry.id" class="relative">
                <span
                  class="absolute top-1.5 -left-[1.625rem] size-2.5 rounded-full ring-4 ring-white"
                  :class="entry.audience === 'bank' ? 'bg-info' : 'bg-ink-muted'"
                  aria-hidden="true"
                />
                <p class="text-sm text-ink">{{ entry.title }}</p>
                <p class="text-xs text-ink-secondary">{{ formatDateTime(entry.at) }} · {{ entry.audience === 'bank' ? 'банк' : 'клиент' }}</p>
              </li>
            </ol>
          </details>
        </template>
      </ProcessMap>

      <div class="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div class="space-y-4">
          <PanelCard :title="`Заявка № ${data.application.number}`">
            <div class="flex flex-wrap items-center gap-2">
              <BaseBadge :tone="CLIENT_STATUS_META[data.client_status].tone">{{ CLIENT_STATUS_META[data.client_status].label }}</BaseBadge>
              <span v-if="data.application.client_stage" class="text-sm text-ink-secondary">{{ data.application.client_stage }}</span>
            </div>
            <dl class="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div>
                <dt class="text-ink-secondary">Продукт</dt>
                <dd class="font-medium text-ink">{{ productTitle(data.application.product_code) }}</dd>
              </div>
              <div v-if="data.application.request">
                <dt class="text-ink-secondary">Запрос</dt>
                <dd class="font-medium text-ink">
                  {{ money(data.application.request.amount) }} на {{ formatTerm(data.application.request.term_months) }}
                </dd>
              </div>
              <div v-if="data.application.request">
                <dt class="text-ink-secondary">Цель</dt>
                <dd class="font-medium text-ink">
                  {{ PURPOSE_LABEL[data.application.request.purpose as LoanPurpose] ?? data.application.request.purpose }}
                  <span v-if="data.application.request.purpose_comment" class="font-normal text-ink-secondary">
                    — {{ data.application.request.purpose_comment }}
                  </span>
                </dd>
              </div>
              <div>
                <dt class="text-ink-secondary">Лимит авторешения</dt>
                <dd class="font-medium text-ink">{{ money(data.application.product_terms.auto_decision_limit) }}</dd>
              </div>
              <div v-if="data.application.collateral">
                <dt class="text-ink-secondary">Залог</dt>
                <dd class="font-medium text-ink">
                  {{ COLLATERAL_TYPE_LABEL[data.application.collateral.type] ?? data.application.collateral.type }},
                  {{ money(data.application.collateral.declared_value) }} — {{ data.application.collateral.description }}
                  <span class="font-normal text-ink-secondary">· собственник: {{ collateralOwnerLine(data.application.collateral) }}</span>
                </dd>
              </div>
              <!-- Ответ клиента о третьем лице (115-ФЗ): по нему выгодоприобретатель проверяется вместе с остальными -->
              <div class="sm:col-span-2">
                <dt class="text-ink-secondary">Выгодоприобретатель</dt>
                <dd class="font-medium" :class="data.application.beneficiary?.acts_for_third_party ? 'text-warning' : 'text-ink'">
                  {{ data.application.beneficiary ? beneficiaryLine(data.application.beneficiary) : 'Клиент не ответил' }}
                </dd>
              </div>
              <div v-if="data.application.submitted_at">
                <dt class="text-ink-secondary">Подана</dt>
                <dd class="font-medium text-ink">{{ formatDateTime(data.application.submitted_at) }}</dd>
              </div>
              <div v-if="consents.length" class="sm:col-span-2">
                <dt class="text-ink-secondary">Согласия</dt>
                <dd class="text-ink">
                  <span v-for="(item, index) in consents" :key="item.title">
                    {{ item.title }} — {{ item.value }}<template v-if="index < consents.length - 1">; </template>
                  </span>
                </dd>
              </div>
            </dl>

            <div v-if="data.application.documents.length" class="mt-5">
              <p class="text-sm font-semibold text-ink">Документы</p>
              <ul class="mt-2 space-y-1.5">
                <li
                  v-for="document in data.application.documents.filter((item) => item.status !== 'pending_upload')"
                  :key="document.id"
                  class="flex items-center justify-between gap-3 rounded-lg bg-surface-soft px-3 py-2 text-sm"
                >
                  <span class="min-w-0 truncate">
                    {{ DOCUMENT_TITLE[document.type] ?? document.type }} · <span class="text-ink-secondary">{{ document.filename }}</span>
                  </span>
                  <button
                    type="button"
                    class="flex size-8 shrink-0 items-center justify-center rounded-lg text-ink-secondary hover:bg-white hover:text-ink"
                    :aria-label="`Скачать ${document.filename}`"
                    @click="download(document.id)"
                  >
                    <Download class="size-4" aria-hidden="true" />
                  </button>
                </li>
              </ul>
            </div>
          </PanelCard>

          <PanelCard v-if="data.application.org_snapshot" title="Компания" description="Снимок на момент подачи">
            <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              <div>
                <dt class="text-ink-secondary">Наименование</dt>
                <dd class="font-medium text-ink">{{ data.application.org_snapshot.name }}</dd>
              </div>
              <div>
                <dt class="text-ink-secondary">ИНН / ОГРН</dt>
                <dd class="font-medium text-ink">{{ data.application.org_snapshot.inn }} / {{ data.application.org_snapshot.ogrn }}</dd>
              </div>
              <div>
                <dt class="text-ink-secondary">Статус в реестре</dt>
                <dd class="font-medium text-ink">
                  {{ REGISTRY_STATUS[data.application.org_snapshot.registry_status] ?? data.application.org_snapshot.registry_status }}
                </dd>
              </div>
              <div>
                <dt class="text-ink-secondary">Возраст бизнеса</dt>
                <dd class="font-medium text-ink">{{ formatTerm(data.application.org_snapshot.business_age_months) }}</dd>
              </div>
              <div>
                <dt class="text-ink-secondary">ОКВЭД · сотрудников</dt>
                <dd class="font-medium text-ink">
                  {{ data.application.org_snapshot.okved_main }} · {{ data.application.org_snapshot.employees_count }}
                </dd>
              </div>
              <div>
                <dt class="text-ink-secondary">Руководитель</dt>
                <dd class="font-medium text-ink">{{ data.application.org_snapshot.head_name ?? '—' }}</dd>
              </div>
            </dl>
            <div
              v-if="data.application.org_snapshot.verification_status === 'mismatch'"
              class="mt-4 rounded-xl bg-warning-soft p-3 text-sm text-ink"
            >
              <p class="font-medium">Расхождения с ЕГРЮЛ</p>
              <ul class="mt-1 text-ink-secondary">
                <li v-for="item in data.application.org_snapshot.discrepancies" :key="item.field">
                  {{ item.field }}: в кабинете «{{ item.declared ?? '—' }}», в реестре «{{ item.registry ?? '—' }}»
                </li>
              </ul>
            </div>
            <div v-if="data.application.org_snapshot.financial_reports.length" class="mt-4 overflow-x-auto">
              <table class="w-full min-w-[28rem] text-left text-sm">
                <thead class="text-xs text-ink-secondary">
                  <tr>
                    <th class="py-2 font-medium">Период</th>
                    <th class="py-2 font-medium">Источник</th>
                    <th class="py-2 text-right font-medium">Выручка</th>
                    <th class="py-2 text-right font-medium">Платежи по долгам / мес.</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  <tr v-for="report in data.application.org_snapshot.financial_reports" :key="`${report.period_year}-${report.period_quarter}-${report.source}`">
                    <td class="py-2">{{ report.period_quarter ? `${report.period_quarter} кв. ` : '' }}{{ report.period_year }}</td>
                    <td class="py-2 text-ink-secondary">{{ REPORT_SOURCE[report.source] ?? report.source }}</td>
                    <td class="py-2 text-right tabular-nums">{{ money(report.revenue) }}</td>
                    <td class="py-2 text-right tabular-nums">{{ money(report.monthly_debt_payments) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </PanelCard>

          <PanelCard v-if="data.enrichment" title="Внешние источники" :description="`Собрано ${formatDateTime(data.enrichment.collected_at)}`">
            <div class="flex flex-wrap gap-2">
              <BaseBadge v-for="source in data.enrichment.sources_ok" :key="source" tone="success">{{ label(SOURCE_LABEL, source) }}</BaseBadge>
              <BaseBadge v-for="failed in data.enrichment.sources_failed" :key="failed.source" tone="brand">
                {{ label(SOURCE_LABEL, failed.source) }}: не ответил
              </BaseBadge>
              <BaseBadge v-for="skipped in data.enrichment.sources_skipped ?? []" :key="`skip-${skipped.source}`" :title="skipped.message">
                {{ label(SOURCE_LABEL, skipped.source) }}: не запрашивали
              </BaseBadge>
            </div>
            <ul v-if="data.enrichment.sources_skipped?.length" class="mt-2 space-y-0.5 text-xs text-ink-secondary">
              <li v-for="skipped in data.enrichment.sources_skipped" :key="`why-${skipped.source}`">
                {{ label(SOURCE_LABEL, skipped.source) }} — {{ skipped.message }}
              </li>
            </ul>

            <div class="mt-5 grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-2">
              <section v-if="data.enrichment.egrul" class="text-sm">
                <p class="font-semibold text-ink">ЕГРЮЛ / ЕГРИП</p>
                <ul class="mt-2 space-y-1 text-ink">
                  <li>Статус: {{ REGISTRY_STATUS[data.enrichment.egrul.status] ?? data.enrichment.egrul.status }}</li>
                  <li v-if="data.enrichment.egrul.kpp">КПП: {{ data.enrichment.egrul.kpp }}</li>
                  <li>
                    Руководитель: {{ data.enrichment.egrul.head_last_name }} {{ data.enrichment.egrul.head_first_name }}
                    {{ data.enrichment.egrul.head_middle_name ?? '' }}, {{ data.enrichment.egrul.head_position
                    }}{{ data.enrichment.egrul.head_since ? `, с ${formatDate(data.enrichment.egrul.head_since)}` : '' }}
                  </li>
                  <li v-if="data.enrichment.egrul.founders.length">Учредители: {{ data.enrichment.egrul.founders.map(founderLine).join('; ') }}</li>
                  <li v-if="data.enrichment.egrul.unreliable?.length" class="text-brand">
                    Отметка о недостоверности: {{ data.enrichment.egrul.unreliable.map((item) => label(UNRELIABLE_LABEL, item)).join(', ') }}
                  </li>
                  <li :class="data.enrichment.egrul.mass_address && 'text-warning'">
                    Адрес: {{ data.enrichment.egrul.address }}{{ data.enrichment.egrul.mass_address ? ' — массовый' : '' }}
                  </li>
                </ul>
              </section>

              <section v-if="data.enrichment.fns" class="text-sm">
                <p class="font-semibold text-ink">ФНС</p>
                <ul class="mt-2 space-y-1 text-ink">
                  <li :class="Number(data.enrichment.fns.tax_arrears) > 0 && 'text-brand'">Недоимка: {{ money(data.enrichment.fns.tax_arrears) }}</li>
                  <li v-if="data.enrichment.fns.reported_revenue">
                    Выручка за {{ data.enrichment.fns.report_year }}: {{ money(data.enrichment.fns.reported_revenue) }}
                  </li>
                  <li>Среднесписочная численность: {{ data.enrichment.fns.avg_headcount }}</li>
                  <li :class="data.enrichment.fns.disqualified_head && 'text-brand'">
                    Дисквалификация руководителя: {{ data.enrichment.fns.disqualified_head ? 'есть' : 'нет' }}
                  </li>
                  <li v-if="typeof data.enrichment.fns.mass_head === 'boolean'" :class="data.enrichment.fns.mass_head && 'text-brand'">
                    Массовый руководитель: {{ data.enrichment.fns.mass_head ? 'да' : 'нет' }}
                  </li>
                  <li>Реестр МСП: {{ data.enrichment.fns.in_msp_registry ? 'есть' : 'нет' }}</li>
                  <li :class="data.enrichment.fns.account_blocks?.length ? 'text-brand' : ''">
                    Приостановления по счетам: {{ data.enrichment.fns.account_blocks?.length ? '' : 'нет' }}
                  </li>
                  <li v-for="block in data.enrichment.fns.account_blocks ?? []" :key="block.decision_number" class="pl-3 text-xs text-brand">
                    № {{ block.decision_number }} от {{ formatDate(block.date) }}, ИФНС {{ block.authority_code }} — {{ block.reason }}
                  </li>
                </ul>
              </section>

              <section v-for="bureau in bureaus" :key="bureau.key" class="text-sm lg:col-span-2">
                <p class="font-semibold text-ink">{{ bureau.title }}</p>
                <p class="mt-2 text-ink">
                  Платежи по кредитам: {{ money(bureau.history!.total_monthly_payments) }} в месяц · запросов за 30 дней:
                  {{ bureau.history!.inquiries_last_30d }} ·
                  <span :class="bureau.history!.max_overdue_days_12m > 0 && 'text-brand'">
                    макс. просрочка за 12 мес.: {{ bureau.history!.max_overdue_days_12m }} дн.
                  </span>
                  <span v-if="bureau.history!.has_active_overdue" class="text-brand"> · есть текущая просрочка</span>
                </p>
                <div v-if="bureau.history!.obligations.length" class="mt-2 overflow-x-auto">
                  <table class="w-full min-w-[36rem] text-left text-sm">
                    <thead class="text-xs text-ink-secondary">
                      <tr>
                        <th class="py-2 font-medium">Кредитор</th>
                        <th class="py-2 text-right font-medium">Остаток</th>
                        <th class="py-2 text-right font-medium">Платёж</th>
                        <th class="py-2 text-right font-medium">Просрочка</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line">
                      <tr v-for="(item, index) in bureau.history!.obligations" :key="index">
                        <td class="py-2">{{ item.creditor }} <span class="text-ink-secondary">· {{ item.kind }}</span></td>
                        <td class="py-2 text-right tabular-nums">{{ money(item.balance) }}</td>
                        <td class="py-2 text-right tabular-nums">{{ money(item.monthly_payment) }}</td>
                        <td class="py-2 text-right tabular-nums" :class="item.overdue_days > 0 && 'text-brand'">{{ item.overdue_days }} дн.</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section v-if="data.enrichment.kontur" class="text-sm">
                <p class="flex flex-wrap items-center gap-2 font-semibold text-ink">
                  Контур
                  <BaseBadge :tone="RELIABILITY[data.enrichment.kontur.reliability]?.tone ?? 'neutral'">
                    {{ RELIABILITY[data.enrichment.kontur.reliability]?.label ?? data.enrichment.kontur.reliability }}
                  </BaseBadge>
                </p>
                <ul class="mt-2 space-y-1 text-ink">
                  <li :class="data.enrichment.kontur.arbitration.as_defendant > 0 && 'text-warning'">
                    Суды: ответчик {{ data.enrichment.kontur.arbitration.as_defendant }} на {{ money(data.enrichment.kontur.arbitration.defendant_sum) }},
                    истец {{ data.enrichment.kontur.arbitration.as_plaintiff }}
                  </li>
                  <li :class="data.enrichment.kontur.enforcement.active > 0 && 'text-warning'">
                    Исполнительные производства: {{ data.enrichment.kontur.enforcement.active }} на {{ money(data.enrichment.kontur.enforcement.sum) }}
                  </li>
                  <li :class="data.enrichment.kontur.bankruptcy_messages.length > 0 && 'text-brand'">
                    Сообщения о банкротстве: {{ data.enrichment.kontur.bankruptcy_messages.length || 'нет' }}
                  </li>
                  <li>
                    Госконтракты: {{ data.enrichment.kontur.gov_contracts.count }} на {{ money(data.enrichment.kontur.gov_contracts.sum) }} · залогов:
                    {{ data.enrichment.kontur.active_pledges }}
                  </li>
                  <li v-for="note in data.enrichment.kontur.notes" :key="note" class="text-xs text-ink-secondary">{{ note }}</li>
                </ul>
              </section>

              <section v-if="data.enrichment.gir_bo" class="text-sm">
                <p class="font-semibold text-ink">ГИР БО — бухотчётность</p>
                <p v-if="!data.enrichment.gir_bo.available || !accountingPeriods.length" class="mt-2 text-ink-secondary">
                  {{ data.enrichment.gir_bo.reason ?? 'Отчётности в ГИР БО нет' }}
                </p>
                <div v-else class="mt-2 overflow-x-auto">
                  <table class="w-full min-w-[22rem] text-left text-xs">
                    <thead class="text-ink-secondary">
                      <tr>
                        <th class="py-1.5 font-medium">Год</th>
                        <th class="py-1.5 text-right font-medium">Выручка</th>
                        <th class="py-1.5 text-right font-medium">Чистая прибыль</th>
                        <th class="py-1.5 text-right font-medium">Капитал</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line tabular-nums">
                      <tr v-for="period in accountingPeriods" :key="period.year">
                        <td class="py-1.5">{{ period.year }}</td>
                        <td class="py-1.5 text-right">{{ money(period.revenue) }}</td>
                        <td class="py-1.5 text-right" :class="Number(period.net_profit) < 0 && 'text-brand'">{{ money(period.net_profit) }}</td>
                        <td class="py-1.5 text-right" :class="Number(period.equity) < 0 && 'text-brand'">{{ money(period.equity) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section v-if="data.enrichment.cashflow" class="text-sm lg:col-span-2">
                <p class="flex items-center gap-2 font-semibold text-ink">
                  <Waves class="size-4" :class="data.enrichment.cashflow.gap_detected ? 'text-warning' : 'text-ink-secondary'" aria-hidden="true" />
                  Денежный поток по выпискам
                </p>
                <p class="mt-2" :class="data.enrichment.cashflow.gap_detected ? 'text-warning' : 'text-ink'">
                  <template v-if="data.enrichment.cashflow.gap_detected">
                    Прогноз кассового разрыва: {{ data.enrichment.cashflow.gap_month }} на {{ money(data.enrichment.cashflow.gap_amount) }}
                  </template>
                  <template v-else>Кассового разрыва в прогнозе нет</template>
                  · поступления за год {{ money(data.enrichment.cashflow.annual_inflow) }}
                  <template v-if="data.enrichment.cashflow.revenue_confirmed !== null">
                    · выручка {{ data.enrichment.cashflow.revenue_confirmed ? 'подтверждена' : 'не подтверждена' }}
                  </template>
                </p>
                <div class="mt-2 overflow-x-auto">
                  <table class="w-full min-w-[36rem] text-left text-xs">
                    <thead class="text-ink-secondary">
                      <tr>
                        <th class="py-1.5 font-medium">Месяц</th>
                        <th class="py-1.5 text-right font-medium">Приход</th>
                        <th class="py-1.5 text-right font-medium">Расход</th>
                        <th class="py-1.5 text-right font-medium">Остаток</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line">
                      <tr v-for="month in data.enrichment.cashflow.months_history" :key="month.month">
                        <td class="py-1.5">{{ month.month }}</td>
                        <td class="py-1.5 text-right tabular-nums">{{ money(month.inflow) }}</td>
                        <td class="py-1.5 text-right tabular-nums">{{ money(month.outflow) }}</td>
                        <td class="py-1.5 text-right tabular-nums" :class="Number(month.balance) < 0 && 'text-brand'">{{ money(month.balance) }}</td>
                      </tr>
                      <tr v-for="month in data.enrichment.cashflow.forecast" :key="`f-${month.month}`" class="text-ink-secondary">
                        <td class="py-1.5">{{ month.month }} (прогноз)</td>
                        <td class="py-1.5" colspan="2" />
                        <td class="py-1.5 text-right tabular-nums" :class="Number(month.projected_balance) < 0 && 'text-brand'">
                          {{ money(month.projected_balance) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <AmlCheckSection v-if="data.enrichment.aml" :aml="data.enrichment.aml" />
              <BankDataSection
                v-if="data.enrichment.bank_stop_list || data.enrichment.bank_turnover"
                :stop-list="data.enrichment.bank_stop_list"
                :turnover="data.enrichment.bank_turnover"
              />
            </div>
          </PanelCard>
        </div>

        <div class="space-y-4">
          <PanelCard
            v-if="data.task"
            :title="TASK_TYPE_LABEL[data.task.type] ?? 'Задача андеррайтера'"
            :description="data.task.type === 'project_assessment' ? 'Стартап: бизнес-план, финмодель, обеспечение и господдержка' : undefined"
          >
            <TaskDecisionForm :task="data.task" :card="data" @claimed="card.reload" @decided="refreshAfterDecision" />
          </PanelCard>

          <StartupProjectPanel v-if="data.startup" :project="data.startup" />

          <PanelCard
            v-if="data.scoring"
            title="Скоринг"
            :description="[
              data.scoring.scorecard && `Скоркарта ${data.scoring.scorecard}`,
              data.scoring.segment && (SEGMENT_LABEL[data.scoring.segment] ?? data.scoring.segment),
              `полнота данных ${formatPercent(Number(data.scoring.data_completeness) * 100)}`,
            ]
              .filter(Boolean)
              .join(' · ')"
          >
            <p v-if="data.scoring.quality === 'degraded'" class="mb-3 rounded-lg bg-warning-soft p-2.5 text-sm text-ink">
              <span class="font-semibold">Данные неполные — решает специалист</span
              ><template v-if="data.scoring.quality_reasons?.length">: {{ data.scoring.quality_reasons.map(qualityReasonLabel).join(', ') }}</template>
            </p>
            <p v-if="modelsVerdict" class="mb-3 text-sm font-semibold" :class="modelsAgree ? 'text-ink' : 'text-warning'">
              {{ modelsVerdict }}
            </p>
            <p v-else class="mb-3 text-xs text-ink-secondary">Оценки ML-модели нет: заявку оценили до того, как появилась вторая модель</p>

            <div class="grid grid-cols-2 gap-3">
              <div v-for="model in models" :key="model.key" class="min-w-0 rounded-lg bg-surface-soft p-3">
                <p class="text-xs text-ink-secondary">{{ model.title }}</p>
                <p class="mt-1 flex flex-wrap items-center gap-2">
                  <span class="text-2xl font-bold text-ink tabular-nums">{{ model.score }}</span>
                  <BaseBadge :tone="gradeTone(model.grade)">{{ model.grade }}</BaseBadge>
                </p>
                <p v-if="model.pd" class="mt-1 text-xs text-ink-secondary">PD 12 мес.: {{ formatProbability(Number(model.pd)) }}</p>
                <p class="mt-1 flex items-center gap-1.5 text-xs text-ink">
                  <span
                    class="size-2 shrink-0 rounded-full"
                    :class="{ 'bg-success': GRADE_ZONE[model.grade] === 'green', 'bg-warning': GRADE_ZONE[model.grade] === 'yellow', 'bg-brand': GRADE_ZONE[model.grade] === 'red' }"
                    aria-hidden="true"
                  />
                  {{ ZONE_LABEL[GRADE_ZONE[model.grade]]?.label ?? '—' }}
                </p>
                <p class="mt-1 truncate text-[11px] text-ink-muted" :title="model.version">{{ model.version }}</p>
              </div>
            </div>

            <div v-if="data.scoring.flags.length" class="mt-3 flex flex-wrap gap-1.5">
              <BaseBadge v-for="flag in data.scoring.flags" :key="flag" tone="warning">{{ label(FLAG_LABEL, flag) }}</BaseBadge>
            </div>

            <SegmentedControl v-if="models.length === 2" v-model="factorsOf" class="mt-4" :options="MODEL_TABS" label="Признаки какой модели показать" />
            <p v-if="shownReasons.length" class="mt-3 text-xs text-ink-secondary">
              Сильнее всего снизили балл: {{ shownReasons.map((code) => label(FACTOR_LABEL, code)).join(', ') }}
            </p>
            <ul class="mt-3 space-y-2 text-sm">
              <li v-for="factor in shownFactors" :key="factor.code" class="flex items-start justify-between gap-3">
                <span class="min-w-0">
                  <span class="text-ink">{{ label(FACTOR_LABEL, factor.code) }}</span>
                  <span v-if="factorDetail(factor)" class="block text-xs text-ink-secondary">{{ factorDetail(factor) }}</span>
                </span>
                <span
                  class="shrink-0 font-semibold tabular-nums"
                  :class="factor.points > 0 ? 'text-success' : factor.points < 0 ? 'text-brand' : 'text-ink-secondary'"
                >
                  {{ factor.points > 0 ? '+' : '' }}{{ factor.points }}
                </span>
              </li>
            </ul>
          </PanelCard>

          <PanelCard v-if="data.decision" title="Решение движка">
            <div class="flex flex-wrap items-center gap-2">
              <BaseBadge :tone="OUTCOME_LABEL[data.decision.outcome]?.tone ?? 'neutral'">
                {{ OUTCOME_LABEL[data.decision.outcome]?.label ?? data.decision.outcome }}
              </BaseBadge>
              <BaseBadge v-if="data.decision.review" :tone="REVIEW_LABEL[data.decision.review].tone">
                {{ REVIEW_LABEL[data.decision.review].label }}
              </BaseBadge>
              <span class="text-xs text-ink-secondary">
                {{ data.decision.decided_by_type === 'auto' ? 'автоматически' : 'андеррайтер' }} ·
                {{ formatDateTime(data.decision.decided_at) }}
              </span>
            </div>
            <ul v-if="data.decision.reason_codes.length" class="mt-3 space-y-1 text-sm text-ink">
              <li v-for="code in data.decision.reason_codes" :key="code">• {{ label(REASON_LABEL, code) }}</li>
            </ul>
            <div v-if="data.decision.triggers?.length" class="mt-3 rounded-lg bg-warning-soft p-2.5 text-sm">
              <p class="text-xs font-medium text-ink">Сработали триггеры ручной проверки</p>
              <ul class="mt-1 space-y-0.5 text-ink">
                <li v-for="trigger in data.decision.triggers" :key="trigger.code">• {{ trigger.detail }}</li>
              </ul>
            </div>
            <dl v-if="data.decision.terms" class="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div class="rounded-lg bg-surface-soft p-2">
                <dt class="text-xs text-ink-secondary">Сумма</dt>
                <dd class="font-semibold">{{ money(data.decision.terms.amount) }}</dd>
              </div>
              <div class="rounded-lg bg-surface-soft p-2">
                <dt class="text-xs text-ink-secondary">Ставка</dt>
                <dd class="font-semibold">{{ formatPercent(Number(data.decision.terms.rate)) }}</dd>
              </div>
            </dl>
            <div v-if="limits.length" class="mt-3 text-xs">
              <p class="font-medium text-ink">
                Лимиты<template v-if="data.decision.limits.final"> · итог {{ money(data.decision.limits.final) }}</template>
              </p>
              <dl class="mt-1 space-y-0.5 text-ink-secondary">
                <div v-for="item in limits" :key="item.key" class="flex justify-between gap-3" :class="item.binding && 'font-semibold text-ink'">
                  <dt>{{ item.title }}<template v-if="item.binding"> — ограничил сумму</template></dt>
                  <dd class="tabular-nums">{{ money(item.amount) }}</dd>
                </div>
              </dl>
            </div>
            <div v-if="data.decision.rate_breakdown" class="mt-3 text-xs">
              <p class="font-medium text-ink">Ставка {{ formatPercent(Number(data.decision.rate_breakdown.total)) }}</p>
              <dl class="mt-1 space-y-0.5 text-ink-secondary">
                <div v-for="part in RATE_PARTS" :key="part.key" class="flex justify-between gap-3">
                  <dt>{{ part.title }}</dt>
                  <dd class="tabular-nums">{{ formatPercent(Number(data.decision.rate_breakdown[part.key])) }}</dd>
                </div>
              </dl>
            </div>
            <p class="mt-3 text-xs text-ink-secondary">
              Политика {{ data.decision.policy_version }} · ключевая ставка {{ formatPercent(Number(data.decision.key_rate)) }}
            </p>
            <details class="mt-3 text-sm">
              <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Как движок пришёл к решению</summary>
              <ul class="mt-2 space-y-1.5">
                <li v-for="(hit, index) in data.decision.rule_trace" :key="index" class="flex items-start gap-2" :class="!hit.matched && 'text-ink-muted'">
                  <CircleCheck v-if="hit.matched" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
                  <CircleX v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  <span>{{ hit.detail }} <span class="text-xs text-ink-muted">({{ hit.rule }})</span></span>
                </li>
              </ul>
            </details>
          </PanelCard>

          <PanelCard v-if="data.product_fit" title="Соответствие продукту">
            <ul class="space-y-1.5 text-sm">
              <li v-for="reason in data.product_fit.reasons" :key="reason.code" class="flex items-start gap-2">
                <CircleCheck v-if="reason.passed" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
                <CircleX v-else class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
                {{ reason.message }}
              </li>
            </ul>
          </PanelCard>

          <p v-if="data.degraded.length" class="text-xs text-ink-secondary">Часть данных недоступна: {{ data.degraded.join(', ') }}</p>
          <p v-if="data.application.offer" class="text-xs text-ink-secondary">
            Предложение клиенту: {{ money(data.application.offer.amount) }} на {{ formatTerm(data.application.offer.term_months) }} под
            {{ formatPercent(Number(data.application.offer.rate)) }}, до {{ formatDate(data.application.offer.expires_at) }}
          </p>
        </div>
      </div>
    </div>
  </AsyncState>
</template>
