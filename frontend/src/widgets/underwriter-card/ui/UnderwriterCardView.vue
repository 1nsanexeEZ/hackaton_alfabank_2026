<script setup lang="ts">
import { CircleCheck, CircleX, Download, Waves } from 'lucide-vue-next'
import { computed } from 'vue'

import { CLIENT_STATUS_META, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL, PURPOSE_LABEL, useProductCatalog } from '@/entities/credit-product'
import {
  FACTOR_LABEL,
  FLAG_LABEL,
  GRADE_TONE,
  label,
  OUTCOME_LABEL,
  REASON_LABEL,
  SOURCE_LABEL,
} from '@/entities/underwriting'
import { TaskDecisionForm } from '@/features/complete-underwriter-task'
import { backofficeApi, type LoanPurpose } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney, formatPercent, formatTerm, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, PanelCard } from '@/shared/ui'

/**
 * Карточка заявки для андеррайтера (GET /bff/backoffice/applications/{id}): что просит клиент,
 * что ответили внешние источники, как посчитал скоринг и почему движок принял такое решение.
 * Если заявка ждёт специалиста — здесь же задача и форма решения.
 */
const props = defineProps<{ applicationId: string }>()

const card = useAsyncData(() => backofficeApi.card(props.applicationId))
const data = computed(() => card.data.value)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code
const money = (value: string | null | undefined) => (value === null || value === undefined ? '—' : formatMoney(Number(value)))

const REGISTRY_STATUS: Record<string, string> = { active: 'Действует', liquidating: 'Ликвидируется', liquidated: 'Ликвидирована', bankrupt: 'Банкротство' }
const REPORT_SOURCE: Record<string, string> = { declared: 'Заявлено', fns: 'ФНС', bank_statement: 'Выписки' }

