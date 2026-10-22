<script setup lang="ts">
import { AlertCircle, CircleCheckBig, Download, Loader, Radio } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { CLIENT_STATUS_META, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL, PURPOSE_LABEL, type ProductCatalog } from '@/entities/credit-product'
import { liveFeed } from '@/entities/notification'
import type { LoanPurpose } from '@/shared/api'
import { formatDateTime, formatMoney, formatTerm } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, TextField } from '@/shared/ui'

import { useApplicationCard } from '../model/useApplicationCard'
import DecisionPanel from './DecisionPanel.vue'
import InfoRequestPanel from './InfoRequestPanel.vue'
import OfferPanel from './OfferPanel.vue'
import SignPanel from './SignPanel.vue'

/**
 * Заявка глазами клиента: где она, что решил банк и что нужно сделать сейчас.
 * Действия — только те, что разрешил бэкенд (available_actions), статус обновляется сам.
 */
const props = defineProps<{ applicationId: string; products: ProductCatalog | null }>()

const emit = defineEmits<{
  /** Черновик: вернуться в мастер с компанией и условиями */
  continueDraft: [draft: { productCode: string; organizationId: string; amount: number; termMonths: number; purpose?: LoanPurpose }]
  /** Оформить другой продукт — например, тот, что посоветовал банк */
  applyProduct: [code: string]
}>()

const application = useApplicationCard(() => props.applicationId)
const { card, details, loading, error, busy, actionError, uploadErrors, signature, infoDocuments, can } = application

const status = computed(() => card.value?.client_status ?? null)
const meta = computed(() => (status.value ? CLIENT_STATUS_META[status.value] : null))
const inProgress = computed(() => status.value === 'submitted' || status.value === 'checking' || status.value === 'scoring')
/** Ручное рассмотрение: этап процесса «Заявка у специалиста» */
const atSpecialist = computed(() => card.value?.client_stage?.toLowerCase().includes('специалист') ?? false)

const productTitle = (code: string) => props.products?.find((product) => product.code === code)?.title ?? null

const requestRows = computed(() => {
  const value = card.value
  if (!value) return []
  const request = value.request
  return [
    {
      label: 'Компания',
      value: value.organization ? [value.organization.name, value.organization.inn && `ИНН ${value.organization.inn}`].filter(Boolean).join(' · ') : '—',
    },
    { label: 'Сумма', value: request?.amount ? formatMoney(Number(request.amount)) : '—' },
    { label: 'Срок', value: request?.term_months ? formatTerm(request.term_months) : '—' },
    { label: 'Цель', value: request?.purpose ? (PURPOSE_LABEL[request.purpose as LoanPurpose] ?? request.purpose) : '—' },
    ...(request?.purpose_comment ? [{ label: 'Комментарий', value: request.purpose_comment }] : []),
    ...(value.collateral
      ? [
          {
            label: 'Залог',
            value: `${COLLATERAL_TYPE_LABEL[value.collateral.type] ?? value.collateral.type}, ${formatMoney(Number(value.collateral.declared_value))}`,
          },
        ]
      : []),
    ...(value.submitted_at ? [{ label: 'Отправлена', value: formatDateTime(value.submitted_at) }] : []),
  ]
})

const uploadedDocuments = computed(() => card.value?.documents.filter((document) => document.status !== 'pending_upload') ?? [])

const cancelling = ref(false)
const cancelReason = ref('')

