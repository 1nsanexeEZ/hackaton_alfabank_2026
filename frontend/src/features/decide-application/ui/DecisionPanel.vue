<script setup lang="ts">
import { BadgeCheck, Banknote, FileSignature, Play, RefreshCw, UserCheck } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { DECISION_OUTCOME_META, RISK_RATE_PREMIUM } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS, findProduct } from '@/entities/credit-product'
import { shortName, useSession } from '@/entities/session'
import { creditApi, type ApplicationDetails, type ApplicationTransition, type DecisionOutcome } from '@/shared/api'
import { errorMessage, formatDateTime, formatMoney, formatPercent, formatTerm, onlyDigits } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/**
 * Действия аналитика по заявке: запустить проверки, взять в работу, вынести решение,
 * отправить на подписание и отметить выдачу. Набор действий зависит от статуса.
 */
const props = defineProps<{ application: ApplicationDetails }>()
const emit = defineEmits<{ updated: [application: ApplicationDetails] }>()

const { can, me } = useSession()
const canUpdate = computed(() => can('requests.update'))

const pending = ref<string | null>(null)
const error = ref<string | null>(null)

const product = computed(() => findProduct(DEMO_CREDIT_PRODUCTS, props.application.productId))
const isReviewable = computed(() => ['scoring', 'info_requested'].includes(props.application.status))
const needsChecks = computed(() => ['submitted', 'checking'].includes(props.application.status))

const OUTCOMES = Object.keys(DECISION_OUTCOME_META) as DecisionOutcome[]

const form = reactive({ outcome: 'approved' as DecisionOutcome, amount: '', term: '', rate: '', comment: '' })
const formErrors = reactive<{ amount?: string; term?: string; rate?: string; comment?: string }>({})

const suggestedRate = computed(() => {
  const risk = props.application.score?.riskClass ?? 'C'
  return product.value.rateFrom + RISK_RATE_PREMIUM[risk]
})

/** Предзаполняем форму рекомендацией скоринга — аналитику остаётся проверить и подтвердить */
function prefill(outcome = props.application.score?.recommendation ?? 'approved') {
  const score = props.application.score
  form.outcome = outcome
  const amount = outcome === 'counter_offer' && score?.suggestedAmount ? score.suggestedAmount : props.application.amount
  form.amount = amount.toLocaleString('ru-RU')
  form.term = String(props.application.termMonths)
  form.rate = String(suggestedRate.value).replace('.', ',')
  form.comment =
    outcome === 'rejected'
      ? (score?.stopFactors[0] ?? '')
      : outcome === 'info_requested'
        ? (score?.missingData[0] ?? '')
        : ''
}

watch(() => props.application.id, () => prefill(), { immediate: true })
watch(
  () => props.application.score?.calculatedAt,
  () => prefill(),
)

function selectOutcome(outcome: DecisionOutcome) {
  prefill(outcome)
}

function validate(): boolean {
  const amount = Number(onlyDigits(form.amount))
  const term = Number(onlyDigits(form.term))
  const rate = Number(form.rate.replace(',', '.'))
  const needsTerms = form.outcome === 'approved' || form.outcome === 'counter_offer'
  formErrors.amount = needsTerms && (amount < product.value.amount.min || amount > product.value.amount.max)
    ? `От ${formatMoney(product.value.amount.min)} до ${formatMoney(product.value.amount.max)}`
    : undefined
  formErrors.term = needsTerms && (term < product.value.termMonths.min || term > product.value.termMonths.max)
    ? `От ${product.value.termMonths.min} до ${product.value.termMonths.max} мес.`
    : undefined
  formErrors.rate = needsTerms && !(rate > 0 && rate < 100) ? 'Укажите ставку, например 24,5' : undefined
  formErrors.comment = form.outcome !== 'approved' && !form.comment.trim() ? 'Объясните решение клиенту' : undefined
  return !formErrors.amount && !formErrors.term && !formErrors.rate && !formErrors.comment
}

async function run(action: string, request: () => Promise<ApplicationDetails>) {
  pending.value = action
  error.value = null
  try {
    emit('updated', await request())
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = null
  }
}

const assign = () => run('assign', () => creditApi.assign(props.application.id))
const rescore = () => run('rescore', () => creditApi.rescore(props.application.id))
const transition = (step: ApplicationTransition) =>
  run('transition', () => creditApi.transition(props.application.id, step))

function submitDecision() {
  if (!validate()) return
  void run('decide', () =>
    creditApi.decide(props.application.id, {
      outcome: form.outcome,
      amount: Number(onlyDigits(form.amount)),
      termMonths: Number(onlyDigits(form.term)),
      rate: Number(form.rate.replace(',', '.')),
      comment: form.comment.trim(),
    }),
  )
}

// Ответственного мок записывает коротким именем сотрудника — так же сравниваем
const isMine = computed(() => props.application.assignee === shortName(me.value))
</script>

