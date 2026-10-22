<script setup lang="ts">
import { watch } from 'vue'

import { loanDraft } from '@/entities/application'
import { findProduct, useProductCatalog } from '@/entities/credit-product'
import { fitLoanParams, getDefaultLoanParams } from '@/features/calculate-loan'
import { SECTION_ID } from '@/shared/config'
import { scrollToSection } from '@/shared/lib'
import { AsyncState, BaseContainer } from '@/shared/ui'
import { startApplication } from '@/widgets/apply-flow'
import { BenefitsSection } from '@/widgets/benefits'
import { FaqSection } from '@/widgets/faq'
import { HeroSection } from '@/widgets/hero'
import { LoanCalculatorSection } from '@/widgets/loan-calculator'
import { ProcessSteps } from '@/widgets/process-steps'
import { ProductsCatalog } from '@/widgets/products-catalog'

// Каталог — из GET /products; параметры кредита общие для каталога, калькулятора и модалки заявки
const { products, error, reload } = useProductCatalog()

watch(
  products,
  (list) => {
    if (!list) return
    const product = findProduct(list, loanDraft.productId)
    const params = loanDraft.productId
      ? { productId: product.id, ...fitLoanParams(product, loanDraft.amount, loanDraft.termMonths) }
      : getDefaultLoanParams(product)
    Object.assign(loanDraft, params)
  },
  { immediate: true },
)

function selectProduct(productId: string) {
  if (!products.value) return
  const product = findProduct(products.value, productId)
  Object.assign(loanDraft, { productId: product.id, ...fitLoanParams(product, loanDraft.amount, loanDraft.termMonths) })
}

function calculateProduct(productId: string) {
  selectProduct(productId)
  scrollToSection(SECTION_ID.calculator)
}

function applyForProduct(productId: string) {
  selectProduct(productId)
  void startApplication()
}
</script>

<template>
  <HeroSection :products="products" />
  <BenefitsSection />
  <template v-if="products">
    <ProductsCatalog :products="products" @calculate="calculateProduct" @apply="applyForProduct" />
    <LoanCalculatorSection
      v-model:product-id="loanDraft.productId"
      v-model:amount="loanDraft.amount"
      v-model:term-months="loanDraft.termMonths"
      :products="products"
      @apply="startApplication()"
    />
  </template>
  <!-- Секции продуктов и калькулятора ждут каталог; якоря держим, чтобы ссылки из шапки работали -->
  <section v-else :id="SECTION_ID.products" class="py-16 lg:py-24">
    <BaseContainer>
      <AsyncState :loading="!error" :error="error" @retry="reload" />
    </BaseContainer>
  </section>
  <ProcessSteps />
  <FaqSection />
</template>
