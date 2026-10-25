<script setup lang="ts">
import { BadgeCheck } from 'lucide-vue-next'

import type { ProductCatalog } from '@/entities/credit-product'
import { LoanCalculator } from '@/features/calculate-loan'
import type { LoanPurpose } from '@/shared/api'
import { SECTION_ID } from '@/shared/config'
import { BaseContainer, FloatCard, SectionHeader } from '@/shared/ui'

/**
 * Подбор и расчёт кредита одной секцией: к ней ведут и «Подобрать кредит», и «Калькулятор» —
 * оба якоря здесь, чтобы ссылки из шапки, футера и с первого экрана работали как раньше.
 */
defineProps<{
  products: ProductCatalog
  /** Компании вошедшего клиента — подбор и расчёт для выбранной */
  companies?: readonly { id: string; name: string }[] | null
}>()

const emit = defineEmits<{
  apply: [params: { productId: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId: string }]
}>()

const productId = defineModel<string>('productId', { required: true })
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })
const purpose = defineModel<LoanPurpose>('purpose', { default: 'working_capital' })
const organizationId = defineModel<string>('organizationId', { default: '' })
</script>

<template>
  <section :id="SECTION_ID.calculator" class="scroll-mt-20 bg-surface py-16 lg:py-24">
    <span :id="SECTION_ID.picker" class="block scroll-mt-20" aria-hidden="true" />
    <BaseContainer class="relative">
      <FloatCard
        class="absolute -top-8 right-10"
        :icon="BadgeCheck"
        eyebrow="Предодобрение"
        title="До 19,2 млн ₽ без справок"
        text="по оборотам на расчётном счёте"
        :delay="2"
      />
      <SectionHeader
        title="Подберём кредит и рассчитаем платёж"
        :description="
          companies?.length
            ? 'Выберите цель, сумму и срок — покажем подходящие продукты вашей компании и посчитаем платёж по ставке её предодобрения.'
            : 'Выберите цель, сумму и срок — покажем, какие продукты подходят и почему, и посчитаем платёж.'
        "
      />
      <div class="relative isolate mt-8 lg:mt-12">
        <LoanCalculator
          v-model:product-id="productId"
          v-model:amount="amount"
          v-model:term-months="termMonths"
          v-model:purpose="purpose"
          v-model:organization-id="organizationId"
          :products="products"
          :companies="companies"
          @apply="(params) => emit('apply', params)"
        />
      </div>
    </BaseContainer>
  </section>
</template>