<template>
  <div class="space-y-4">
    <p v-if="!canUpdate" class="rounded-xl bg-surface-soft p-4 text-sm text-ink-secondary">
      У вас доступ только на просмотр: решения принимают кредитные аналитики.
    </p>

    <template v-else>
      <div v-if="!isMine && isReviewable" class="flex items-center justify-between gap-3 rounded-xl bg-surface-soft p-3 pl-4 text-sm">
        <span class="text-ink-secondary">
          {{ application.assignee ? `Ответственный: ${application.assignee}` : 'Заявку ещё никто не взял' }}
        </span>
        <BaseButton variant="secondary" size="s" :loading="pending === 'assign'" @click="assign">
          <UserCheck class="size-4" aria-hidden="true" />
          Взять себе
        </BaseButton>
      </div>

      <div v-if="needsChecks" class="rounded-xl bg-info-soft p-4">
        <p class="text-sm text-ink">
          Заявка ждёт автоматических проверок: запросим ЕГРЮЛ/ЕГРИП, ФНС, ГИР БО и Контур и посчитаем скоринг.
        </p>
        <BaseButton class="mt-3" size="s" :loading="pending === 'rescore'" @click="rescore">
          <Play class="size-4" aria-hidden="true" />
          Запустить проверки
        </BaseButton>
      </div>

      <form v-if="isReviewable" class="space-y-4" novalidate @submit.prevent="submitDecision">
        <fieldset>
          <legend class="mb-2 text-sm font-medium text-ink">Решение</legend>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="outcome in OUTCOMES"
              :key="outcome"
              type="button"
              :aria-pressed="form.outcome === outcome"
              :class="[
                'h-11 rounded-lg px-3 text-sm font-medium transition',
                form.outcome === outcome ? 'bg-night text-on-night' : 'bg-surface text-ink hover:bg-surface-strong',
              ]"
              @click="selectOutcome(outcome)"
            >
              {{ DECISION_OUTCOME_META[outcome].label }}
              <span v-if="application.score?.recommendation === outcome" class="ml-1 text-xs opacity-60">· реком.</span>
            </button>
          </div>
        </fieldset>

        <div v-if="form.outcome === 'approved' || form.outcome === 'counter_offer'" class="grid gap-3 sm:grid-cols-3">
          <TextField v-model="form.amount" label="Сумма, ₽" inputmode="numeric" dense :error="formErrors.amount" class="sm:col-span-3" />
          <TextField v-model="form.term" label="Срок, мес." inputmode="numeric" dense :error="formErrors.term" />
          <TextField
            v-model="form.rate"
            label="Ставка, %"
            inputmode="decimal"
            dense
            :error="formErrors.rate"
            :hint="`Базовая ${formatPercent(product.rateFrom)} + риск`"
            class="sm:col-span-2"
          />
        </div>

        <div>
          <label for="decision-comment" class="mb-2 block text-sm font-medium text-ink">Комментарий для клиента</label>
          <textarea
            id="decision-comment"
            v-model="form.comment"
            rows="3"
            :aria-invalid="Boolean(formErrors.comment)"
            class="w-full rounded-lg bg-surface px-4 py-3 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20"
            :class="formErrors.comment && 'bg-brand-soft ring-1 ring-brand'"
            placeholder="Например: одобрено на меньшую сумму из-за долговой нагрузки"
          />
          <p v-if="formErrors.comment" class="mt-1.5 text-sm text-brand">{{ formErrors.comment }}</p>
        </div>

        <div class="flex flex-wrap gap-2">
          <BaseButton type="submit" :loading="pending === 'decide'">
            <BadgeCheck class="size-4" aria-hidden="true" />
            Вынести решение
          </BaseButton>
          <BaseButton
            v-if="application.status === 'scoring'"
            variant="secondary"
            :loading="pending === 'rescore'"
            @click="rescore"
          >
            <RefreshCw class="size-4" aria-hidden="true" />
            Пересчитать скоринг
          </BaseButton>
        </div>
      </form>

      <div v-if="application.status === 'approved' || application.status === 'counter_offer'">
        <BaseButton :loading="pending === 'transition'" @click="transition('to_signing')">
          <FileSignature class="size-4" aria-hidden="true" />
          Отправить договор на подписание
        </BaseButton>
      </div>
      <div v-if="application.status === 'signing'">
        <BaseButton :loading="pending === 'transition'" @click="transition('issue')">
          <Banknote class="size-4" aria-hidden="true" />
          Отметить выдачу кредита
        </BaseButton>
      </div>
    </template>

    <p v-if="error" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>

    <div v-if="application.decision" class="rounded-xl bg-surface-soft p-4 text-sm">
      <p class="font-semibold text-ink">{{ DECISION_OUTCOME_META[application.decision.outcome].action }}</p>
      <p v-if="application.decision.outcome === 'approved' || application.decision.outcome === 'counter_offer'" class="mt-1 text-ink">
        {{ formatMoney(application.decision.amount) }} на {{ formatTerm(application.decision.termMonths) }} под
        {{ formatPercent(application.decision.rate) }}
      </p>
      <p v-if="application.decision.comment" class="mt-1 text-ink-secondary">{{ application.decision.comment }}</p>
      <p class="mt-2 text-xs text-ink-secondary">
        {{ application.decision.decidedBy }} · {{ formatDateTime(application.decision.decidedAt) }}
      </p>
    </div>
  </div>
</template>
