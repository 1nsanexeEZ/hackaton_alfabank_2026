<script setup lang="ts">
import { BENEFICIARY_BASIS_LABEL } from '@/entities/application'
import type { BeneficiaryBasis } from '@/shared/api'

import type { BeneficiaryForm } from '../model/thirdParty'
import type { DocumentSlot } from '../model/useApplicationWizard'
import DocumentUploads from './DocumentUploads.vue'
import ThirdPartyFields from './ThirdPartyFields.vue'

/**
 * Вопрос о третьем лице: в чьих интересах клиент берёт кредит. Обязателен для всех заявок.
 * Ответ «да» — кто это, на каком основании и сам договор: без него заявку не отправить.
 */
defineProps<{ contract: DocumentSlot; errors: Record<string, string>; disabled?: boolean }>()

const emit = defineEmits<{ upload: [type: string, file: File]; remove: [documentId: string] }>()

const beneficiary = defineModel<BeneficiaryForm>('beneficiary', { required: true })

const ANSWERS: { value: boolean; label: string }[] = [
  { value: false, label: 'Нет, в своих интересах' },
  { value: true, label: 'Да' },
]
const BASIS_OPTIONS = Object.entries(BENEFICIARY_BASIS_LABEL) as [BeneficiaryBasis, string][]

const choiceClass = (active: boolean) =>
  active ? 'bg-brand-soft text-ink ring-2 ring-brand' : 'bg-surface-soft text-ink hover:bg-surface'

function answer(value: boolean) {
  beneficiary.value.acts = value
}

function chooseBasis(value: BeneficiaryBasis) {
  beneficiary.value.basis = value
}
</script>

<template>
  <section class="space-y-4">
    <div data-field="beneficiary.acts_for_third_party">
      <p id="beneficiary-question" class="text-sm font-semibold text-ink">
        Вы действуете в интересах третьего лица — по агентскому договору, договору поручения, комиссии или
        доверительного управления?
      </p>
      <div class="mt-3 grid gap-2 sm:grid-cols-2" role="radiogroup" aria-labelledby="beneficiary-question">
        <button
          v-for="item in ANSWERS"
          :key="String(item.value)"
          type="button"
          role="radio"
          class="rounded-xl px-4 py-3 text-left text-sm font-medium transition-colors"
          :class="choiceClass(beneficiary.acts === item.value)"
          :aria-checked="beneficiary.acts === item.value"
          @click="answer(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
      <p v-if="errors['beneficiary.acts_for_third_party']" class="mt-1.5 text-sm text-brand">
        {{ errors['beneficiary.acts_for_third_party'] }}
      </p>
    </div>

    <div v-if="beneficiary.acts" class="space-y-4 rounded-2xl border border-line p-4">
      <p class="text-sm font-medium text-ink">В чьих интересах</p>
      <ThirdPartyFields v-model:party="beneficiary.party" prefix="beneficiary.beneficiary" :errors="errors" />

      <div data-field="beneficiary.basis">
        <p id="beneficiary-basis" class="text-sm font-medium text-ink">Основание</p>
        <div class="mt-2 grid gap-2 sm:grid-cols-2" role="radiogroup" aria-labelledby="beneficiary-basis">
          <button
            v-for="[value, label] in BASIS_OPTIONS"
            :key="value"
            type="button"
            role="radio"
            class="rounded-xl px-3.5 py-2.5 text-left text-sm transition-colors"
            :class="choiceClass(beneficiary.basis === value)"
            :aria-checked="beneficiary.basis === value"
            @click="chooseBasis(value)"
          >
            {{ label }}
          </button>
        </div>
        <p v-if="errors['beneficiary.basis']" class="mt-1.5 text-sm text-brand">{{ errors['beneficiary.basis'] }}</p>
      </div>

      <div>
        <p class="text-sm font-medium text-ink">Договор</p>
        <p class="mt-0.5 text-xs text-ink-secondary">Загрузите договор с третьим лицом — банк проверит его вместе с заявкой</p>
        <DocumentUploads
          class="mt-2"
          :slots="[contract]"
          :errors="errors"
          :disabled="disabled"
          @upload="(type, file) => emit('upload', type, file)"
          @remove="(id) => emit('remove', id)"
        />
      </div>
    </div>
  </section>
</template>
