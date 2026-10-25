<script setup lang="ts">
import { AlertCircle, ArrowRight, CircleCheck, Clock, Download, FileText, Inbox, PenLine } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'

import { CLIENT_STATUS_META, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL, PURPOSE_LABEL, REPAYMENT_LABEL, type ProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import type { LoanPurpose, Repayment } from '@/shared/api'
import { formatDateTime, formatMoney, formatTerm, shakeInvalid } from '@/shared/lib'
import { AsyncState, BaseButton, TextField } from '@/shared/ui'

import { timeLeft } from '../model/presentation'
import { hasContractDocument, useApplicationCard } from '../model/useApplicationCard'
import ApplicationEvents from './ApplicationEvents.vue'
import CardHeader from './CardHeader.vue'
import ContractSheet from './ContractSheet.vue'
import DecisionPanel from './DecisionPanel.vue'
import HeadConsentNotice from './HeadConsentNotice.vue'
import InfoRequestPanel from './InfoRequestPanel.vue'
import ScheduleView from './ScheduleView.vue'
import SignaturesView from './SignaturesView.vue'
import SignSteps from './SignSteps.vue'
import TermTiles from './TermTiles.vue'

/**
 * Окно заявки глазами клиента. Сверху тёмная шапка с этапами, дальше «Сейчас» — что происходит и что
 * нужно от клиента, условия крупными цифрами и вкладки «Условия / График / Договор / История / Уведомления / Документы».
 * Главные действия — в подвале окна, вне прокрутки: «Принять предложение», «Подписать договор»…
 * Действия — только те, что разрешил бэкенд (available_actions), статус обновляется сам.
 * Окно рисует себя целиком: BaseModal открывает его в режиме bare.
 */
const props = defineProps<{
  applicationId: string
  products: ProductCatalog | null
  /** id заголовка окна — на него ссылается aria-labelledby диалога */
  titleId: string
  backLabel: string | null
}>()

const emit = defineEmits<{
  /** Черновик: вернуться в мастер с компанией и условиями */
  continueDraft: [draft: { productCode: string; organizationId: string; amount: number; termMonths: number; purpose?: LoanPurpose }]
  /** Оформить другой продукт — например, тот, что посоветовал банк */
  applyProduct: [code: string]
  back: []
  close: []
  /** Вопрос в поддержку по этой заявке */
  ask: [applicationId: string]
}>()

const SIGN_FORM_ID = 'application-sign-form'

const application = useApplicationCard(() => props.applicationId)
const {
  card,
  details,
  loading,
  error,
  busy,
  actionError,
  actionErrorCode,
  uploadErrors,
  contract,
  contractError,
  documentSlow,
  rules,
  rulesError,
  infoDocuments,
  can,
} = application

/*
 * Ошибка действия показывается там, где клиент действовал: неверный пароль — под полем пароля,
 * остальное — в подвале рядом с кнопками, а не над всей карточкой, где её не видно.
 */
const passwordError = computed(() => (actionErrorCode.value === 'invalid_password' ? actionError.value : null))
const footerError = computed(() => (passwordError.value ? null : actionError.value))

const status = computed(() => card.value?.client_status ?? null)
const meta = computed(() => (status.value ? CLIENT_STATUS_META[status.value] : null))
/** Ручное рассмотрение: этап процесса «Заявка у специалиста» */
const atSpecialist = computed(() => card.value?.client_stage?.toLowerCase().includes('специалист') ?? false)
const unsignedContract = computed(() => status.value === 'signing' && contract.value?.status === 'unsigned')

/** Согласие руководителя на его БКИ нужно, пока банк рассматривает заявку */
const headConsentMissing = computed(() => {
  const head = card.value?.consents?.head_credit_bureau
  const deciding = ['submitted', 'checking', 'scoring', 'info_requested'].includes(status.value ?? '')
  return head && head.required && !head.given && deciding && card.value?.organization ? head : null
})

const productTitle = (code: string) => props.products?.find((product) => product.code === code)?.title ?? null

// --- «Сейчас»: что происходит и что нужно от клиента ------------------------------------------------

type NowTone = 'neutral' | 'success' | 'negative'
interface Now {
  tone: NowTone
  icon: Component
  eyebrow: string
  title: string
  text: string
  chip: string | null
}

const NOW_TONE: Record<NowTone, { box: string; icon: string; eyebrow: string }> = {
  neutral: { box: 'bg-surface-soft', icon: 'bg-white text-ink', eyebrow: 'text-brand-active' },
  success: { box: 'bg-success-soft', icon: 'bg-success text-white', eyebrow: 'text-success' },
  negative: { box: 'bg-brand-soft', icon: 'bg-white text-brand', eyebrow: 'text-brand-active' },
}

const now = computed<Now | null>(() => {
  const value = card.value
  if (!value || !status.value) return null
  const expires = value.offer?.expires_at
  const until = expires ? `до ${formatDateTime(expires)}` : ''
  const chip = expires ? timeLeft(expires) : null
  const base = { tone: 'neutral' as NowTone, eyebrow: 'Сейчас', chip: null }
  switch (status.value) {
    case 'draft':
      return { ...base, icon: FileText, eyebrow: 'Черновик', title: 'Заявка ещё не отправлена в банк', text: 'Всё, что вы заполнили, сохранено. Продолжите, когда будете готовы.' }
    case 'submitted':
    case 'checking':
    case 'scoring':
      return atSpecialist.value
        ? { ...base, icon: Clock, title: 'Заявку смотрит специалист банка', text: 'Обычно в течение рабочего дня. Если понадобятся документы, запрос придёт сюда — статус обновится сам.' }
        : { ...base, icon: Clock, title: 'Банк проверяет заявку', text: 'Проверяем данные и оцениваем заявку. Обычно несколько минут — статус здесь обновится сам.' }
    case 'info_requested':
      return { ...base, icon: Inbox, title: 'Банку нужны данные', text: 'Загрузите документы и ответьте на запрос ниже — после этого банк продолжит рассмотрение.' }
    case 'approved':
      return { ...base, icon: CircleCheck, chip, title: 'Банк одобрил заявку на запрошенных условиях', text: `Примите предложение ${until} — потом понадобится новое решение банка.` }
    case 'counter_offer':
      return { ...base, icon: CircleCheck, chip, title: 'Банк предлагает другие условия', text: `Сравните с заявкой и примите предложение ${until} — или откажитесь от него.` }
    case 'signing':
      if (contract.value?.status === 'signed') {
        return { ...base, icon: Clock, title: 'Договор подписан вами', text: 'Банк подписывает договор своей электронной подписью и выдаёт кредит — обычно несколько секунд.' }
      }
      if (!can('sign')) {
        return { ...base, icon: PenLine, chip, title: 'Договор ждёт подписи', text: 'Подписать может руководитель компании или сотрудник с доверенностью на подпись.' }
      }
      return { ...base, icon: PenLine, chip, title: 'Подпишите договор', text: `Проверьте проект, примите Правила и подтвердите подпись паролем. Предложение действует ${until}.` }
    case 'issued': {
      const payout = details.value?.disbursement
      const when = payout ? ` ${formatDateTime(payout.disbursed_at)}` : ''
      return {
        ...base,
        tone: 'success',
        icon: CircleCheck,
        eyebrow: 'Готово',
        title: 'Договор подписан сторонами, кредит выдан',
        text: `Деньги отправлены на расчётный счёт компании${when}. На демо-стенде выдача смоделирована: денежных операций нет.`,
      }
    }
    case 'rejected':
      return { ...base, tone: 'negative', icon: AlertCircle, eyebrow: 'Решение банка', title: 'Банк не может выдать кредит', text: 'Почему так и что поможет в следующий раз — ниже.' }
    case 'declined':
      return { ...base, icon: AlertCircle, eyebrow: 'Итог', title: 'Вы отказались от предложения банка', text: 'Новую заявку можно подать в любой момент.' }
    case 'expired':
      return { ...base, icon: Clock, eyebrow: 'Итог', title: 'Срок предложения истёк', text: 'Подайте заявку заново — условия рассчитаем ещё раз.' }
    case 'cancelled':
      return { ...base, icon: AlertCircle, eyebrow: 'Итог', title: 'Заявка отменена', text: 'Новую заявку можно подать в любой момент.' }
  }
  return null
})

// --- Условия -------------------------------------------------------------------------------------

/** Плитки условий — когда есть предложение банка */
const tilesOffer = computed(() =>
  card.value?.offer && ['approved', 'counter_offer', 'signing', 'issued'].includes(status.value ?? '') ? card.value.offer : null,
)

/** Чем контрпредложение отличается от запроса — видно сразу под плитками */
const counterChanges = computed(() => {
  const offer = card.value?.offer
  const request = card.value?.request
  if (status.value !== 'counter_offer' || !offer || !request) return []
  const list: string[] = []
  if (request.amount !== null && Number(request.amount) !== Number(offer.amount)) {
    list.push(`Сумма: просили ${formatMoney(Number(request.amount))}, банк предлагает ${formatMoney(Number(offer.amount))}`)
  }
  if (request.term_months !== null && request.term_months !== offer.term_months) {
    list.push(`Срок: просили ${formatTerm(request.term_months)}, банк предлагает ${formatTerm(offer.term_months)}`)
  }
  return list
})

const termRows = computed(() => {
  const value = card.value
  if (!value) return []
  const request = value.request
  const offer = tilesOffer.value
  const rows: { label: string; value: string }[] = [
    { label: 'Продукт', value: value.product.name ?? value.product.code },
    { label: offer ? 'Сумма в заявке' : 'Сумма', value: request?.amount ? formatMoney(Number(request.amount)) : '—' },
    { label: offer ? 'Срок в заявке' : 'Срок', value: request?.term_months ? formatTerm(request.term_months) : '—' },
    { label: 'Цель', value: request?.purpose ? (PURPOSE_LABEL[request.purpose as LoanPurpose] ?? request.purpose) : '—' },
  ]
  if (offer) rows.push({ label: 'Погашение', value: REPAYMENT_LABEL[offer.schedule_type as Repayment] ?? offer.schedule_type })
  if (offer && (status.value === 'approved' || status.value === 'counter_offer' || unsignedContract.value)) {
    rows.push({ label: 'Предложение действует', value: `до ${formatDateTime(offer.expires_at)}` })
  }
  if (offer?.conditions.length) rows.push({ label: 'Условия банка', value: offer.conditions.join('; ') })
  if (value.collateral) {
    rows.push({
      label: 'Залог',
      value: `${COLLATERAL_TYPE_LABEL[value.collateral.type] ?? value.collateral.type}, ${formatMoney(Number(value.collateral.declared_value))}`,
    })
  }
  if (request?.purpose_comment) rows.push({ label: 'Комментарий', value: request.purpose_comment })
  if (value.submitted_at) rows.push({ label: 'Отправлена', value: formatDateTime(value.submitted_at) })
  return rows
})

const uploadedDocuments = computed(() => card.value?.documents.filter((document) => document.status !== 'pending_upload') ?? [])

// --- Вкладки -------------------------------------------------------------------------------------

type Tab = 'terms' | 'schedule' | 'contract' | 'history' | 'events' | 'documents'

const tabs = computed(() => {
  const list: { id: Tab; label: string; count?: number }[] = [{ id: 'terms', label: 'Условия' }]
  const payments = contract.value?.schedule.payments.length ?? 0
  if (payments) list.push({ id: 'schedule', label: 'График', count: payments })
  if (status.value === 'signing' || status.value === 'issued') list.push({ id: 'contract', label: 'Договор' })
  if (card.value?.timeline.length) list.push({ id: 'history', label: 'История' })
  // Черновик в ленту не пишет: уведомления по заявке появляются после подачи
  if (status.value && status.value !== 'draft') list.push({ id: 'events', label: 'Уведомления' })
  if (uploadedDocuments.value.length) list.push({ id: 'documents', label: 'Документы', count: uploadedDocuments.value.length })
  return list
})

const selectedTab = ref<Tab>('terms')
const currentTab = computed<Tab>(() => (tabs.value.some((tab) => tab.id === selectedTab.value) ? selectedTab.value : 'terms'))

/** Куда сдвигается новая вкладка при переходе: вправо по списку — выезжает справа, назад — слева */
const tabShift = ref('1rem')
watch(currentTab, (next, previous) => {
  const ids = tabs.value.map((tab) => tab.id)
  tabShift.value = ids.indexOf(next) >= ids.indexOf(previous) ? '1rem' : '-1rem'
})

/** Красная линия под активной вкладкой переезжает, а не перескакивает: её место и ширина — от кнопки вкладки */
const tabButtons = new Map<Tab, HTMLElement>()
const indicator = ref({ left: 0, width: 0 })
function setTabButton(id: Tab, element: unknown) {
  if (element instanceof HTMLElement) tabButtons.set(id, element)
  else tabButtons.delete(id)
}
function placeIndicator() {
  const button = tabButtons.get(currentTab.value)
  if (button) indicator.value = { left: button.offsetLeft, width: button.offsetWidth }
}
watch([currentTab, tabs], () => nextTick(placeIndicator), { flush: 'post' })
onMounted(() => {
  nextTick(placeIndicator)
  window.addEventListener('resize', placeIndicator)
})
onBeforeUnmount(() => window.removeEventListener('resize', placeIndicator))

// На подписании и после выдачи главное — договор: открываем его вкладку
watch(
  status,
  (value) => {
    selectedTab.value = value === 'signing' || value === 'issued' ? 'contract' : 'terms'
  },
  { immediate: true },
)

const sealedDocumentId = computed(() => {
  const document = contract.value?.document
  return contract.value?.status === 'signed' && document?.kind === 'signed' && document.status === 'ready' ? (document.id ?? null) : null
})

// --- Подпись -------------------------------------------------------------------------------------

const password = ref('')
const rulesAccepted = ref(false)
/** Клиент скачал проект в этом окне — первый шаг подписи отмечен */
const draftOpened = ref(false)
/** Отказ от предложения или отмена заявки ждут подтверждения с причиной — в подвале */
const confirming = ref<'decline' | 'cancel' | null>(null)
const confirmReason = ref('')

watch(
  () => props.applicationId,
  () => {
    password.value = ''
    rulesAccepted.value = false
    draftOpened.value = false
    confirming.value = null
  },
)

// Клиент исправляет пароль — старая ошибка под полем уходит
watch(password, () => {
  if (actionErrorCode.value !== 'invalid_password') return
  actionError.value = null
  actionErrorCode.value = null
})

async function downloadContract(kind: 'draft' | 'signed') {
  await application.downloadContract(kind)
  if (kind === 'draft' && !actionError.value) draftOpened.value = true
}

const canSubmitSign = computed(() => {
  const value = contract.value
  if (!value || !password.value || busy.value) return false
  if (!hasContractDocument(value)) return true
  const draftReady = value.document?.kind === 'draft' && value.document.status === 'ready'
  return draftReady && rulesAccepted.value && Boolean(rules.value)
})

/** «Подписать» без всего нужного: вздрагивает то, чего не хватает — проект, согласие с Правилами, пароль */
function shakeMissingSign() {
  const form = document.getElementById(SIGN_FORM_ID)
  const value = contract.value
  if (!form || !value) return
  const missing: string[] = []
  if (hasContractDocument(value)) {
    if (!(value.document?.kind === 'draft' && value.document.status === 'ready')) missing.push('draft')
    if (!rulesAccepted.value || !rules.value) missing.push('rules')
  }
  if (!password.value) missing.push('password')
  // У пароля трясём само поле, у Правил — строку с галочкой, у проекта — весь шаг
  const target: Record<string, string> = {
    draft: '[data-sign="draft"]',
    rules: '[data-sign="rules"] label',
    password: '[data-sign="password"] input',
  }
  shakeInvalid(missing.map((step) => form.querySelector(target[step]!)))
}

async function submitSign() {
  if (busy.value) return
  if (!canSubmitSign.value) return shakeMissingSign()
  if (await application.sign(password.value, rulesAccepted.value)) password.value = ''
}

// --- Отказ от предложения и отмена заявки: подтверждение с причиной в подвале ----------------------

function askConfirm(kind: 'decline' | 'cancel') {
  confirmReason.value = ''
  confirming.value = kind
}

async function confirmAction() {
  const done = confirming.value === 'decline' ? await application.decline(confirmReason.value) : await application.cancel(confirmReason.value)
  if (done) confirming.value = null
}

function continueDraft() {
  const value = card.value
  if (!value?.organization) return
  emit('continueDraft', {
    productCode: value.product.code,
    organizationId: value.organization.id,
    amount: Number(value.request?.amount ?? 0),
    termMonths: value.request?.term_months ?? 0,
    purpose: (value.request?.purpose ?? undefined) as LoanPurpose | undefined,
  })
}

const footerHint = computed(() => {
  if (status.value === 'approved' || status.value === 'counter_offer') {
    return can('accept_offer') ? 'Договор сформируется сразу после принятия — подпишете его здесь же, паролем от кабинета.' : null
  }
  if (unsignedContract.value && can('sign')) {
    return canSubmitSign.value
      ? `Подписываете договор № ${contract.value?.number} — ровно тот проект, что открывали.`
      : 'Примите Правила и введите пароль — кнопка станет активной.'
  }
  if (status.value === 'issued' && hasContractDocument(contract.value)) return 'Договор и журнал подписания хранятся в архиве банка без права изменения.'
  return null
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <CardHeader
      :card="card"
      :title-id="titleId"
      :back-label="backLabel"
      :live="liveFeed.state.connected"
      @back="emit('back')"
      @close="emit('close')"
    />

    <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 sm:px-7 sm:py-6">
      <AsyncState :loading="loading && !card" :error="card ? null : error" @retry="application.reload">
        <div v-if="card && meta && now" class="space-y-5">
          <HeadConsentNotice
            v-if="headConsentMissing"
            :organization-id="card.organization!.id"
            :head-name="headConsentMissing.head_name"
            @given="application.reload"
          />

          <section class="flex items-start gap-4 rounded-2xl px-4 py-4 sm:px-5" :class="NOW_TONE[now.tone].box" aria-label="Что сейчас">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl" :class="NOW_TONE[now.tone].icon" aria-hidden="true">
              <component :is="now.icon" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-xs font-bold tracking-wider uppercase" :class="NOW_TONE[now.tone].eyebrow">
                {{ now.eyebrow }}<template v-if="now.chip"><span class="sm:hidden"> · {{ now.chip }}</span></template>
              </p>
              <p class="mt-0.5 text-base font-bold text-ink">{{ now.title }}</p>
              <p class="mt-1 text-sm leading-relaxed text-ink-secondary">{{ now.text }}</p>
            </div>
            <span v-if="now.chip" class="hidden shrink-0 rounded-full border border-line bg-white px-3 py-1.5 text-[0.8125rem] font-semibold whitespace-nowrap text-ink sm:inline">
              {{ now.chip }}
            </span>
          </section>

          <template v-if="tilesOffer">
            <TermTiles :offer="tilesOffer" :compact="status === 'signing'" />
            <p v-if="contract" class="-mt-1 text-sm text-ink-secondary">
              Переплата <b class="text-ink tabular-nums">{{ formatMoney(Number(contract.schedule.total_interest)) }}</b> · всего выплатить
              <b class="text-ink tabular-nums">{{ formatMoney(Number(contract.schedule.total_paid)) }}</b>
            </p>
            <ul v-if="counterChanges.length" class="-mt-1 space-y-1 text-sm text-ink">
              <li v-for="change in counterChanges" :key="change">{{ change }}</li>
            </ul>
          </template>

          <DecisionPanel
            v-if="card.decision && (status === 'counter_offer' || status === 'rejected')"
            :decision="card.decision"
            :alternative-title="card.decision.alternative_product_code ? productTitle(card.decision.alternative_product_code) : null"
            :tone="status === 'rejected' ? 'negative' : 'neutral'"
            @apply-product="(code) => emit('applyProduct', code)"
          />

          <InfoRequestPanel
            v-if="status === 'info_requested' && card.info_request"
            :request="card.info_request"
            :uploaded="infoDocuments"
            :upload-errors="uploadErrors"
            :can-upload="can('upload_document')"
            :can-answer="can('answer_info_request')"
            :busy="busy"
            @upload="application.upload"
            @answer="application.answer"
          />

          <p v-if="card.degraded.length" class="rounded-xl bg-surface-soft p-3 text-xs text-ink-secondary">
            Часть сведений сейчас недоступна, показываем то, что есть.
          </p>

          <div :style="{ '--tab-shift': tabShift }">
            <div class="relative flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line" role="tablist" aria-label="Разделы заявки">
              <button
                v-for="tab in tabs"
                :id="`application-tab-${tab.id}`"
                :key="tab.id"
                :ref="(element) => setTabButton(tab.id, element)"
                type="button"
                role="tab"
                :aria-selected="currentTab === tab.id"
                :aria-controls="`application-panel-${tab.id}`"
                class="shrink-0 px-3 py-3 text-[0.9375rem] whitespace-nowrap transition-colors sm:px-3.5"
                :class="currentTab === tab.id ? 'font-bold text-ink' : 'font-semibold text-ink-secondary hover:text-ink'"
                @click="selectedTab = tab.id"
              >
                {{ tab.label }}<span v-if="tab.count" class="ml-1.5 text-xs font-medium text-ink-secondary">{{ tab.count }}</span>
              </button>
              <span
                class="tab-indicator pointer-events-none absolute bottom-0 left-0 h-0.5 rounded-full bg-brand"
                :style="{ width: `${indicator.width}px`, transform: `translateX(${indicator.left}px)` }"
                aria-hidden="true"
              />
            </div>

            <!-- Панели через v-show: форма подписи остаётся в DOM, кнопка в подвале отправляет её с любой вкладки -->
            <Transition name="tab-panel">
            <div v-show="currentTab === 'terms'" id="application-panel-terms" role="tabpanel" aria-labelledby="application-tab-terms" class="pt-2">
              <dl class="grid sm:grid-cols-2 sm:gap-x-8">
                <div v-for="row in termRows" :key="row.label" class="flex flex-col gap-0.5 border-b border-line py-3">
                  <dt class="text-[0.8125rem] text-ink-secondary">{{ row.label }}</dt>
                  <dd class="text-[0.9375rem] font-medium break-words text-ink">{{ row.value }}</dd>
                </div>
              </dl>
            </div>
            </Transition>

            <Transition name="tab-panel">
            <div v-if="contract" v-show="currentTab === 'schedule'" id="application-panel-schedule" role="tabpanel" aria-labelledby="application-tab-schedule" class="pt-5">
              <ScheduleView :schedule="contract.schedule" />
            </div>
            </Transition>

            <Transition name="tab-panel">
            <div v-show="currentTab === 'contract'" id="application-panel-contract" role="tabpanel" aria-labelledby="application-tab-contract" class="space-y-4 pt-5">
              <template v-if="contract">
                <ContractSheet
                  v-if="hasContractDocument(contract)"
                  :contract="contract"
                  :busy="busy"
                  :slow="documentSlow"
                  @download="downloadContract"
                  @refresh="application.refreshDocument"
                />
                <SignSteps
                  v-if="unsignedContract"
                  v-model:password="password"
                  v-model:rules-accepted="rulesAccepted"
                  :contract="contract"
                  :rules="rules"
                  :rules-error="rulesError"
                  :can-sign="can('sign')"
                  :draft-opened="draftOpened"
                  :busy="busy"
                  :form-id="SIGN_FORM_ID"
                  :password-error="passwordError"
                  :via-demo="customer.state.viaDemo"
                  @submit="submitSign"
                  @reload-rules="application.loadRules"
                  @download="downloadContract"
                />
                <SignaturesView v-if="sealedDocumentId" :document-id="sealedDocumentId" />
                <p v-if="status === 'issued' && !hasContractDocument(contract)" class="text-xs text-ink-secondary">
                  Подписание и выдача смоделированы (моки ЭДО и АБС): реальных подписей и денежных операций нет.
                </p>
              </template>
              <div v-else-if="contractError" class="space-y-3">
                <p class="text-sm text-brand" role="alert">{{ contractError }}</p>
                <BaseButton variant="secondary" size="s" @click="application.reload">Загрузить договор ещё раз</BaseButton>
              </div>
              <p v-else class="text-sm text-ink-secondary">Загружаем договор…</p>
            </div>
            </Transition>

            <Transition name="tab-panel">
            <div v-show="currentTab === 'history'" id="application-panel-history" role="tabpanel" aria-labelledby="application-tab-history" class="pt-5">
              <ol class="relative space-y-4 border-l border-line pl-5">
                <li v-for="(entry, index) in card.timeline" :key="`${entry.at}-${index}`" class="relative">
                  <span
                    class="absolute top-1.5 -left-[1.625rem] size-2.5 rounded-full ring-4 ring-white"
                    :class="index === card.timeline.length - 1 ? 'bg-brand' : 'bg-ink-muted'"
                    aria-hidden="true"
                  />
                  <p class="text-sm font-medium text-ink">{{ entry.title }}</p>
                  <p class="text-xs text-ink-secondary">{{ formatDateTime(entry.at) }}</p>
                </li>
              </ol>
            </div>
            </Transition>

            <Transition name="tab-panel">
            <div v-if="currentTab === 'events'" id="application-panel-events" role="tabpanel" aria-labelledby="application-tab-events" class="pt-5">
              <ApplicationEvents :application-id="card.id" />
            </div>
            </Transition>

            <Transition name="tab-panel">
            <div v-show="currentTab === 'documents'" id="application-panel-documents" role="tabpanel" aria-labelledby="application-tab-documents" class="pt-5">
              <ul class="space-y-2">
                <li
                  v-for="document in uploadedDocuments"
                  :key="document.id"
                  class="flex items-center justify-between gap-3 rounded-xl bg-surface-soft px-4 py-3 text-sm"
                >
                  <div class="min-w-0">
                    <p class="truncate font-medium text-ink">{{ document.filename }}</p>
                    <p class="text-xs text-ink-secondary">{{ DOCUMENT_TITLE[document.type] ?? document.type }}</p>
                    <p v-if="document.review_comment" class="mt-1 text-xs text-warning">{{ document.review_comment }}</p>
                  </div>
                  <button
                    type="button"
                    class="flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-white hover:text-ink"
                    :aria-label="`Скачать ${document.filename}`"
                    @click="application.download(document.id)"
                  >
                    <Download class="size-4" aria-hidden="true" />
                  </button>
                </li>
              </ul>
            </div>
            </Transition>
          </div>
        </div>
      </AsyncState>
    </div>

    <footer v-if="card" class="shrink-0 border-t border-line bg-white px-5 py-3.5 sm:px-7 sm:py-4">
      <p v-if="footerError" class="mb-3 flex items-start gap-2 rounded-xl bg-brand-soft px-3.5 py-2.5 text-sm text-brand" role="alert">
        <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ footerError }}
      </p>
      <div v-if="confirming" class="space-y-3">
        <TextField
          v-model="confirmReason"
          :label="confirming === 'decline' ? 'Почему отказываетесь' : 'Почему отменяете'"
          placeholder="Необязательно"
          :maxlength="500"
        />
        <div class="flex flex-wrap justify-end gap-2.5 max-sm:*:flex-1">
          <BaseButton variant="ghost" :disabled="Boolean(busy)" @click="confirming = null">
            {{ confirming === 'decline' ? 'Не отказываться' : 'Не отменять' }}
          </BaseButton>
          <BaseButton variant="secondary" :loading="busy === confirming" @click="confirmAction">
            {{ confirming === 'decline' ? 'Отказаться от предложения' : 'Отменить заявку' }}
          </BaseButton>
        </div>
      </div>

      <div v-else class="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div class="min-w-0 flex-1 basis-56 space-y-1">
          <p v-if="footerHint" class="text-[0.8125rem] leading-snug text-ink-secondary">{{ footerHint }}</p>
          <div class="flex flex-wrap gap-x-4 gap-y-1">
            <button
              v-if="can('cancel')"
              type="button"
              class="text-sm font-medium text-ink-secondary underline underline-offset-2 hover:text-brand"
              @click="askConfirm('cancel')"
            >
              Отменить заявку
            </button>
            <button
              type="button"
              class="text-sm font-medium text-ink-secondary underline underline-offset-2 hover:text-brand"
              @click="emit('ask', card.id)"
            >
              Вопрос поддержке
            </button>
          </div>
        </div>

        <div class="flex flex-wrap gap-2.5 max-sm:w-full max-sm:*:flex-1">
          <BaseButton v-if="status === 'draft' && can('edit')" @click="continueDraft">Продолжить заполнение</BaseButton>

          <template v-else-if="(status === 'approved' || status === 'counter_offer') && (can('accept_offer') || can('decline_offer'))">
            <BaseButton v-if="can('decline_offer')" variant="secondary" :disabled="Boolean(busy)" @click="askConfirm('decline')">Отказаться</BaseButton>
            <BaseButton v-if="can('accept_offer')" :loading="busy === 'accept'" :disabled="Boolean(busy)" @click="application.accept">
              Принять предложение
              <ArrowRight class="size-4" aria-hidden="true" />
            </BaseButton>
          </template>

          <BaseButton
            v-else-if="unsignedContract && can('sign')"
            type="submit"
            :form="SIGN_FORM_ID"
            :loading="busy === 'sign'"
            :disabled="Boolean(busy)"
          >
            <PenLine class="size-4" aria-hidden="true" />
            Подписать договор
          </BaseButton>

          <BaseButton v-else variant="secondary" @click="emit('close')">{{ status === 'issued' ? 'Готово' : 'Закрыть' }}</BaseButton>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Новая вкладка въезжает со стороны, куда шагнули, старая исчезает сразу — две панели вместе не видны */
.tab-panel-enter-active {
  transition:
    opacity 0.26s ease,
    transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.tab-panel-enter-from {
  opacity: 0;
  transform: translateX(var(--tab-shift, 1rem));
}
.tab-indicator {
  transition:
    transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1),
    width 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}
@media (prefers-reduced-motion: reduce) {
  .tab-panel-enter-active,
  .tab-indicator {
    transition: none;
  }
}
</style>
