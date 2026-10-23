<script setup lang="ts">
import { computed } from 'vue'

import { CLIENT_STATUS_META, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL } from '@/entities/credit-product'
import type { StageKey, StageState, StageWindow } from '@/entities/process'
import {
  GRADE_ZONE,
  gradeTone,
  label,
  OUTCOME_LABEL,
  REASON_LABEL,
  REVIEW_LABEL,
  SOURCE_LABEL,
  TASK_STATUS_LABEL,
  TASK_TYPE_LABEL,
  ZONE_LABEL,
} from '@/entities/underwriting'
import type { UnderwriterCardDto } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney, formatPercent, formatRelativeTime, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

/** Что карточка заявки знает про этап маршрута: данные, решение, задача, предложение и события этапа */
const props = defineProps<{
  stage: StageKey
  state: StageState
  card: UnderwriterCardDto
  windows: readonly StageWindow[]
}>()

const money = (value: string | null | undefined) => (value === null || value === undefined ? '—' : formatMoney(Number(value)))
const application = computed(() => props.card.application)
const decision = computed(() => props.card.decision)
const manual = computed(() => decision.value?.decided_by_type === 'underwriter')

const documentTitle = (type: string) => DOCUMENT_TITLE[type] ?? type
const documents = computed(() => application.value.documents.map((item) => documentTitle(item.type)).join(', '))

const INFO_REQUEST_STATUS: Record<string, string> = { open: 'ждём ответа клиента', answered: 'клиент ответил', cancelled: 'снят' }

/** События карточки, пока заявка была на этапе — по заходам на него */
const events = computed(() => {
  const time = (value: string) => new Date(value).getTime()
  return props.card.timeline.filter((entry) =>
    props.windows.some(
      (window) => (window.from === null || time(entry.at) >= time(window.from)) && (window.to === null || time(entry.at) < time(window.to)),
    ),
  )
})

const models = computed(() => {
  const scoring = props.card.scoring
  if (!scoring) return []
  return [
    { title: 'PD-модель', score: scoring.score, grade: scoring.grade },
    ...(scoring.ml ? [{ title: 'ML-модель', score: scoring.ml.score, grade: scoring.ml.grade }] : []),
  ]
})
</script>

