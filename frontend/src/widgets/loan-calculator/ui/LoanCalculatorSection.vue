<script setup lang="ts">
import { Calculator, CalendarCheck } from 'lucide-vue-next'

import type { ProductCatalog } from '@/entities/credit-product'
import { LoanCalculator } from '@/features/calculate-loan'
import { SECTION_ID } from '@/shared/config'
import { BaseContainer, DecorSticker, PeekSticker, SectionHeader } from '@/shared/ui'

defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{ apply: [] }>()

const productId = defineModel<string>('productId', { required: true })
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })
</script>

<template>
  <section :id="SECTION_ID.calculator" class="bg-surface py-16 lg:py-24">
    <BaseContainer class="relative">
      <DecorSticker
        class="absolute top-6 right-6"
        :icon="CalendarCheck"
        tone="sky"
        title="Равные платежи"
        caption="каждый месяц"
        :tilt="4"
      />
      <DecorSticker
        class="absolute top-2 right-[19rem]"
        :icon="Calculator"
        tone="sun"
        title="Расчёт за секунду"
        caption="меняйте сумму и срок"
        :tilt="-5"
        :delay="3"
      />
      <SectionHeader
        title="Рассчитайте платёж"
        description="Выберите продукт, сумму и срок — параметры сразу перенесутся в заявку."
      />
      <div class="relative isolate mt-8 lg:mt-12">
        <PeekSticker art="banknote" class="absolute -top-16 right-14 -z-10" :tilt="-10" :delay="3" />
        <PeekSticker art="calculator" from="left" class="absolute bottom-10 -left-16 -z-10" :tilt="12" />
        <LoanCalculator
          v-model:product-id="productId"
          v-model:amount="amount"
          v-model:term-months="termMonths"
          :products="products"
          @apply="emit('apply')"
        />
      </div>
    </BaseContainer>
  </section>
</template>
