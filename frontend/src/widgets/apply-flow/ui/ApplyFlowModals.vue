<script setup lang="ts">
import { computed, watch } from 'vue'

import { myApplications } from '@/entities/application'
import { useProductCatalog } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { CustomerLoginModal } from '@/features/customer-login'
import { ApplicationModal } from '@/features/submit-application'
import { AsyncState, BaseModal } from '@/shared/ui'

import { applyFlow, onLoggedIn, switchAccount } from '../model/flow'

/** Модалки входа и заявки — одни на весь сайт, открываются через startApplication / openLogin */
const { products, error, reload } = useProductCatalog()

function modalModel(name: 'login' | 'application') {
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
</script>

<template>
  <CustomerLoginModal v-model:open="loginOpen" :description="loginDescription" @success="onLoggedIn" />

  <ApplicationModal v-if="products" v-model:open="applicationOpen" :products="products" @switch-account="switchAccount" />
  <!-- Нажали «Оформить», пока каталог ещё грузится или не загрузился -->
  <BaseModal v-else v-model:open="applicationOpen" title="Заявка на кредит">
    <AsyncState :loading="!error" :error="error" @retry="reload" />
  </BaseModal>
</template>
