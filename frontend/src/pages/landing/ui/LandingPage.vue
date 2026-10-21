<script setup lang="ts">
import { ref } from 'vue'

import type { ApplicationDraft } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS, findProduct } from '@/entities/credit-product'
import { fitLoanParams, getDefaultLoanParams } from '@/features/calculate-loan'
import { SECTION_ID } from '@/shared/config'
import { scrollToSection } from '@/shared/lib'
import { ApplicationRequest } from '@/widgets/application-request'
import { BenefitsSection } from '@/widgets/benefits'
import { FaqSection } from '@/widgets/faq'
import { HeroSection } from '@/widgets/hero'
import { LoanCalculatorSection } from '@/widgets/loan-calculator'
import { ProcessSteps } from '@/widgets/process-steps'
import { ProductsCatalog } from '@/widgets/products-catalog'

const products = DEMO_CREDIT_PRODUCTS

// Параметры кредита общие для каталога, калькулятора и формы заявки
const loan = ref<ApplicationDraft>(getDefaultLoanParams(products[0]))

function selectProduct(productId: string) {
  const product = findProduct(products, productId)
  loan.value = { productId: product.id, ...fitLoanParams(product, loan.value.amount, loan.value.termMonths) }
}

function calculateProduct(productId: string) {
  selectProduct(productId)
  scrollToSection(SECTION_ID.calculator)
}

function applyForProduct(productId: string) {
  selectProduct(productId)
  scrollToSection(SECTION_ID.application)
}
</script>

<template>
  <HeroSection />
  <BenefitsSection />
  <ProductsCatalog :products="products" @calculate="calculateProduct" @apply="applyForProduct" />
  <LoanCalculatorSection
    v-model:product-id="loan.productId"
    v-model:amount="loan.amount"
    v-model:term-months="loan.termMonths"
    :products="products"
    @apply="scrollToSection(SECTION_ID.application)"
  />
  <ProcessSteps />
  <ApplicationRequest :products="products" :draft="loan" @edit-loan="scrollToSection(SECTION_ID.calculator)" />
  <FaqSection />
</template>
