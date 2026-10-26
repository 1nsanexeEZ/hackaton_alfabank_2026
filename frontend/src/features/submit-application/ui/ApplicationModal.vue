<script setup lang="ts">
import { AlertCircle, ArrowLeft, ArrowRight, Building2, CircleCheck } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'

import type { ProductCatalog } from '@/entities/credit-product'
import { shakeInvalid } from '@/shared/lib'
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
  missing,
  nudge,
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

/** В строке у кнопок помещается пара пунктов, остальное — «ещё N»; полный список — в подсказке */
const MISSING_SHOWN = 2
const missingShown = computed(() => missing.value.slice(0, MISSING_SHOWN))
const missingRest = computed(() => missing.value.length - missingShown.value.length)
const missingTitle = computed(() => missing.value.map((item) => item.label).join(', '))

const body = ref<HTMLElement>()
const shaking = ref(false)

/** Поле по пути: точное совпадение data-field или ближайший родитель (product_fields.loans.0.amount → product_fields.loans) */
function fieldElement(key: string): HTMLElement | null {
  const parts = key.split('.')
  while (parts.length) {
    const element = body.value?.querySelector<HTMLElement>(`[data-field="${parts.join('.')}"]`)
    if (element) return element
    parts.pop()
  }
  return null
}

/** Что трясти у пропуска: группу вариантов выбора, иначе само поле, иначе весь блок */
function shakeTarget(element: HTMLElement): HTMLElement {
  return (
    element.querySelector<HTMLElement>('[role="radiogroup"]') ??
    element.querySelector<HTMLElement>('[aria-invalid="true"]') ??
    element.querySelector<HTMLElement>('input:not([type=file]):not([type=checkbox]), textarea') ??
    element.querySelector<HTMLElement>('input[type=checkbox]')?.closest('label') ??
    element
  )
}

function goToField(key: string) {
  const element = fieldElement(key)
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  element.querySelector<HTMLElement>('input:not([type=file]), textarea, button')?.focus({ preventScroll: true })
  shakeInvalid([shakeTarget(element)])
}

// Нажали «Далее» с пропусками: список у кнопок вздрагивает, каждый пропуск вздрагивает красным, форма — к первому
watch(nudge, async () => {
  shaking.value = false
  await nextTick()
  shaking.value = true
  const first = missing.value[0]
  if (!first) return
  goToField(first.key)
  const rest = missing.value.slice(1).map((item) => fieldElement(item.key))
  shakeInvalid(rest.filter((element): element is HTMLElement => Boolean(element)).map(shakeTarget))
})

const alertBox = ref<HTMLElement>()
const hasAlert = computed(() => Boolean(error.value || violations.value.length))

/** Ошибка появляется под формой, за краем окна: прокручиваем к ней и встряхиваем, чтобы её заметили */
function showAlert() {
  const element = alertBox.value
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  shakeInvalid([element])
}

// Новая ошибка или та же самая после повторного «Далее» — снова показываем
watch([error, () => violations.value.length, busy], async ([, , isBusy]) => {
  if (isBusy || !hasAlert.value) return
  await nextTick()
  showAlert()
})
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

        <div ref="body">
          <StepTerms v-if="step === 'terms'" :wizard="wizard" :products="products" />
          <StepDetails v-else-if="step === 'details'" :wizard="wizard" />
          <StepConsents v-else-if="step === 'consents'" :wizard="wizard" />
        </div>
        <ApplicationSubmitted
          v-if="step === 'done' && application"
          :application="application"
          :product-title="product.title"
        />

        <div
          v-if="hasAlert"
          ref="alertBox"
          class="mt-6 scroll-mb-6 rounded-2xl bg-brand-soft p-4 text-sm text-brand"
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
        <!-- Что ещё не заполнено на этом шаге — в одной строке с кнопками, клик ведёт к полю -->
        <div
          class="missing mr-auto flex min-w-0 basis-full flex-wrap items-center gap-1.5 text-sm sm:basis-auto sm:flex-1"
          :class="{ 'is-shaking': shaking }"
          aria-live="polite"
          @animationend="shaking = false"
        >
          <template v-if="missing.length">
            <span class="font-medium text-brand" :title="missingTitle">Не заполнено:</span>
            <button
              v-for="item in missingShown"
              :key="item.key"
              type="button"
              class="missing__chip max-w-[12rem] truncate rounded-full bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand hover:bg-brand hover:text-white"
              :title="`Перейти к полю «${item.label}»`"
              @click="goToField(item.key)"
            >
              {{ item.label }}
            </button>
            <span v-if="missingRest > 0" class="text-xs text-ink-secondary" :title="missingTitle">ещё {{ missingRest }}</span>
          </template>
          <button
            v-else-if="hasAlert"
            type="button"
            class="flex items-center gap-1.5 font-medium text-brand underline-offset-2 hover:underline"
            @click="showAlert"
          >
            <AlertCircle class="size-4" aria-hidden="true" />
            {{ error ? 'Посмотрите сообщение ниже' : 'Есть что исправить' }}
          </button>
          <span v-else class="flex items-center gap-1.5 font-medium text-success">
            <CircleCheck class="size-4" aria-hidden="true" />
            Всё заполнено
          </span>
        </div>

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

<style scoped>
.missing__chip {
  transition:
    background-color 0.2s,
    color 0.2s;
}

/* Попытка пройти дальше с пропусками: список у кнопок вздрагивает */
.missing.is-shaking {
  animation: missing-shake 0.45s ease-in-out;
}

@keyframes missing-shake {
  20%,
  60% {
    translate: -4px 0;
  }
  40%,
  80% {
    translate: 4px 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .missing.is-shaking {
    animation: none;
  }
}
</style>