<template>
  <div class="mt-3 space-y-3 text-sm">
    <template v-if="stage === 'submitted'">
      <dl class="grid gap-x-6 gap-y-2 sm:grid-cols-3">
        <div v-if="application.request">
          <dt class="text-xs text-ink-secondary">Запрос</dt>
          <dd class="font-medium text-ink">{{ money(application.request.amount) }} на {{ formatTerm(application.request.term_months) }}</dd>
        </div>
        <div v-if="application.submitted_at">
          <dt class="text-xs text-ink-secondary">Подана</dt>
          <dd class="font-medium text-ink">{{ formatDateTime(application.submitted_at) }}</dd>
        </div>
        <div>
          <dt class="text-xs text-ink-secondary">Документов</dt>
          <dd class="font-medium text-ink">{{ application.documents.filter((item) => item.status !== 'pending_upload').length }}</dd>
        </div>
      </dl>
    </template>

    <template v-else-if="stage === 'completeness'">
      <p v-if="application.documents.length" class="text-ink">
        Документы: {{ documents }}
      </p>
      <p v-if="application.info_requests.some((item) => item.status === 'open')" class="text-warning">
        Открыт дозапрос — после ответа клиента полноту проверят снова.
      </p>
      <p v-else-if="state === 'done'" class="text-ink-secondary">Комплект полный — заявка ушла за данными о компании.</p>
    </template>

    <template v-else-if="stage === 'info_request'">
      <ul v-if="application.info_requests.length" class="space-y-2">
        <li v-for="request in application.info_requests" :key="request.id" class="rounded-lg bg-white p-2.5">
          <p class="text-ink">
            {{ request.requested_documents.map(documentTitle).join(', ') || 'Уточнение данных' }}
          </p>
          <p v-if="request.comment" class="text-xs text-ink-secondary">«{{ request.comment }}»</p>
          <p class="mt-0.5 text-xs text-ink-secondary">
            {{ formatDateTime(request.created_at) }} · {{ INFO_REQUEST_STATUS[request.status] ?? request.status
            }}<template v-if="request.answered_at"> {{ formatDateTime(request.answered_at) }}</template>
          </p>
        </li>
      </ul>
      <p v-else class="text-ink-secondary">Дозапросов по заявке не было.</p>
    </template>

    <template v-else-if="stage === 'enrichment'">
      <template v-if="card.enrichment">
        <div class="flex flex-wrap gap-1.5">
          <BaseBadge v-for="source in card.enrichment.sources_ok" :key="source" tone="success">{{ label(SOURCE_LABEL, source) }}</BaseBadge>
          <BaseBadge v-for="item in card.enrichment.sources_failed" :key="item.source" tone="brand">
            {{ label(SOURCE_LABEL, item.source) }} — не ответил
          </BaseBadge>
          <BaseBadge v-for="item in card.enrichment.sources_skipped ?? []" :key="item.source">
            {{ label(SOURCE_LABEL, item.source) }} — не запрашивали
          </BaseBadge>
        </div>
        <ul v-if="card.enrichment.sources_failed.length || card.enrichment.sources_skipped?.length" class="space-y-0.5 text-xs text-ink-secondary">
          <li v-for="item in [...card.enrichment.sources_failed, ...(card.enrichment.sources_skipped ?? [])]" :key="item.source">
            {{ label(SOURCE_LABEL, item.source) }}: {{ item.message }}
          </li>
        </ul>
        <p v-if="card.enrichment.cashflow?.gap_detected" class="text-warning">
          По выпискам ожидается кассовый разрыв<template v-if="card.enrichment.cashflow.gap_month"> в {{ card.enrichment.cashflow.gap_month }}</template>
        </p>
        <p class="text-xs text-ink-secondary">Собрано {{ formatDateTime(card.enrichment.collected_at) }} — подробности в «Внешних источниках» ниже</p>
      </template>
      <p v-else class="text-ink-secondary">Данные ещё собираются.</p>
    </template>

    <template v-else-if="stage === 'collateral'">
      <p v-if="application.collateral" class="text-ink">
        {{ COLLATERAL_TYPE_LABEL[application.collateral.type] ?? application.collateral.type }},
        {{ money(application.collateral.declared_value) }} — {{ application.collateral.description }}
        <span class="text-ink-secondary">(собственник: {{ application.collateral.owner }})</span>
      </p>
      <p v-else class="text-ink-secondary">Залог в заявке не указан.</p>
    </template>

    <template v-else-if="stage === 'scoring'">
      <div v-if="models.length" class="grid grid-cols-2 gap-2 sm:max-w-md">
        <div v-for="model in models" :key="model.title" class="rounded-lg bg-white p-2.5">
          <p class="text-xs text-ink-secondary">{{ model.title }}</p>
          <p class="mt-0.5 flex items-center gap-2">
            <span class="text-lg font-bold text-ink tabular-nums">{{ model.score }}</span>
            <BaseBadge :tone="gradeTone(model.grade)">{{ model.grade }}</BaseBadge>
          </p>
          <p class="text-xs text-ink-secondary">{{ ZONE_LABEL[GRADE_ZONE[model.grade]]?.label }}</p>
        </div>
      </div>
      <p v-else class="text-ink-secondary">Скоринг ещё не посчитан.</p>
    </template>

    <template v-else-if="stage === 'decision' || stage === 'rejected'">
      <template v-if="decision">
        <div class="flex flex-wrap items-center gap-2">
          <BaseBadge :tone="OUTCOME_LABEL[decision.outcome]?.tone ?? 'neutral'">{{ OUTCOME_LABEL[decision.outcome]?.label ?? decision.outcome }}</BaseBadge>
          <BaseBadge v-if="decision.review" :tone="REVIEW_LABEL[decision.review].tone">{{ REVIEW_LABEL[decision.review].label }}</BaseBadge>
          <span class="text-xs text-ink-secondary">{{ manual ? 'решил андеррайтер' : 'автоматически' }} · {{ formatDateTime(decision.decided_at) }}</span>
        </div>
        <ul v-if="decision.reason_codes.length" class="space-y-0.5 text-ink">
          <li v-for="code in decision.reason_codes" :key="code">• {{ label(REASON_LABEL, code) }}</li>
        </ul>
        <p v-if="decision.limits.final" class="text-ink-secondary">Итоговый лимит {{ money(decision.limits.final) }}</p>
        <p v-if="stage === 'rejected' && decision.client_explanation" class="rounded-lg bg-white p-2.5 text-ink-secondary">
          Клиенту: «{{ decision.client_explanation }}»
        </p>
      </template>
      <p v-else class="text-ink-secondary">Решения ещё нет.</p>
    </template>

    <template v-else-if="stage === 'underwriter'">
      <template v-if="card.task">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-medium text-ink">{{ TASK_TYPE_LABEL[card.task.type] ?? 'Задача андеррайтера' }}</span>
          <BaseBadge :tone="card.task.status === 'done' ? 'success' : card.task.status === 'cancelled' ? 'neutral' : 'info'">
            {{ TASK_STATUS_LABEL[card.task.status] ?? card.task.status }}
          </BaseBadge>
          <span v-if="card.task.status === 'open' || card.task.status === 'in_progress'" class="text-xs text-ink-secondary">
            {{ card.task.assignee_id ? 'взята в работу' : 'никто не взял' }}
          </span>
        </div>
        <p v-if="card.task.due_at && card.task.status !== 'done' && card.task.status !== 'cancelled'" class="text-ink-secondary">
          Срок решения — {{ formatDateTime(card.task.due_at) }}
          <span :class="new Date(card.task.due_at).getTime() < Date.now() ? 'font-medium text-brand' : ''">({{ formatRelativeTime(card.task.due_at) }})</span>
        </p>
      </template>
      <template v-if="decision && manual">
        <p class="text-ink">
          Решение: <b>{{ OUTCOME_LABEL[decision.outcome]?.label ?? decision.outcome }}</b>
          <template v-if="decision.terms"> — {{ money(decision.terms.amount) }} под {{ formatPercent(Number(decision.terms.rate)) }}</template>
        </p>
        <p v-if="decision.comment" class="text-ink-secondary">«{{ decision.comment }}»</p>
      </template>
      <p v-if="!card.task && !manual" class="text-ink-secondary">Заявку андеррайтеру не передавали.</p>
    </template>

    <template v-else-if="stage === 'offer' || stage === 'signing' || stage === 'disbursement'">
      <p v-if="application.offer" class="text-ink">
        {{ money(application.offer.amount) }} на {{ formatTerm(application.offer.term_months) }} под
        {{ formatPercent(Number(application.offer.rate)) }}, платёж
        {{ money(application.offer.monthly_payment) }}
        <span v-if="stage === 'offer'" class="text-ink-secondary"> · действует до {{ formatDate(application.offer.expires_at) }}</span>
      </p>
      <p class="text-ink-secondary">Для клиента: {{ CLIENT_STATUS_META[card.client_status].label }}</p>
    </template>

    <p v-else-if="stage === 'closed'" class="text-ink-secondary">
      Клиент отказался от предложения или не ответил вовремя<template v-if="application.offer">
        — предложение действовало до {{ formatDate(application.offer.expires_at) }}</template
      >
    </p>

    <div v-if="events.length">
      <p class="text-xs font-medium text-ink-secondary">События этапа</p>
      <ul class="mt-1 space-y-0.5">
        <li v-for="entry in events" :key="entry.id" class="flex flex-wrap justify-between gap-x-3 text-ink">
          <span>{{ entry.title }}</span>
          <span class="text-xs text-ink-secondary">{{ formatDateTime(entry.at) }} · {{ entry.audience === 'bank' ? 'банк' : 'клиент' }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
