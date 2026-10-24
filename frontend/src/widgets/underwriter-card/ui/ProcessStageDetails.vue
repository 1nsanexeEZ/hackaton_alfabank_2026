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
  qualityReasonLabel,
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

import type { PreludeData } from '../model/usePrelude'

/** Что карточка заявки знает про этап маршрута: данные, решение, задача, предложение и события этапа */
const props = defineProps<{
  stage: StageKey
  state: StageState
  card: UnderwriterCardDto
  windows: readonly StageWindow[]
  /** Что было с компанией до заявки — для этапов до подачи */
  pre: PreludeData | null
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

const SOURCE_TEXT: Record<string, string> = { profile: 'из профиля', application: 'галочкой в заявке' }
const VERIFICATION_TEXT: Record<string, string> = {
  verified: 'сверена — предодобрение считается',
  mismatch: 'расхождения с реестром — без сверки предодобрения нет',
  unverified: 'ещё не сверяли — без сверки предодобрения нет',
}
const BASIS_TEXT: Record<string, string> = { estimate: 'по данным компании', full: 'с проверками', project: 'по проектной оценке' }
const offer = computed(() => props.pre?.offers.find((item) => item.product_code === application.value.product_code) ?? null)

/** Сработавшие стоп-факторы: с ними заявка идёт мимо скоринга на отказ (или к специалисту у ИП без согласия на авторешение) */
const stopCodes = computed(() => decision.value?.reason_codes.filter((code) => code.startsWith('STOP_')) ?? [])

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
    <template v-if="stage === 'pre:consents'">
      <ul class="space-y-0.5 text-ink">
        <li>
          Обработка ПДн —
          {{ application.consents?.personal_data_at
            ? `${SOURCE_TEXT[application.consents.personal_data_source ?? ''] ?? 'дано'}, ${formatDateTime(application.consents.personal_data_at)}`
            : 'не дано' }}
        </li>
        <li>
          Запрос в БКИ компании —
          {{ application.consents?.credit_bureau_at
            ? `${SOURCE_TEXT[application.consents.credit_bureau_source ?? ''] ?? 'дано'}, ${formatDateTime(application.consents.credit_bureau_at)}`
            : 'не дано' }}
        </li>
        <li v-if="application.org_snapshot?.legal_form === 'IE'">
          Решение автоматикой —
          {{ application.consents?.automated_decision_at ? `дано, ${formatDateTime(application.consents.automated_decision_at)}` : 'не дано' }}
        </li>
      </ul>
      <p v-if="application.status === 'draft'" class="text-xs text-ink-secondary">
        Черновик: согласия из профиля он берёт сам, недостающие клиент отмечает перед подачей.
      </p>
    </template>

    <template v-else-if="stage === 'pre:prescoring'">
      <p v-if="application.org_snapshot" class="text-ink">
        Сверка с ЕГРЮЛ: {{ VERIFICATION_TEXT[application.org_snapshot.verification_status] ?? application.org_snapshot.verification_status }}
      </p>
      <p v-if="offer" class="text-ink">
        Предодобрено по продукту до <b>{{ money(offer.max_amount) }}</b> от {{ formatPercent(Number(offer.rate_from)) }},
        {{ BASIS_TEXT[offer.basis ?? ''] ?? '' }} · действует до {{ formatDate(offer.valid_until) }}
      </p>
      <p v-else-if="pre" class="text-ink-secondary">По этому продукту предодобрения нет — решение по полной проверке.</p>
      <p v-if="pre && pre.offers.length > (offer ? 1 : 0)" class="text-xs text-ink-secondary">
        Другие предодобренные продукты: {{ pre.offers.filter((item) => item !== offer).length }}
      </p>
      <p v-if="application.status === 'draft'" class="text-xs text-ink-secondary">
        Клиент выбирает условия — калькулятор считает по ставке предодобрения, заявка ещё не подана.
      </p>
    </template>

    <template v-else-if="stage === 'pre:prescreen'">
      <template v-if="pre?.prescreen">
        <p class="text-ink">
          {{ pre.prescreen.founder.name }} — {{ pre.prescreen.status === 'passed' ? 'пройдена' : 'не пройдена' }},
          {{ formatDateTime(pre.prescreen.checked_at) }}{{ pre.prescreen.valid ? `, действует до ${formatDate(pre.prescreen.valid_until)}` : ', срок истёк' }}
        </p>
        <ul class="space-y-0.5 text-ink-secondary">
          <li v-for="reason in pre.prescreen.reasons" :key="reason.code">{{ reason.passed ? '✓' : '✗' }} {{ reason.message }}</li>
        </ul>
      </template>
      <p v-else class="text-ink-secondary">Проверку учредителя не проходили.</p>
    </template>

    <template v-else-if="stage === 'pre:project'">
      <template v-if="pre?.project">
        <p class="text-ink">
          {{ pre.project.status === 'passed' ? 'Пройдена' : 'Не пройдена' }}, {{ formatDateTime(pre.project.checked_at)
          }}<template v-if="pre.project.max_amount"> — предодобрено до <b>{{ money(pre.project.max_amount) }}</b></template>
        </p>
        <ul class="space-y-0.5 text-ink-secondary">
          <li v-for="reason in pre.project.reasons" :key="reason.code">{{ reason.passed ? '✓' : '✗' }} {{ reason.message }}</li>
        </ul>
        <p class="text-xs text-ink-secondary">Цифры оценки — в панели «Проект стартапа» ниже.</p>
      </template>
      <p v-else class="text-ink-secondary">Проектную оценку не проходили — сумму определит специалист.</p>
    </template>

    <template v-else-if="stage === 'submitted'">
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

    <template v-else-if="stage === 'stop_factors'">
      <template v-if="stopCodes.length">
        <p class="font-medium text-brand">Сработали стоп-факторы — скоринг не нужен:</p>
        <ul class="space-y-0.5 text-ink">
          <li v-for="code in stopCodes" :key="code">• {{ label(REASON_LABEL, code) }}</li>
        </ul>
      </template>
      <p v-else-if="state === 'done'" class="text-ink-secondary">Стоп-факторов нет — заявка пошла дальше по маршруту.</p>
      <p v-if="card.enrichment?.aml" class="text-xs text-ink-secondary">
        115-ФЗ: совпадений с перечнями — {{ card.enrichment.aml.list_hits.length }}, ПДЛ — {{ card.enrichment.aml.pep_hits.length }}, риск
        ЗСК — {{ { low: 'низкий', medium: 'средний', high: 'высокий' }[card.enrichment.aml.zsk.level] }}
      </p>
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
      <p v-if="card.scoring?.quality === 'degraded'" class="rounded-lg bg-warning-soft p-2.5 text-ink">
        Данные неполные — решение за специалистом<template v-if="card.scoring.quality_reasons?.length"
          >: {{ card.scoring.quality_reasons.map(qualityReasonLabel).join(', ') }}</template
        >
      </p>
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
