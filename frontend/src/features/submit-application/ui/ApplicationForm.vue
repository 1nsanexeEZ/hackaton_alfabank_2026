<script setup lang="ts">
import { CircleAlert, CircleCheck, PenLine } from 'lucide-vue-next'
import { computed } from 'vue'

import { APPLICATION_STATUS_META, type ApplicationDraft } from '@/entities/application'
import { findProduct, type ProductCatalog } from '@/entities/credit-product'
import { formatMoney, formatTerm } from '@/shared/lib'
import { BaseBadge, BaseButton, CheckboxField, SelectField, TextField } from '@/shared/ui'

import { PURPOSE_OPTIONS, useApplicationForm } from '../model/useApplicationForm'

const props = defineProps<{
  products: ProductCatalog
  draft: ApplicationDraft
}>()

const emit = defineEmits<{ editLoan: [] }>()

const product = computed(() => findProduct(props.products, props.draft.productId))

const { form, errors, status, result, submit, reset, fillDemo } = useApplicationForm(() => props.draft)
</script>

<template>
  <div class="rounded-3xl bg-white p-5 sm:p-6 lg:rounded-card lg:p-8">
    <div v-if="status === 'success' && result" class="flex flex-col items-start" role="status">
      <span class="flex size-14 items-center justify-center rounded-full bg-success-soft">
        <CircleCheck class="size-7 text-success" aria-hidden="true" />
      </span>
      <h3 class="text-subtitle mt-5">Заявка № {{ result.number }} отправлена</h3>
      <BaseBadge class="mt-3" :tone="APPLICATION_STATUS_META[result.status].tone">
        {{ APPLICATION_STATUS_META[result.status].label }}
      </BaseBadge>
      <p class="mt-4 text-ink-secondary">
        Следующий шаг — автоматическая проверка данных компании. Статус и запросы банка появятся в личном
        кабинете, ничего не нужно ждать по почте или телефону.
      </p>
      <BaseButton class="mt-6" variant="secondary" @click="reset">Отправить ещё одну заявку</BaseButton>
    </div>

    <form v-else class="space-y-5" novalidate @submit.prevent="submit">
      <div class="rounded-2xl bg-surface-soft p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm text-ink-secondary">Вы выбрали</p>
            <p class="mt-1 font-semibold">{{ product.title }}</p>
            <p class="mt-1 text-sm text-ink-secondary">
              {{ formatMoney(draft.amount) }} · {{ formatTerm(draft.termMonths) }}
            </p>
          </div>
          <button
            type="button"
            class="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-brand transition-colors hover:bg-brand-soft"
            @click="emit('editLoan')"
          >
            <PenLine class="size-4" aria-hidden="true" />
            Изменить
          </button>
        </div>
      </div>

      <TextField
        v-model="form.inn"
        label="ИНН компании или ИП"
        placeholder="10 или 12 цифр"
        inputmode="numeric"
        :maxlength="12"
        :error="errors.inn"
        hint="Остальные данные о компании подтянем из ЕГРЮЛ/ЕГРИП"
      />
      <TextField
        v-model="form.contactName"
        label="Контактное лицо"
        placeholder="Имя и фамилия"
        autocomplete="name"
        :error="errors.contactName"
      />
      <SelectField v-model="form.purpose" label="Цель кредита" :options="PURPOSE_OPTIONS" />

      <CheckboxField v-model="form.consent" :error="errors.consent">
        Согласен на обработку данных и запрос в бюро кредитных историй
      </CheckboxField>

      <p
        v-if="status === 'error'"
        class="flex items-center gap-2 rounded-xl bg-brand-soft p-3 text-sm text-brand"
        role="alert"
      >
        <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
        Не получилось отправить заявку. Попробуйте ещё раз.
      </p>

      <div class="flex flex-col gap-3 pt-2 sm:flex-row">
        <BaseButton type="submit" size="l" :loading="status === 'submitting'" class="sm:flex-1">
          Отправить заявку
        </BaseButton>
        <BaseButton variant="ghost" size="l" @click="fillDemo">Тестовые данные</BaseButton>
      </div>
    </form>
  </div>
</template>
