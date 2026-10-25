<script setup lang="ts">
import { CircleCheck, CircleMinus, Download, FileText } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { beneficialOwnersLine, beneficiaryLine, collateralOwnerLine, DOCUMENT_TITLE } from '@/entities/application'
import { COLLATERAL_TYPE_LABEL, PURPOSE_LABEL } from '@/entities/credit-product'
import { backofficeApi, type LoanPurpose, type UnderwriterCardDto } from '@/shared/api'
import { errorMessage, formatDate, formatDateTime, formatMoney, formatMoneyShort, formatPercent, formatTerm, saveFile } from '@/shared/lib'
import { BaseBadge, BaseButton, PanelCard } from '@/shared/ui'

import { share } from '../model/figures'
import FactRow from './FactRow.vue'
import StatTile from './StatTile.vue'

/**
 * Что просит клиент: сумма, продукт и цель плитками, запрос относительно лимита авторешения, ответы
 * по 115-ФЗ, согласия и документы. Номер заявки — в заголовке страницы.
 */
const props = defineProps<{ card: UnderwriterCardDto; productTitle: string }>()

const application = computed(() => props.card.application)
const money = (value: string | number) => formatMoney(Number(value))

/** Запрос в лимите авторешения: до лимита решает движок, сверху — специалист */
const autoLimit = computed(() => {
  const request = application.value.request
  const limit = Number(application.value.product_terms.auto_decision_limit)
  if (!request || !limit) return null
  const part = Number(request.amount) / limit
  return { limit, part, width: share(Number(request.amount), limit), within: part <= 1 }
})

const terms = computed(() => {
  const value = application.value.product_terms
  return `Продукт: ${formatMoneyShort(Number(value.amount_min))} – ${formatMoneyShort(Number(value.amount_max))} на ${value.term_min_months}–${value.term_max_months} мес. · ставка ${formatPercent(Number(value.rate_base))} – ${formatPercent(Number(value.rate_max))}`
})

/** Бенефициары со слов клиента расходятся с ЕГРЮЛ — подробности в проверке по 115-ФЗ */
const ownersMismatch = computed(() => Boolean(props.card.enrichment?.aml?.owner_discrepancies?.length))

/**
 * Согласия заявки: когда даны и откуда — галочка в черновике или из профиля. Согласие на решение только
 * автоматикой (ст. 16 152-ФЗ) важно у ИП: без него отказ и встречное предложение принимает человек.
 */
const consents = computed(() => {
  const value = application.value.consents
  if (!value) return []
  const given = (at: string | null | undefined, source: string | null | undefined) =>
    at ? `${source === 'profile' ? 'из профиля' : 'в заявке'}, ${formatDate(at)}` : null
  const list = [
    { title: 'Обработка ПДн', value: given(value.personal_data_at, value.personal_data_source) },
    { title: 'БКИ компании', value: given(value.credit_bureau_at, value.credit_bureau_source) },
  ]
  if (application.value.org_snapshot?.legal_form === 'IE') {
    list.push({
      title: 'Решение автоматикой',
      value: value.automated_decision_at ? `дано, ${formatDate(value.automated_decision_at)}` : null,
    })
  }
  return list
})

const documents = computed(() => application.value.documents.filter((item) => item.status !== 'pending_upload'))
const sizeOf = (bytes: number | undefined) => (bytes ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : null)

async function download(documentId: string) {
  const { url } = await backofficeApi.downloadDocument(application.value.id, documentId)
  window.open(url, '_blank', 'noopener')
}

/** Договор в PDF — после подписи клиента: итоговый с подписью банка или, пока его нет, последний готовый */
const contractSigned = computed(() => application.value.status === 'signed' || application.value.status === 'disbursed')
const contractBusy = ref(false)
const contractError = ref<string | null>(null)

async function downloadContract() {
  contractBusy.value = true
  contractError.value = null
  try {
    const file = await backofficeApi.contractDocument(application.value.id)
    saveFile(file.blob, file.filename ?? `Договор ${application.value.number}.pdf`)
  } catch (caught) {
    contractError.value = errorMessage(caught)
  } finally {
    contractBusy.value = false
  }
}
</script>

