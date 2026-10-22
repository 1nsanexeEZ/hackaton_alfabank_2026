<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import { computed, watch } from 'vue'

import { loanDraft, myApplications } from '@/entities/application'
import { findProduct, useProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { CustomerLoginModal } from '@/features/customer-login'
import { ClientProfileForm } from '@/features/edit-client-profile'
import { CompanyPanel } from '@/features/manage-company'
import { NotificationsPanel } from '@/features/read-notifications'
import { ApplicationModal } from '@/features/submit-application'
import { ApplicationCard, MyApplicationsList } from '@/features/track-application'
import type { LoanPurpose } from '@/shared/api'
import { clamp } from '@/shared/lib'
import { AsyncState, BaseModal } from '@/shared/ui'

import { applyFlow, backFromCard, onLoggedIn, openApplicationCard, startApplication, switchAccount } from '../model/flow'

/**
 * Модалки клиента на сайте: вход, мастер заявки и кабинет — мои заявки, заявка, уведомления,
 * компания, профиль. Одни на весь сайт, открываются через startApplication / openLogin / openCabinet.
 */
const { products, error, reload } = useProductCatalog()

function modalModel(name: NonNullable<typeof applyFlow.modal>) {
  return computed({
    get: () => applyFlow.modal === name,
    set: (isOpen: boolean) => {
      if (isOpen) applyFlow.modal = name
      else if (applyFlow.modal === name) applyFlow.modal = null
    },
  })
}

const loginOpen = modalModel('login')
const applicationOpen = modalModel('application')
const applicationsOpen = modalModel('applications')
const cardOpen = modalModel('card')
const notificationsOpen = modalModel('notifications')
const companyOpen = modalModel('company')
const profileOpen = modalModel('profile')

// Мастер закрыли — черновик мог появиться, заявка уйти в банк: карточка на первом экране должна это показать
watch(
  () => applyFlow.modal,
  (modal, previous) => {
    if (previous === 'application' && modal !== 'application' && customer.state.me) void myApplications.refresh()
  },
)

const loginDescription = computed(() =>
  applyFlow.continueToApplication
    ? 'Чтобы оформить заявку, войдите: данные компании подтянем автоматически'
    : 'Заявки, решения банка и подписание — в одном кабинете',
)

/** Открыть мастер с продуктом, компанией и суммой: продолжить черновик, оформить совет банка или предодобрение */
function applyWith(
  code: string,
  params: { organizationId?: string; amount?: number; termMonths?: number; purpose?: LoanPurpose } = {},
) {
  if (!products.value) return
  const product = products.value.find((item) => item.code === code) ?? findProduct(products.value, loanDraft.productId)
  Object.assign(loanDraft, {
    productId: product.id,
    amount: clamp(params.amount || loanDraft.amount || product.amount.min, product.amount.min, product.amount.max),
    termMonths: clamp(params.termMonths || loanDraft.termMonths || product.termMonths.min, product.termMonths.min, product.termMonths.max),
    organizationId: params.organizationId,
    purpose: params.purpose,
  })
  void startApplication()
}
</script>

<template>
  <CustomerLoginModal v-model:open="loginOpen" :description="loginDescription" @success="onLoggedIn" />

  <ApplicationModal v-if="products" v-model:open="applicationOpen" :products="products" @switch-account="switchAccount" />
  <!-- Нажали «Оформить», пока каталог ещё грузится или не загрузился -->
  <BaseModal v-else v-model:open="applicationOpen" title="Заявка на кредит">
    <AsyncState :loading="!error" :error="error" @retry="reload" />
  </BaseModal>

  <BaseModal v-model:open="applicationsOpen" title="Мои заявки" description="Заявки всех ваших компаний" wide>
    <MyApplicationsList v-if="applicationsOpen" @open="openApplicationCard" @apply="startApplication()" />
  </BaseModal>

  <BaseModal v-model:open="cardOpen" title="Заявка" wide>
    <button
      v-if="applyFlow.cardFrom"
      type="button"
      class="mb-4 flex items-center gap-1.5 text-sm font-medium text-ink-secondary hover:text-ink"
      @click="backFromCard"
    >
      <ArrowLeft class="size-4" aria-hidden="true" />
      {{ applyFlow.cardFrom === 'notifications' ? 'К уведомлениям' : 'Ко всем заявкам' }}
    </button>
    <ApplicationCard
      v-if="cardOpen && applyFlow.cardId"
      :application-id="applyFlow.cardId"
      :products="products"
      @continue-draft="(draft) => applyWith(draft.productCode, draft)"
      @apply-product="(code) => applyWith(code)"
    />
  </BaseModal>

  <BaseModal v-model:open="notificationsOpen" title="Уведомления" description="События по заявкам и новости для вашего бизнеса" wide>
    <NotificationsPanel v-if="notificationsOpen" @open-application="openApplicationCard" />
  </BaseModal>

  <BaseModal v-model:open="companyOpen" title="Компания" wide>
    <CompanyPanel
      v-if="companyOpen"
      :products="products"
      @apply-product="(code, organizationId, maxAmount) => applyWith(code, { organizationId, amount: maxAmount })"
    />
  </BaseModal>

  <BaseModal v-model:open="profileOpen" title="Профиль">
    <ClientProfileForm v-if="profileOpen" />
  </BaseModal>
</template>
