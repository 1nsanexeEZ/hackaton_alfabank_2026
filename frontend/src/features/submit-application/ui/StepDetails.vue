<script setup lang="ts">
import { computed } from 'vue'

import { COLLATERAL_TYPE_LABEL } from '@/entities/credit-product'
import { SelectField, TextField } from '@/shared/ui'

import type { ApplicationWizard, CollateralForm } from '../model/useApplicationWizard'
import DocumentUploads from './DocumentUploads.vue'
import ProductFieldsForm from './ProductFieldsForm.vue'

const props = defineProps<{ wizard: ApplicationWizard }>()

const { product, collateral, collateralNeeded, withFields, productFields, documents, fieldErrors, busy } = props.wizard

const collateralOptions = computed(() =>
  product.value.collateralTypes.map((value) => ({ value, label: COLLATERAL_TYPE_LABEL[value] ?? value })),
)

const OWNER_OPTIONS: { value: CollateralForm['owner']; label: string }[] = [
  { value: 'self', label: 'Компании или мне' },
  { value: 'third_party', label: 'Третьему лицу' },
]
</script>

<template>
  <div class="space-y-8">
    <section v-if="collateralNeeded" class="space-y-4">
      <div>
        <h3 class="text-base font-bold text-ink">Залог</h3>
        <p class="mt-0.5 text-sm text-ink-secondary">
          {{ product.collateral === 'required' ? 'Продукт выдаётся под залог.' : 'При такой сумме залог обязателен.' }}
          Оценку банк проверит сам.
        </p>
      </div>
      <div class="grid gap-4 sm:grid-cols-2">
        <div data-field="collateral.type">
          <SelectField v-model="collateral.type" label="Что даёте в залог" :options="collateralOptions" />
          <p v-if="fieldErrors['collateral.type']" class="mt-1.5 text-sm text-brand">{{ fieldErrors['collateral.type'] }}</p>
        </div>
        <SelectField v-model="collateral.owner" label="Кому принадлежит" :options="OWNER_OPTIONS" />
      </div>
      <TextField
        v-model="collateral.description"
        data-field="collateral.description"
        label="Описание"
        placeholder="Например: склад 1 200 м², Подольск, ул. Заводская, 5"
        :maxlength="1000"
        :error="fieldErrors['collateral.description']"
      />
      <TextField
        v-model="collateral.declaredValue"
        data-field="collateral.declared_value"
        label="Оценочная стоимость, ₽"
        inputmode="numeric"
        placeholder="0"
        :error="fieldErrors['collateral.declared_value']"
      />
    </section>

    <section v-if="withFields" class="space-y-4">
      <div>
        <h3 class="text-base font-bold text-ink">Анкета продукта</h3>
        <p class="mt-0.5 text-sm text-ink-secondary">Эти данные нужны для продукта «{{ product.title }}»</p>
      </div>
      <ProductFieldsForm v-model:values="productFields" :schema="product.fieldsSchema" :errors="fieldErrors" />
    </section>

    <section v-if="documents.length" class="space-y-4">
      <div>
        <h3 class="text-base font-bold text-ink">Документы</h3>
        <p class="mt-0.5 text-sm text-ink-secondary">Список зависит от продукта, суммы и формы бизнеса</p>
      </div>
      <DocumentUploads
        :slots="documents"
        :errors="fieldErrors"
        :disabled="busy"
        @upload="wizard.uploadDocument"
        @remove="wizard.removeDocument"
      />
    </section>
  </div>
</template>