<template>
  <PanelCard
    title="Заявка"
    :description="application.submitted_at ? `Что просит клиент · подана ${formatDateTime(application.submitted_at)}` : 'Что просит клиент'"
  >
    <div class="grid grid-cols-2 gap-2.5 @xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <div class="col-span-2 min-w-0 rounded-xl bg-surface-soft px-3.5 py-3 @xl:col-span-1">
        <p class="text-xs text-ink-secondary">Запрос</p>
        <p class="mt-0.5 text-[1.75rem] leading-tight font-extrabold tracking-tight text-ink tabular-nums">
          {{ application.request ? money(application.request.amount) : '—' }}
        </p>
        <p v-if="application.request" class="mt-0.5 text-xs text-ink-secondary">на {{ formatTerm(application.request.term_months) }}</p>
      </div>
      <StatTile label="Продукт" :hint="application.collateral ? 'с залогом' : 'без залога'">
        <span class="text-[0.9375rem]">{{ productTitle }}</span>
      </StatTile>
      <StatTile
        label="Цель"
        :hint="application.request?.purpose_comment ? `комментарий: «${application.request.purpose_comment}»` : null"
      >
        <span class="text-[0.9375rem]">
          {{ application.request ? (PURPOSE_LABEL[application.request.purpose as LoanPurpose] ?? application.request.purpose) : '—' }}
        </span>
      </StatTile>
    </div>

    <div v-if="autoLimit" class="mt-2.5 rounded-xl p-4 ring-1 ring-line">
      <div class="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span>
          <span class="font-semibold text-ink">Лимит авторешения</span>
          <span class="text-ink-secondary"> — {{ money(autoLimit.limit) }}</span>
        </span>
        <span class="font-semibold" :class="autoLimit.within ? 'text-success' : 'text-warning'">
          {{ autoLimit.within ? `запрос — ${Math.round(autoLimit.part * 100)}% лимита` : 'запрос выше лимита — решает специалист' }}
        </span>
      </div>
      <div
        class="mt-2.5 h-2.5 overflow-hidden rounded-full bg-surface-strong"
        role="img"
        :aria-label="`Запрос — ${Math.round(autoLimit.part * 100)}% лимита авторешения`"
      >
        <div class="h-full rounded-full" :class="autoLimit.within ? 'bg-night' : 'bg-warning'" :style="{ width: `${autoLimit.width}%` }" />
      </div>
      <p class="mt-2 text-xs text-ink-secondary">{{ terms }}</p>
    </div>

    <dl v-if="application.collateral" class="mt-4">
      <FactRow
        label="Залог"
        :hint="`${application.collateral.description} · собственник: ${collateralOwnerLine(application.collateral)}`"
      >
        {{ COLLATERAL_TYPE_LABEL[application.collateral.type] ?? application.collateral.type }}, {{ money(application.collateral.declared_value) }}
      </FactRow>
    </dl>

    <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Клиент о себе · 115-ФЗ</h3>
    <dl class="mt-1">
      <!-- Ответ клиента о третьем лице: по нему выгодоприобретатель проверяется вместе с остальными -->
      <FactRow label="Выгодоприобретатель" :tone="application.beneficiary?.acts_for_third_party ? 'warning' : 'default'">
        {{ application.beneficiary ? beneficiaryLine(application.beneficiary) : 'Клиент не ответил' }}
      </FactRow>
      <!-- Бенефициары со слов клиента (policy_v9): сверяются с ЕГРЮЛ и проверяются по перечням -->
      <FactRow label="Бенефициары">
        {{ application.beneficial_owners ? beneficialOwnersLine(application.beneficial_owners) : 'Клиент не ответил' }}
        <span v-if="ownersMismatch" class="mt-1 block"><BaseBadge tone="warning">Расходится с ЕГРЮЛ — см. 115-ФЗ</BaseBadge></span>
      </FactRow>
    </dl>

    <template v-if="consents.length">
      <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Согласия</h3>
      <ul class="mt-2 flex flex-wrap gap-2">
        <li
          v-for="item in consents"
          :key="item.title"
          class="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold"
          :class="item.value ? 'bg-success-soft text-success' : 'bg-surface text-ink-secondary'"
        >
          <CircleCheck v-if="item.value" class="size-3.5" aria-hidden="true" />
          <CircleMinus v-else class="size-3.5" aria-hidden="true" />
          {{ item.title }} · {{ item.value ?? 'нет' }}
        </li>
      </ul>
    </template>

    <template v-if="documents.length">
      <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Документы · {{ documents.length }}</h3>
      <ul class="mt-2 space-y-1.5">
        <li v-for="document in documents" :key="document.id" class="flex items-center gap-3 rounded-xl bg-surface-soft px-3 py-2.5 text-sm">
          <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white text-ink-secondary" aria-hidden="true">
            <FileText class="size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block font-semibold text-ink">{{ DOCUMENT_TITLE[document.type] ?? document.type }}</span>
            <span class="block truncate text-xs text-ink-secondary">
              {{ [document.filename, sizeOf(document.size_bytes), document.uploaded_at && `загружен ${formatDateTime(document.uploaded_at)}`].filter(Boolean).join(' · ') }}
            </span>
          </span>
          <button
            type="button"
            class="flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-white hover:text-ink"
            :aria-label="`Скачать ${document.filename}`"
            @click="download(document.id)"
          >
            <Download class="size-4" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </template>

    <div v-if="contractSigned" class="mt-5 flex flex-wrap items-center gap-3">
      <BaseButton size="s" variant="secondary" :loading="contractBusy" @click="downloadContract">
        <FileText class="size-4" aria-hidden="true" />
        Договор (PDF)
      </BaseButton>
      <p v-if="contractError" class="text-sm text-brand" role="alert">{{ contractError }}</p>
    </div>
  </PanelCard>
</template>
