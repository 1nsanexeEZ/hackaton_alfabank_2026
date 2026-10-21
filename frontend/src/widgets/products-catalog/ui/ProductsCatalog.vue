<script setup lang="ts">
import { Calculator, Zap } from 'lucide-vue-next'
import { ref, watch } from 'vue'

import { ProductFlexCard, type ProductCatalog } from '@/entities/credit-product'
import { ProductFilterControl, useProductFilter } from '@/features/filter-products'
import { SECTION_ID } from '@/shared/config'
import { BaseButton, BaseContainer, DecorSticker, PeekSticker, SectionHeader } from '@/shared/ui'

const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  /** Рассчитать платёж по продукту */
  calculate: [productId: string]
  /** Сразу перейти к заявке */
  apply: [productId: string]
}>()

const { filter, filteredProducts } = useProductFilter(() => props.products)

// В ряду всегда раскрыта одна карточка
const expandedId = ref(props.products[0].id)

watch(filteredProducts, (list) => {
  const first = list[0]
  if (first && !list.some((product) => product.id === expandedId.value)) expandedId.value = first.id
})
</script>

<template>
  <section :id="SECTION_ID.products" class="py-16 lg:py-24">
    <BaseContainer class="relative">
      <DecorSticker
        class="absolute -top-12 right-24"
        :icon="Zap"
        title="Решение онлайн"
        caption="без похода в банк"
        :tilt="6"
        :delay="1"
      />
      <SectionHeader
        title="Кредиты для бизнеса"
        description="Условия демонстрационные: итоговые ставка и лимит зависят от решения банка по заявке."
      >
        <template #aside>
          <ProductFilterControl v-model="filter" class="self-start lg:self-auto" />
        </template>
      </SectionHeader>

      <div class="relative isolate mt-8 flex flex-col gap-3 lg:mt-12 lg:h-[28rem] lg:flex-row lg:gap-4">
        <PeekSticker art="rocket" from="right" class="absolute top-28 -right-20 -z-10" :tilt="62" :delay="1" />
        <ProductFlexCard
          v-for="(product, index) in filteredProducts"
          :key="product.id"
          :product="product"
          :index="index"
          :expanded="product.id === expandedId"
          @expand="expandedId = product.id"
        >
          <template #actions>
            <BaseButton variant="inverted" @click="emit('apply', product.id)">Оформить</BaseButton>
            <BaseButton variant="glass" @click="emit('calculate', product.id)">
              <Calculator class="size-4" aria-hidden="true" />
              Рассчитать платёж
            </BaseButton>
          </template>
        </ProductFlexCard>
      </div>
    </BaseContainer>
  </section>
</template>
