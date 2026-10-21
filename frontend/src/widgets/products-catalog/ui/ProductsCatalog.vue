<script setup lang="ts">
import { Calculator } from 'lucide-vue-next'

import { ProductCard, type ProductCatalog } from '@/entities/credit-product'
import { ProductFilterControl, useProductFilter } from '@/features/filter-products'
import { SECTION_ID } from '@/shared/config'
import { BaseButton, BaseContainer, SectionHeader } from '@/shared/ui'

const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  /** Рассчитать платёж по продукту */
  calculate: [productId: string]
  /** Сразу перейти к заявке */
  apply: [productId: string]
}>()

const { filter, filteredProducts } = useProductFilter(() => props.products)
</script>

<template>
  <section :id="SECTION_ID.products" class="py-16 lg:py-24">
    <BaseContainer>
      <SectionHeader
        title="Кредиты для бизнеса"
        description="Условия демонстрационные: итоговые ставка и лимит зависят от решения банка по заявке."
      >
        <template #aside>
          <ProductFilterControl v-model="filter" class="self-start lg:self-auto" />
        </template>
      </SectionHeader>

      <ul class="mt-8 grid gap-4 lg:mt-12 lg:grid-cols-2 lg:gap-6">
        <li v-for="product in filteredProducts" :key="product.id">
          <ProductCard :product="product" class="h-full">
            <template #actions>
              <BaseButton class="sm:flex-1" @click="emit('apply', product.id)">Оформить</BaseButton>
              <BaseButton variant="secondary" class="sm:flex-1" @click="emit('calculate', product.id)">
                <Calculator class="size-4" aria-hidden="true" />
                Рассчитать платёж
              </BaseButton>
            </template>
          </ProductCard>
        </li>
      </ul>
    </BaseContainer>
  </section>
</template>
