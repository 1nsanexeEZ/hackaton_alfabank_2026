<script setup lang="ts">
import type { ProductCatalog } from '@/entities/credit-product'
import { LoanCalculator } from '@/features/calculate-loan'
import { SECTION_ID } from '@/shared/config'
import { BaseContainer, SectionHeader } from '@/shared/ui'

defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{ apply: [] }>()

const productId = defineModel<string>('productId', { required: true })
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })
</script>

<template>
  <section :id="SECTION_ID.calculator" class="bg-surface py-16 lg:py-24">
    <BaseContainer>
      <SectionHeader
        title="Рассчитайте платёж"
        description="Выберите продукт, сумму и срок — параметры сразу перенесутся в заявку."
      />
      <LoanCalculator
        v-model:product-id="productId"
        v-model:amount="amount"
        v-model:term-months="termMonths"
        class="mt-8 lg:mt-12"
        :products="products"
        @apply="emit('apply')"
      />
    </BaseContainer>
  </section>
</template>
