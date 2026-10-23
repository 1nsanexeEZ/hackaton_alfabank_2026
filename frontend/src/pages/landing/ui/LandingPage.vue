<script setup lang="ts">
import { shallowRef, watch } from 'vue'

import { loanDraft, type ApplicationDraft } from '@/entities/application'
import { findProduct, useProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { fitLoanParams, getDefaultLoanParams } from '@/features/calculate-loan'
import { clientApi, type LoanPurpose, type PreApprovedOfferDto } from '@/shared/api'
import { SECTION_ID } from '@/shared/config'
import { scrollToSection } from '@/shared/lib'
import { AsyncState, BaseContainer } from '@/shared/ui'
import { openApplicationCard, startApplication } from '@/widgets/apply-flow'
import { BenefitsSection } from '@/widgets/benefits'
import { FaqSection } from '@/widgets/faq'
import { HeroSection } from '@/widgets/hero'
import { LoanCalculatorSection } from '@/widgets/loan-calculator'
import { ProcessSteps } from '@/widgets/process-steps'
import { ProductPickerSection } from '@/widgets/product-picker'
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

/** Предодобрение компании вошедшего клиента — калькулятор показывает лимит и предупреждает, если сумма больше */
const preApproved = shallowRef<{ companyName: string; offers: PreApprovedOfferDto[] } | null>(null)

watch(
  () => customer.state.me?.id,
  async (id) => {
    preApproved.value = null
    if (!id) return
    try {
      const dashboard = await clientApi.dashboard()
      if (dashboard.organization && dashboard.pre_approved.length) {
        preApproved.value = { companyName: dashboard.organization.name, offers: dashboard.pre_approved }
      }
    } catch {
      // Без предодобрения калькулятор считает по базовой ставке, как для гостя
    }
  },
  { immediate: true },
)

/** Подбор под задачу: условия подогнаны под продукт — переносим их в заявку или калькулятор как есть */
function pickedProduct(code: string) {
  return products.value?.find((product) => product.code === code)
}

function applyPicked(params: { productCode: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId?: string }) {
  const product = pickedProduct(params.productCode)
  if (!product) return
  Object.assign(loanDraft, {
    productId: product.id,
    amount: params.amount,
    termMonths: params.termMonths,
    purpose: params.purpose,
    organizationId: params.organizationId,
  })
  void startApplication()
}

function calculatePicked(params: { productCode: string; amount: number; termMonths: number }) {
  const product = pickedProduct(params.productCode)
  if (!product) return
  Object.assign(loanDraft, { productId: product.id, amount: params.amount, termMonths: params.termMonths })
  scrollToSection(SECTION_ID.calculator)
}

/** «Продолжить заявку» на карточке первого экрана: мастер откроется с компанией и условиями черновика */
function continueApplication(draft: ApplicationDraft) {
  Object.assign(loanDraft, draft)
  void startApplication()
}
</script>

<template>
  <HeroSection :products="products" @apply="startApplication()" @continue="continueApplication" @open="openApplicationCard" />
  <BenefitsSection />
  <template v-if="products">
    <ProductPickerSection :products="products" @apply="applyPicked" @calculate="calculatePicked" />
    <ProductsCatalog :products="products" @calculate="calculateProduct" @apply="applyForProduct" />
    <LoanCalculatorSection
      v-model:product-id="loanDraft.productId"
      v-model:amount="loanDraft.amount"
      v-model:term-months="loanDraft.termMonths"
      :products="products"
      :pre-approved="preApproved"
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