/** Решение по задаче процесс применяет асинхронно — перечитываем, пока задача не закроется */
async function refreshAfterDecision() {
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

const sortedFactors = computed(() => [...(data.value?.scoring?.factors ?? [])].sort((a, b) => Math.abs(b.points) - Math.abs(a.points)))
</script>

<template>
  <AsyncState :loading="card.loading.value && !data" :error="data ? null : card.error.value" @retry="card.reload">
    <div v-if="data" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
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
              </dd>
            </div>
            <div v-if="data.application.submitted_at">
              <dt class="text-ink-secondary">Подана</dt>
              <dd class="font-medium text-ink">{{ formatDateTime(data.application.submitted_at) }}</dd>
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
          </div>

          <div class="mt-5 grid gap-5 lg:grid-cols-2">
            <section v-if="data.enrichment.egrul" class="text-sm">
              <p class="font-semibold text-ink">ЕГРЮЛ / ЕГРИП</p>
              <ul class="mt-2 space-y-1 text-ink">
                <li>Статус: {{ REGISTRY_STATUS[data.enrichment.egrul.status] ?? data.enrichment.egrul.status }}</li>
                <li>
                  Руководитель: {{ data.enrichment.egrul.head_last_name }} {{ data.enrichment.egrul.head_first_name }}
                  {{ data.enrichment.egrul.head_middle_name ?? '' }}, {{ data.enrichment.egrul.head_position }}
                </li>
                <li v-if="data.enrichment.egrul.founders.length">
                  Учредители: {{ data.enrichment.egrul.founders.map((item) => `${item.name} (${Number(item.share_percent)}%)`).join(', ') }}
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
                <li>Реестр МСП: {{ data.enrichment.fns.in_msp_registry ? 'есть' : 'нет' }}</li>
              </ul>
            </section>

            <section v-if="data.enrichment.bki" class="text-sm lg:col-span-2">
              <p class="font-semibold text-ink">Бюро кредитных историй</p>
              <p class="mt-2 text-ink">
                Платежи по кредитам: {{ money(data.enrichment.bki.total_monthly_payments) }} в месяц · запросов за 30 дней:
                {{ data.enrichment.bki.inquiries_last_30d }} ·
                <span :class="data.enrichment.bki.max_overdue_days_12m > 0 && 'text-brand'">
                  макс. просрочка за 12 мес.: {{ data.enrichment.bki.max_overdue_days_12m }} дн.
                </span>
              </p>
              <div v-if="data.enrichment.bki.obligations.length" class="mt-2 overflow-x-auto">
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
                    <tr v-for="(item, index) in data.enrichment.bki.obligations" :key="index">
                      <td class="py-2">{{ item.creditor }} <span class="text-ink-secondary">· {{ item.kind }}</span></td>
                      <td class="py-2 text-right tabular-nums">{{ money(item.balance) }}</td>
                      <td class="py-2 text-right tabular-nums">{{ money(item.monthly_payment) }}</td>
                      <td class="py-2 text-right tabular-nums" :class="item.overdue_days > 0 && 'text-brand'">{{ item.overdue_days }} дн.</td>
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
          </div>
        </PanelCard>

        <PanelCard v-if="data.process || data.timeline.length" title="Ход процесса">
          <ol v-if="data.process" class="space-y-1.5 text-sm">
            <li v-for="(step, index) in data.process.steps" :key="`${step.node_id}-${index}`" class="flex flex-wrap justify-between gap-2">
              <span class="text-ink">{{ step.step_code ?? step.node_id }}<span v-if="step.outcome" class="text-ink-secondary"> → {{ step.outcome }}</span></span>
              <span class="text-xs text-ink-secondary">{{ formatDateTime(step.started_at) }}</span>
            </li>
          </ol>
          <ol v-if="data.timeline.length" class="relative mt-4 space-y-3 border-l border-line pl-5">
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
        </PanelCard>
      </div>

      <div class="space-y-4">
        <PanelCard v-if="data.task" title="Задача андеррайтера">
          <TaskDecisionForm :task="data.task" :card="data" @claimed="card.reload" @decided="refreshAfterDecision" />
        </PanelCard>

        <PanelCard v-if="data.scoring" title="Скоринг" :description="`Модель ${data.scoring.model_version} · полнота данных ${data.scoring.data_completeness}`">
          <div class="flex items-center gap-3">
            <span class="text-3xl font-bold text-ink tabular-nums">{{ data.scoring.score }}</span>
            <BaseBadge :tone="GRADE_TONE[data.scoring.grade] ?? 'neutral'">Грейд {{ data.scoring.grade }}</BaseBadge>
          </div>
          <div v-if="data.scoring.flags.length" class="mt-3 flex flex-wrap gap-1.5">
            <BaseBadge v-for="flag in data.scoring.flags" :key="flag" tone="warning">{{ label(FLAG_LABEL, flag) }}</BaseBadge>
          </div>
          <ul class="mt-4 space-y-2 text-sm">
            <li v-for="factor in sortedFactors" :key="factor.code" class="flex items-start justify-between gap-3">
              <span class="min-w-0">
                <span class="text-ink">{{ label(FACTOR_LABEL, factor.code) }}</span>
                <span v-if="factor.value" class="block text-xs text-ink-secondary">{{ factor.value }} · {{ factor.bin }}</span>
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
            <span class="text-xs text-ink-secondary">
              {{ data.decision.decided_by_type === 'auto' ? 'автоматически' : 'андеррайтер' }} ·
              {{ formatDateTime(data.decision.decided_at) }}
            </span>
          </div>
          <ul v-if="data.decision.reason_codes.length" class="mt-3 space-y-1 text-sm text-ink">
            <li v-for="code in data.decision.reason_codes" :key="code">• {{ label(REASON_LABEL, code) }}</li>
          </ul>
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
          <dl class="mt-3 space-y-1 text-xs text-ink-secondary">
            <div v-if="data.decision.limits.by_revenue">Лимит по выручке: {{ money(data.decision.limits.by_revenue) }}</div>
            <div v-if="data.decision.limits.by_ltv">Лимит по залогу: {{ money(data.decision.limits.by_ltv) }}</div>
            <div v-if="data.decision.limits.by_capacity">Лимит по платёжеспособности: {{ money(data.decision.limits.by_capacity) }}</div>
            <div>Политика {{ data.decision.policy_version }} · ключевая ставка {{ formatPercent(Number(data.decision.key_rate)) }}</div>
          </dl>
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
  </AsyncState>
</template>
