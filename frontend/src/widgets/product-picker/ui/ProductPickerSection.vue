<script setup lang="ts">
import { Target } from 'lucide-vue-next'

import type { ProductCatalog } from '@/entities/credit-product'
import { ProductPicker } from '@/features/pick-product'
import type { LoanPurpose } from '@/shared/api'
import { SECTION_ID } from '@/shared/config'
import { BaseContainer, DecorSticker, SectionHeader } from '@/shared/ui'

/** Подбор кредита под задачу — к нему ведёт кнопка «Подобрать кредит» на первом экране */
defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  apply: [params: { productCode: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId?: string }]
  calculate: [params: { productCode: string; amount: number; termMonths: number }]
}>()
</script>

<template>
  <section :id="SECTION_ID.picker" class="scroll-mt-20 py-16 lg:py-24">
    <BaseContainer class="relative">
      <DecorSticker
        class="absolute -top-10 right-10"
        :icon="Target"
        title="Под вашу задачу"
        caption="с объяснением"
        :tilt="-5"
        :delay="2"
      />
      <SectionHeader
        title="Подберём кредит под задачу"
        description="Выберите цель, сумму и срок — покажем, какие продукты подходят, почему и что поменять, если не подходят."
      />
      <div class="mt-8 lg:mt-12">
        <ProductPicker
          :products="products"
          @apply="(params) => emit('apply', params)"
          @calculate="(params) => emit('calculate', params)"
        />
      </div>
    </BaseContainer>
  </section>
</template>
