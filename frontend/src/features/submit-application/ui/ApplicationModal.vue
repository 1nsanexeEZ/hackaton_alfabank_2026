<script setup lang="ts">
import { AlertCircle, ArrowLeft, ArrowRight, Building2 } from 'lucide-vue-next'
import { computed, watch } from 'vue'

import type { ProductCatalog } from '@/entities/credit-product'
import { AsyncState, BaseButton, BaseModal } from '@/shared/ui'

import { useApplicationWizard } from '../model/useApplicationWizard'
import ApplicationSubmitted from './ApplicationSubmitted.vue'
import StepConsents from './StepConsents.vue'
import StepDetails from './StepDetails.vue'
import StepTerms from './StepTerms.vue'

/**
 * Заявка на кредит в модальном окне. Открывать только для вошедшего пользователя:
 * все ручки заявки требуют токен. Состояние мастера живёт, пока смонтирован компонент.
 */
const props = defineProps<{ products: ProductCatalog }>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ switchAccount: [] }>()

const wizard = useApplicationWizard(() => props.products)
const {
  step,
  steps,
  organizations,
  organizationsLoading,
  organizationsError,
  application,
  product,
  busy,
  error,
  violations,
  ineligibleReason,
  startupBlock,
} = wizard

watch(open, (isOpen) => isOpen && wizard.prepare(), { immediate: true })

const STEP_TITLE = { terms: 'Условия', details: 'Анкета и документы', consents: 'Согласия и отправка' } as const

const hasCompanies = computed(() => (organizations.value?.length ?? 0) > 0)
const stepIndex = computed(() => steps.value.indexOf(step.value as (typeof steps.value)[number]))
const description = computed(() =>
  step.value === 'done' || !hasCompanies.value
    ? undefined
    : `Шаг ${stepIndex.value + 1} из ${steps.value.length}: ${STEP_TITLE[step.value as keyof typeof STEP_TITLE]}`,
)

function close() {
  open.value = false
}
</script>

<template>
  <BaseModal v-model:open="open" title="Заявка на кредит" :description="description" wide>
    <AsyncState
      :loading="organizationsLoading || (!organizations && !organizationsError)"
      :error="organizationsError"
      @retry="wizard.loadOrganizations"
    >
      <div v-if="!hasCompanies" class="flex flex-col items-center gap-3 px-4 py-10 text-center">
        <span class="flex size-12 items-center justify-center rounded-full bg-surface text-ink-secondary">
          <Building2 class="size-6" aria-hidden="true" />
        </span>
        <p class="font-semibold text-ink">У этой учётной записи нет компаний</p>
        <p class="max-w-sm text-sm text-ink-secondary">
          Заявку подаёт участник компании: собственник, руководитель или бухгалтер. Войдите учётной записью
          предпринимателя.
        </p>
        <BaseButton variant="secondary" @click="emit('switchAccount')">Войти другой учётной записью</BaseButton>
      </div>

      <template v-else>
        <ol v-if="step !== 'done'" class="mb-6 flex gap-2" aria-label="Шаги заявки">
          <li
            v-for="(item, index) in steps"
            :key="item"
            class="h-1.5 flex-1 rounded-full transition-colors"
            :class="index <= stepIndex ? 'bg-brand' : 'bg-surface-strong'"
            :aria-current="item === step ? 'step' : undefined"
          >
            <span class="sr-only">{{ STEP_TITLE[item] }}</span>
          </li>
        </ol>

        <StepTerms v-if="step === 'terms'" :wizard="wizard" :products="products" />
        <StepDetails v-else-if="step === 'details'" :wizard="wizard" />
        <StepConsents v-else-if="step === 'consents'" :wizard="wizard" />
        <ApplicationSubmitted
          v-else-if="step === 'done' && application"
          :application="application"
          :product-title="product.title"
        />

        <div
          v-if="error || violations.length"
          class="mt-6 rounded-2xl bg-brand-soft p-4 text-sm text-brand"
          role="alert"
        >
          <p class="flex items-center gap-2 font-semibold">
            <AlertCircle class="size-4 shrink-0" aria-hidden="true" />
            {{ error ?? 'Чтобы отправить заявку, исправьте:' }}
          </p>
          <ul v-if="violations.length" class="mt-2 space-y-1.5">
            <li v-for="(item, index) in violations" :key="index" class="flex flex-wrap items-baseline justify-between gap-2">
              <span>{{ item.message }}</span>
              <button
                v-if="item.step !== step"
                type="button"
                class="font-medium underline underline-offset-2"
                @click="wizard.goTo(item.step)"
              >
                Исправить
              </button>
            </li>
          </ul>
        </div>
      </template>
    </AsyncState>

    <template #footer>
      <template v-if="!hasCompanies || step === 'done'">
        <BaseButton @click="close">{{ step === 'done' ? 'Готово' : 'Закрыть' }}</BaseButton>
      </template>
      <template v-else>
        <BaseButton v-if="step === 'terms'" variant="ghost" @click="close">Отмена</BaseButton>
        <BaseButton v-else variant="ghost" :disabled="busy" @click="wizard.back">
          <ArrowLeft class="size-4" aria-hidden="true" />
          Назад
        </BaseButton>
        <BaseButton v-if="step === 'terms'" :loading="busy" :disabled="Boolean(ineligibleReason || startupBlock)" @click="wizard.submitTerms">
          Далее
          <ArrowRight class="size-4" aria-hidden="true" />
        </BaseButton>
        <BaseButton v-else-if="step === 'details'" :loading="busy" @click="wizard.submitDetails">
          Далее
          <ArrowRight class="size-4" aria-hidden="true" />
        </BaseButton>
        <BaseButton v-else :loading="busy" @click="wizard.submit">Отправить заявку</BaseButton>
      </template>
    </template>
  </BaseModal>
</template>
