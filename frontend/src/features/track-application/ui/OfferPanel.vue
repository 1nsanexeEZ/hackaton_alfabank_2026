<script setup lang="ts">
import { computed, ref } from 'vue'

import { REPAYMENT_LABEL } from '@/entities/credit-product'
import type { LoanRequestDto, OfferDto, Repayment } from '@/shared/api'
import { formatDate, formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/** Предложение банка: условия, срок действия, принять или отказаться */
const props = defineProps<{
  offer: OfferDto
  request: LoanRequestDto | null
  canAccept: boolean
  canDecline: boolean
  busy: string | null
}>()

const emit = defineEmits<{ accept: []; decline: [reason: string] }>()

const declining = ref(false)
const reason = ref('')

const isCounter = computed(() => props.offer.kind === 'counter')

/** Чем контрпредложение отличается от запроса — показываем рядом, чтобы было видно разницу */
const changes = computed(() => {
  const request = props.request
  if (!isCounter.value || !request) return []
  const list: string[] = []
  if (request.amount !== null && Number(request.amount) !== Number(props.offer.amount)) {
    list.push(`Сумма: просили ${formatMoney(Number(request.amount))}, банк предлагает ${formatMoney(Number(props.offer.amount))}`)
  }
  if (request.term_months !== null && request.term_months !== props.offer.term_months) {
    list.push(`Срок: просили ${formatTerm(request.term_months)}, банк предлагает ${formatTerm(props.offer.term_months)}`)
  }
  return list
})

const rows = computed(() => [
  { label: 'Сумма', value: formatMoney(Number(props.offer.amount)) },
  { label: 'Срок', value: formatTerm(props.offer.term_months) },
  { label: 'Ставка', value: formatPercent(Number(props.offer.rate)) },
  { label: 'Платёж в месяц', value: formatMoney(Number(props.offer.monthly_payment)) },
  { label: 'Погашение', value: REPAYMENT_LABEL[props.offer.schedule_type as Repayment] ?? props.offer.schedule_type },
])
</script>

<template>
  <section class="rounded-2xl bg-surface-soft p-5">
    <h3 class="text-base font-bold text-ink">
      {{ isCounter ? 'Банк предлагает другие условия' : 'Банк одобрил заявку' }}
    </h3>
    <p class="mt-1 text-sm text-ink-secondary">
      Предложение действует до {{ formatDate(offer.expires_at) }} — примите его, и останется подписать договор.
    </p>

    <ul v-if="changes.length" class="mt-3 space-y-1 text-sm text-ink">
      <li v-for="change in changes" :key="change">{{ change }}</li>
    </ul>

    <dl class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
      <div v-for="row in rows" :key="row.label" class="rounded-xl bg-white p-3">
        <dt class="text-xs text-ink-secondary">{{ row.label }}</dt>
        <dd class="mt-1 font-semibold text-ink">{{ row.value }}</dd>
      </div>
    </dl>

    <div v-if="offer.conditions.length" class="mt-4">
      <p class="text-sm font-semibold text-ink">Условия</p>
      <ul class="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
        <li v-for="condition in offer.conditions" :key="condition">{{ condition }}</li>
      </ul>
    </div>

    <div v-if="declining" class="mt-5 space-y-3">
      <TextField v-model="reason" label="Почему отказываетесь" placeholder="Необязательно" :maxlength="500" />
      <div class="flex flex-wrap gap-3">
        <BaseButton variant="secondary" :loading="busy === 'decline'" @click="emit('decline', reason)">
          Отказаться от предложения
        </BaseButton>
        <BaseButton variant="ghost" :disabled="busy === 'decline'" @click="declining = false">Не отказываться</BaseButton>
      </div>
    </div>
    <div v-else-if="canAccept || canDecline" class="mt-5 flex flex-wrap gap-3">
      <BaseButton v-if="canAccept" :loading="busy === 'accept'" :disabled="Boolean(busy)" @click="emit('accept')">
        Принять предложение
      </BaseButton>
      <BaseButton v-if="canDecline" variant="ghost" :disabled="Boolean(busy)" @click="declining = true">
        Отказаться
      </BaseButton>
    </div>
  </section>
</template>
