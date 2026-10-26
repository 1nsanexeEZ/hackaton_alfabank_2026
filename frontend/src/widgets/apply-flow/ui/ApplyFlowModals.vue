<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'

import { loanDraft, myApplications } from '@/entities/application'
import { findProduct, useProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { CustomerLoginDrawer } from '@/features/customer-login'
import { ClientProfileForm, CompanyConsents, PersonalConsents } from '@/features/edit-client-profile'
import { CompanyPanel } from '@/features/manage-company'
import { NotificationsPanel } from '@/features/read-notifications'
import { ApplicationModal } from '@/features/submit-application'
import { ApplicationCard, MyApplicationsList } from '@/features/track-application'
import type { LoanPurpose } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { clamp } from '@/shared/lib'
import { AsyncState, BaseModal } from '@/shared/ui'

import { applyFlow, backFromCard, onLoggedIn, openApplicationCard, startApplication, switchAccount } from '../model/flow'

/**
 * Модалки клиента на сайте: вход, мастер заявки и кабинет — мои заявки, заявка, уведомления,
 * компания, профиль. Одни на весь сайт, открываются через startApplication / openLogin / openCabinet.
 */
const { products, error, reload } = useProductCatalog()
const router = useRouter()

/** Из модалки — на страницу сайта (чат поддержки): модалку закрываем */
function leaveTo(target: RouteLocationRaw) {
  applyFlow.modal = null
  void router.push(target)
}

/** Вопрос в поддержку по заявке: форма нового обращения с подставленной заявкой */
const askAbout = (applicationId: string) => leaveTo({ path: ROUTE_PATH.support, query: { application: applicationId } })

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
    ? 'Чтобы оформить заявку, войдите: данные компании загрузим автоматически'
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
  <CustomerLoginDrawer
    v-model:open="loginOpen"
    :description="loginDescription"
    :next="applyFlow.continueToApplication ? 'application' : 'profile'"
    @success="onLoggedIn"
  />

  <ApplicationModal v-if="products" v-model:open="applicationOpen" :products="products" @switch-account="switchAccount" />
  <!-- Нажали «Оформить», пока каталог ещё грузится или не загрузился -->
  <BaseModal v-else v-model:open="applicationOpen" title="Заявка на кредит">
    <AsyncState :loading="!error" :error="error" @retry="reload" />
  </BaseModal>

  <BaseModal v-model:open="applicationsOpen" title="Мои заявки" description="Заявки всех ваших компаний" wide>
    <MyApplicationsList v-if="applicationsOpen" @open="openApplicationCard" @apply="startApplication()" />
  </BaseModal>

  <!-- Окно заявки рисует себя целиком: тёмная шапка с этапами, вкладки, действия в подвале.
       Высота постоянная: вкладки разной длины не двигают окно -->
  <BaseModal v-model:open="cardOpen" title="Заявка" wide bare tall>
    <template #default="{ close, titleId }">
      <ApplicationCard
        v-if="cardOpen && applyFlow.cardId"
        :application-id="applyFlow.cardId"
        :products="products"
        :title-id="titleId"
        :back-label="applyFlow.cardFrom ? (applyFlow.cardFrom === 'notifications' ? 'К уведомлениям' : 'Ко всем заявкам') : null"
        @back="backFromCard"
        @close="close"
        @continue-draft="(draft) => applyWith(draft.productCode, draft)"
        @apply-product="(code) => applyWith(code)"
        @ask="askAbout"
      />
    </template>
  </BaseModal>

  <BaseModal v-model:open="notificationsOpen" title="Уведомления" description="События по заявкам и новости для вашего бизнеса" wide>
    <NotificationsPanel v-if="notificationsOpen" @open-application="openApplicationCard" @open-link="leaveTo" />
  </BaseModal>

  <BaseModal v-model:open="companyOpen" title="Компания" wide>
    <CompanyPanel
      v-if="companyOpen"
      :products="products"
      @apply-product="(code, organizationId, maxAmount) => applyWith(code, { organizationId, amount: maxAmount })"
    />
  </BaseModal>

  <BaseModal v-model:open="profileOpen" title="Профиль">
    <template v-if="profileOpen">
      <ClientProfileForm />
      <PersonalConsents class="mt-6" />
      <CompanyConsents class="mt-6" />
    </template>
  </BaseModal>
</template>
