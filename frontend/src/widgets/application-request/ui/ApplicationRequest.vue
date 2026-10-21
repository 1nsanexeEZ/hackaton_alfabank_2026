<script setup lang="ts">
import { Check } from 'lucide-vue-next'

import type { ApplicationDraft } from '@/entities/application'
import type { ProductCatalog } from '@/entities/credit-product'
import { ApplicationForm } from '@/features/submit-application'
import { SECTION_ID } from '@/shared/config'
import { BaseContainer } from '@/shared/ui'

defineProps<{
  products: ProductCatalog
  draft: ApplicationDraft
}>()

const emit = defineEmits<{ editLoan: [] }>()

const HIGHLIGHTS = [
  'Заявка занимает пару минут — без сканов и визита в офис',
  'Данные о компании подтягиваются из госреестров автоматически',
  'Если банку что-то понадобится, запрос придёт в кабинет',
  'Решение и условия вы увидите там же, где подавали заявку',
]
</script>

<template>
  <section :id="SECTION_ID.application" class="pb-16 lg:pb-24">
    <BaseContainer>
      <div
        class="-mx-4 grid gap-8 rounded-[2.5rem] bg-night px-4 py-10 sm:mx-0 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16 lg:rounded-sheet lg:p-16"
      >
        <div class="px-2 text-on-night sm:px-0">
          <h2 class="text-title">Оформите заявку онлайн</h2>
          <p class="text-lead mt-4 text-on-night-secondary">
            Параметры из калькулятора уже подставлены. Осталось указать компанию и контактное лицо.
          </p>
          <ul class="mt-8 space-y-4">
            <li v-for="item in HIGHLIGHTS" :key="item" class="flex gap-3">
              <span class="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-brand">
                <Check class="size-3.5 text-white" :stroke-width="3" aria-hidden="true" />
              </span>
              <span>{{ item }}</span>
            </li>
          </ul>
        </div>

        <ApplicationForm :products="products" :draft="draft" @edit-loan="emit('editLoan')" />
      </div>
    </BaseContainer>
  </section>
</template>
