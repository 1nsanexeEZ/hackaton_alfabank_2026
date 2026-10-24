<script setup lang="ts">
import { ref, shallowRef, watch } from 'vue'

import { loanDraft, type ApplicationDraft } from '@/entities/application'
import { findProduct, useProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { fitLoanParams, getDefaultLoanParams } from '@/features/calculate-loan'
import { clientApi, type LoanPurpose } from '@/shared/api'
import { SECTION_ID } from '@/shared/config'
import { scrollToSection } from '@/shared/lib'
import { AsyncState, BaseContainer } from '@/shared/ui'
import { openApplicationCard, startApplication } from '@/widgets/apply-flow'
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

/**
 * Компании вошедшего клиента: подбор проверяет выбранную, калькулятор считает по ставке её предодобрения
 * (POST /bff/products/{code}/calculate), а «Оформить» открывает заявку от неё же
 */
const companies = shallowRef<{ id: string; name: string }[] | null>(null)
const calculatorCompany = ref('')

watch(
  () => customer.state.me?.id,
  async (id) => {
    companies.value = null
    calculatorCompany.value = ''
    if (!id) return
    try {
      const list = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
      companies.value = list.map((item) => ({ id: item.id, name: item.name }))
      const preferred = list.find((item) => item.my_permissions.includes('submit_application')) ?? list[0]
      calculatorCompany.value = preferred?.id ?? ''
    } catch {
      // Без компаний калькулятор считает по базовой ставке, как для гостя
    }
  },
  { immediate: true },
)

/** Подбор и расчёт: сумма и срок уже подогнаны под выбранный продукт — переносим их в заявку как есть */
function applyFromCalculator(params: { productId: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId: string }) {
  Object.assign(loanDraft, { ...params, organizationId: params.organizationId || undefined })
  void startApplication()
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
    <LoanCalculatorSection
      v-model:product-id="loanDraft.productId"
      v-model:amount="loanDraft.amount"
      v-model:term-months="loanDraft.termMonths"
      v-model:purpose="loanDraft.purpose"
      v-model:organization-id="calculatorCompany"
      :products="products"
      :companies="companies"
      @apply="applyFromCalculator"
    />
    <ProductsCatalog :products="products" @calculate="calculateProduct" @apply="applyForProduct" />
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