async function confirmCancel() {
  if (await application.cancel(cancelReason.value)) cancelling.value = false
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
</script>

<template>
  <AsyncState :loading="loading && !card" :error="card ? null : error" @retry="application.reload">
    <div v-if="card && meta" class="space-y-6">
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm text-ink-secondary">Заявка № {{ card.number }}</p>
          <p class="mt-1 text-lg font-bold text-ink">{{ card.product.name ?? card.product.code }}</p>
          <p v-if="card.client_stage" class="mt-0.5 text-sm text-ink-secondary">{{ card.client_stage }}</p>
        </div>
        <div class="flex flex-col items-end gap-2">
          <BaseBadge :tone="meta.tone">{{ meta.label }}</BaseBadge>
          <span
            v-if="liveFeed.state.connected"
            class="flex items-center gap-1.5 text-xs text-ink-secondary"
            title="Статус обновляется сам, перезагружать страницу не нужно"
          >
            <Radio class="size-3.5 text-success" aria-hidden="true" />
            Обновляется сам
          </span>
        </div>
      </header>

      <!-- Что происходит сейчас и что нужно от клиента -->
      <section v-if="status === 'draft'" class="rounded-2xl bg-surface-soft p-5">
        <p class="text-sm text-ink">Заявка ещё не отправлена в банк. Всё, что вы заполнили, сохранено.</p>
        <BaseButton v-if="can('edit')" class="mt-4" @click="continueDraft">Продолжить заполнение</BaseButton>
      </section>

      <section v-else-if="inProgress" class="flex items-start gap-3 rounded-2xl bg-info-soft p-5">
        <Loader class="mt-0.5 size-5 shrink-0 animate-spin text-info" aria-hidden="true" />
        <div>
          <p class="text-sm font-semibold text-ink">Банк рассматривает заявку</p>
          <p v-if="atSpecialist" class="mt-1 text-sm text-ink-secondary">
            Заявку смотрит специалист банка — обычно в течение рабочего дня. Если понадобятся документы, запрос придёт
            сюда, статус обновится сам.
          </p>
          <p v-else class="mt-1 text-sm text-ink-secondary">
            Проверяем данные в ЕГРЮЛ, ФНС и бюро кредитных историй, затем оцениваем риск. Обычно это занимает несколько
            минут — статус здесь обновится сам.
          </p>
        </div>
      </section>

      <InfoRequestPanel
        v-else-if="status === 'info_requested' && card.info_request"
        :request="card.info_request"
        :uploaded="infoDocuments"
        :upload-errors="uploadErrors"
        :can-upload="can('upload_document')"
        :can-answer="can('answer_info_request')"
        :busy="busy"
        @upload="application.upload"
        @answer="application.answer"
      />

      <template v-else-if="(status === 'approved' || status === 'counter_offer') && card.offer">
        <DecisionPanel
          v-if="card.decision && status === 'counter_offer'"
          :decision="card.decision"
          :alternative-title="card.decision.alternative_product_code ? productTitle(card.decision.alternative_product_code) : null"
          tone="neutral"
          @apply-product="(code) => emit('applyProduct', code)"
        />
        <OfferPanel
          :offer="card.offer"
          :request="card.request"
          :can-accept="can('accept_offer')"
          :can-decline="can('decline_offer')"
          :busy="busy"
          @accept="application.accept"
          @decline="application.decline"
        />
      </template>

      <SignPanel v-else-if="status === 'signing'" :offer="card.offer" :can-sign="can('sign')" :busy="busy" @sign="application.sign" />

      <section v-else-if="status === 'issued'" class="rounded-2xl bg-success-soft p-5">
        <p class="flex items-center gap-2 text-base font-bold text-ink">
          <CircleCheckBig class="size-5 text-success" aria-hidden="true" />
          Договор подписан, кредит выдан
        </p>
        <dl class="mt-3 space-y-1 text-sm text-ink">
          <div v-if="signature" class="flex flex-wrap gap-x-2">
            <dt class="text-ink-secondary">Документ в ЭДО:</dt>
            <dd>{{ signature.edo_document_id }} · {{ formatDateTime(signature.signed_at) }}</dd>
          </div>
          <div v-if="details?.disbursement" class="flex flex-wrap gap-x-2">
            <dt class="text-ink-secondary">Выдача:</dt>
            <dd>№ {{ details.disbursement.reference }} · {{ formatDateTime(details.disbursement.disbursed_at) }}</dd>
          </div>
        </dl>
        <p class="mt-3 text-xs text-ink-secondary">
          Подписание и выдача смоделированы (моки ЭДО и АБС): реальных подписей и денежных операций нет.
        </p>
      </section>

      <DecisionPanel
        v-else-if="status === 'rejected' && card.decision"
        :decision="card.decision"
        :alternative-title="card.decision.alternative_product_code ? productTitle(card.decision.alternative_product_code) : null"
        tone="negative"
        @apply-product="(code) => emit('applyProduct', code)"
      />

      <section v-else class="rounded-2xl bg-surface-soft p-5 text-sm text-ink">
        <template v-if="status === 'declined'">Вы отказались от предложения банка. Новую заявку можно подать в любой момент.</template>
        <template v-else-if="status === 'expired'">Срок предложения истёк. Подайте заявку заново — условия рассчитаем ещё раз.</template>
        <template v-else>Заявка отменена.</template>
      </section>

      <p v-if="actionError" class="flex items-start gap-2 rounded-2xl bg-brand-soft p-4 text-sm text-brand" role="alert">
        <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ actionError }}
      </p>

      <p v-if="card.degraded.length" class="rounded-xl bg-surface-soft p-3 text-xs text-ink-secondary">
        Часть сведений сейчас недоступна, показываем то, что есть.
      </p>

      <section>
        <h3 class="text-base font-bold text-ink">Условия заявки</h3>
        <dl class="mt-3 divide-y divide-line rounded-2xl bg-surface-soft px-4">
          <div v-for="row in requestRows" :key="row.label" class="flex justify-between gap-4 py-3 text-sm">
            <dt class="text-ink-secondary">{{ row.label }}</dt>
            <dd class="text-right font-semibold text-ink">{{ row.value }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="card.timeline.length">
        <h3 class="text-base font-bold text-ink">Ход рассмотрения</h3>
        <ol class="relative mt-3 space-y-4 border-l border-line pl-5">
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
      </section>

      <section v-if="uploadedDocuments.length">
        <h3 class="text-base font-bold text-ink">Документы</h3>
        <ul class="mt-3 space-y-2">
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
      </section>

      <section v-if="can('cancel')" class="border-t border-line pt-5">
        <div v-if="cancelling" class="space-y-3">
          <TextField v-model="cancelReason" label="Почему отменяете" placeholder="Необязательно" :maxlength="500" />
          <div class="flex flex-wrap gap-3">
            <BaseButton variant="secondary" :loading="busy === 'cancel'" @click="confirmCancel">Отменить заявку</BaseButton>
            <BaseButton variant="ghost" :disabled="busy === 'cancel'" @click="cancelling = false">Не отменять</BaseButton>
          </div>
        </div>
        <button v-else type="button" class="text-sm font-medium text-ink-secondary underline underline-offset-2 hover:text-brand" @click="cancelling = true">
          Отменить заявку
        </button>
      </section>
    </div>
  </AsyncState>
</template>
