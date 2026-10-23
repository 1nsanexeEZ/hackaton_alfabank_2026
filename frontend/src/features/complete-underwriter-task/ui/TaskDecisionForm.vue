<script setup lang="ts">
import { Hand } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'

import { DOCUMENT_TITLE } from '@/entities/application'
import { useSession } from '@/entities/session'
import { TASK_STATUS_LABEL } from '@/entities/underwriting'
import { backofficeApi, type TaskDecision, type UnderwriterCardDto, type UnderwriterTaskDto } from '@/shared/api'
import { errorMessage, formatDateTime } from '@/shared/lib'
import { BaseButton, CheckboxField, SegmentedControl, TextField } from '@/shared/ui'

/**
 * Решение андеррайтера по задаче (POST /tasks/{id}/claim, /complete). Сначала задачу берут на себя,
 * потом выбирают исход. Условия по умолчанию — из решения движка и рамок продукта.
 */
const props = defineProps<{ task: UnderwriterTaskDto; card: UnderwriterCardDto }>()

const emit = defineEmits<{ claimed: []; decided: [] }>()

const { me } = useSession()

const mine = computed(() => props.task.assignee_id !== null && props.task.assignee_id === me.value?.id)
const takenByOther = computed(() => props.task.assignee_id !== null && !mine.value)
const active = computed(() => props.task.status === 'open' || props.task.status === 'in_progress')

const OUTCOMES: readonly { value: TaskDecision; label: string }[] = [
  { value: 'approve', label: 'Одобрить' },
  { value: 'counter_offer', label: 'Контрпредложение' },
  { value: 'request_info', label: 'Запросить данные' },
  { value: 'reject', label: 'Отказать' },
]

/** Документы, которые можно запросить у клиента */
const REQUESTABLE = ['bank_statement', 'financial_report', 'tax_return', 'collateral_documents', 'other'] as const

const suggested = props.card.decision?.terms
const request = props.card.application.request
const form = reactive({
  decision: 'approve' as TaskDecision,
  amount: String(Number(suggested?.amount ?? request?.amount ?? 0)),
  termMonths: String(suggested?.term_months ?? request?.term_months ?? ''),
  rate: String(Number(suggested?.rate ?? props.card.application.product_terms.rate_base)),
  conditions: (suggested?.conditions ?? []).join('\n'),
  documents: { bank_statement: true, financial_report: false, tax_return: false, collateral_documents: false, other: false } as Record<
    (typeof REQUESTABLE)[number],
    boolean
  >,
  comment: '',
})

const withTerms = computed(() => form.decision === 'approve' || form.decision === 'counter_offer')
const busy = ref<'claim' | 'complete' | null>(null)
const error = ref<string | null>(null)
const errors = ref<Record<string, string>>({})

const toNumber = (value: string) => Number(value.replace(/\s/g, '').replace(',', '.'))

async function claim() {
  busy.value = 'claim'
  error.value = null
  try {
    await backofficeApi.claim(props.task.id)
    emit('claimed')
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    busy.value = null
  }
}

async function complete() {
  const next: Record<string, string> = {}
  if (!form.comment.trim()) next.comment = 'Напишите, почему такое решение — его увидят в истории заявки'
  if (withTerms.value) {
    if (!(toNumber(form.amount) > 0)) next.amount = 'Укажите сумму'
    if (!(toNumber(form.termMonths) > 0)) next.termMonths = 'Укажите срок'
    if (!(toNumber(form.rate) > 0)) next.rate = 'Укажите ставку'
  }
  const documents = REQUESTABLE.filter((type) => form.documents[type])
  if (form.decision === 'request_info' && !documents.length) next.documents = 'Выберите, что запросить'
  errors.value = next
  if (Object.keys(next).length) return

  busy.value = 'complete'
  error.value = null
  try {
    await backofficeApi.complete(props.task.id, {
      decision: form.decision,
      amount: withTerms.value ? toNumber(form.amount) : null,
      term_months: withTerms.value ? toNumber(form.termMonths) : null,
      rate: withTerms.value ? toNumber(form.rate) : null,
      conditions: withTerms.value ? form.conditions.split('\n').map((line) => line.trim()).filter(Boolean) : [],
      requested_documents: form.decision === 'request_info' ? documents : [],
      comment: form.comment.trim(),
    })
    emit('decided')
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <p class="text-sm text-ink-secondary">
      {{ TASK_STATUS_LABEL[task.status] ?? task.status }}
      <template v-if="task.due_at"> · решить до {{ formatDateTime(task.due_at) }}</template>
    </p>

    <template v-if="active">
      <div v-if="!task.assignee_id">
        <BaseButton :loading="busy === 'claim'" @click="claim">
          <Hand class="size-4" aria-hidden="true" />
          Взять в работу
        </BaseButton>
      </div>
      <p v-else-if="takenByOther" class="rounded-xl bg-surface-soft p-3 text-sm text-ink-secondary">
        Задачу уже взял другой специалист — решение примет он.
      </p>

      <form v-else class="space-y-4" @submit.prevent="complete">
        <SegmentedControl v-model="form.decision" :options="OUTCOMES" label="Решение" />

        <div v-if="withTerms" class="grid gap-3 sm:grid-cols-3">
          <TextField v-model="form.amount" label="Сумма, ₽" inputmode="decimal" :error="errors.amount" dense />
          <TextField v-model="form.termMonths" label="Срок, мес." inputmode="numeric" :error="errors.termMonths" dense />
          <TextField v-model="form.rate" label="Ставка, %" inputmode="decimal" :error="errors.rate" dense />
        </div>
        <label v-if="withTerms" class="block">
          <span class="mb-2 block text-sm font-medium text-ink">Условия, по одному на строку</span>
          <textarea
            v-model="form.conditions"
            rows="3"
            class="w-full rounded-lg bg-surface px-3 py-2 text-sm text-ink outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
            placeholder="Например: поручительство собственника"
          />
        </label>

        <fieldset v-if="form.decision === 'request_info'" class="space-y-2">
          <legend class="mb-1 text-sm font-medium text-ink">Что запросить у клиента</legend>
          <CheckboxField v-for="type in REQUESTABLE" :key="type" v-model="form.documents[type]">
            {{ DOCUMENT_TITLE[type] ?? type }}
          </CheckboxField>
          <p v-if="errors.documents" class="text-sm text-brand">{{ errors.documents }}</p>
        </fieldset>

        <label class="block">
          <span class="mb-2 block text-sm font-medium text-ink">Комментарий</span>
          <textarea
            v-model="form.comment"
            rows="3"
            class="w-full rounded-lg bg-surface px-3 py-2 text-sm text-ink outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
            :class="errors.comment && 'ring-2 ring-brand/40'"
            placeholder="Почему такое решение"
          />
          <span v-if="errors.comment" class="mt-1 block text-sm text-brand">{{ errors.comment }}</span>
        </label>

        <BaseButton type="submit" :loading="busy === 'complete'">Вынести решение</BaseButton>
      </form>
    </template>

    <p v-if="error" class="rounded-xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ error }}</p>
  </div>
</template>
