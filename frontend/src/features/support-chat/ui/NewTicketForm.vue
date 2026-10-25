<script setup lang="ts">
import { computed, reactive, ref, shallowRef, watch } from 'vue'

import { useProductCatalog } from '@/entities/credit-product'
import { clientApi, type ApplicationSummaryDto, type OrganizationSummaryDto, type SupportTicketDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, SelectField, TextField } from '@/shared/ui'

/**
 * Вопрос в поддержку (POST /support/tickets): тема и текст, по желанию — компания и заявка.
 * Из карточки заявки форма открывается с ней: заявка задаёт и компанию обращения.
 */
const props = defineProps<{ applicationId?: string | null }>()
const emit = defineEmits<{ created: [ticket: SupportTicketDto]; cancel: [] }>()

const SUBJECT_MAX = 200
const TEXT_MAX = 4000

const form = reactive({ subject: '', text: '', organizationId: '', applicationId: props.applicationId ?? '' })
const errors = reactive<{ subject?: string; text?: string }>({})
const pending = ref(false)
const error = ref<string | null>(null)

const companies = shallowRef<OrganizationSummaryDto[]>([])
const applications = shallowRef<ApplicationSummaryDto[]>([])
clientApi
  .listOrganizations()
  .then((list) => (companies.value = list.filter((item) => item.my_role !== null)))
  .catch(() => undefined)
clientApi
  .listApplications(50)
  .then((list) => {
    applications.value = list
    const preset = list.find((item) => item.id === form.applicationId)
    if (preset) form.organizationId = preset.organization_id
  })
  .catch(() => undefined)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

const companyOptions = computed(() => [
  { value: '', label: 'Не про конкретную компанию' },
  ...companies.value.map((item) => ({ value: item.id, label: item.name })),
])
/** Заявки выбранной компании; компания не выбрана — все */
const applicationOptions = computed(() => [
  { value: '', label: 'Не про заявку' },
  ...applications.value
    .filter((item) => !form.organizationId || item.organization_id === form.organizationId)
    .map((item) => ({ value: item.id, label: `${item.number} · ${productTitle(item.product_code)}` })),
])

// Сменили компанию — заявка другой компании больше не подходит
watch(
  () => form.organizationId,
  (organizationId) => {
    const chosen = applications.value.find((item) => item.id === form.applicationId)
    if (chosen && organizationId && chosen.organization_id !== organizationId) form.applicationId = ''
  },
)

async function submit() {
  errors.subject = form.subject.trim() ? undefined : 'Коротко — о чём вопрос'
  errors.text = form.text.trim() ? undefined : 'Опишите вопрос'
  if (errors.subject || errors.text) return
  pending.value = true
  error.value = null
  try {
    emit(
      'created',
      await clientApi.openSupportTicket({
        subject: form.subject.trim(),
        text: form.text.trim(),
        organization_id: form.applicationId ? null : form.organizationId || null,
        application_id: form.applicationId || null,
      }),
    )
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <form class="space-y-4" novalidate @submit.prevent="submit">
    <TextField v-model="form.subject" label="Тема" :maxlength="SUBJECT_MAX" placeholder="Например: какие документы нужны для залога" :error="errors.subject" />
    <label class="block">
      <span class="mb-2 block text-sm font-medium text-ink">Вопрос</span>
      <textarea
        v-model="form.text"
        rows="5"
        :maxlength="TEXT_MAX"
        placeholder="Опишите, что случилось или что хотите узнать"
        class="block w-full resize-y rounded-xl bg-surface px-4 py-3 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20"
        :aria-invalid="Boolean(errors.text)"
      />
      <span v-if="errors.text" class="mt-1.5 block text-sm text-brand" role="alert">{{ errors.text }}</span>
    </label>
    <div class="grid gap-3 sm:grid-cols-2">
      <SelectField v-if="companies.length" v-model="form.organizationId" label="Компания" :options="companyOptions" dense />
      <SelectField v-if="applications.length" v-model="form.applicationId" label="Заявка" :options="applicationOptions" dense />
    </div>
    <p v-if="error" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>
    <div class="flex flex-wrap justify-end gap-2">
      <BaseButton variant="secondary" @click="emit('cancel')">Отмена</BaseButton>
      <BaseButton type="submit" :loading="pending">Отправить вопрос</BaseButton>
    </div>
  </form>
</template>
