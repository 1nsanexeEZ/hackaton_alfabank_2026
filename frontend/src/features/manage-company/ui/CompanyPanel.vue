<script setup lang="ts">
import { CircleAlert, CircleCheck } from 'lucide-vue-next'
import { computed, onMounted, watch } from 'vue'

import type { ProductCatalog } from '@/entities/credit-product'
import { founderPrescreen, FounderPrescreenPanel } from '@/entities/customer'
import { AsyncState, SelectField } from '@/shared/ui'

import { useCompany } from '../model/useCompany'
import CompanyMembers from './CompanyMembers.vue'
import CompanyRequisites from './CompanyRequisites.vue'
import FinancialReports from './FinancialReports.vue'
import PreApprovedOffers from './PreApprovedOffers.vue'
import StartupProject from './StartupProject.vue'

/**
 * Компания клиента: реквизиты, предодобрение (у стартапа — проверка учредителя, бизнес-план и проектная
 * оценка), отчётность, участники
 */
const props = defineProps<{ products: ProductCatalog | null }>()

const emit = defineEmits<{ applyProduct: [code: string, organizationId: string, maxAmount: number] }>()

const company = useCompany()
const {
  organizations,
  organizationId,
  detail,
  reports,
  preApproved,
  members,
  loading,
  error,
  busy,
  actionError,
  notice,
  verification,
  accessLost,
  canEditFinancials,
  canManageMembers,
  canSubmit,
} = company

onMounted(() => void company.loadOrganizations())

const organizationOptions = computed(() => organizations.value.map((item) => ({ value: item.id, label: `${item.name} · ИНН ${item.inn}` })))
// Сегмент компании: у стартапа вместо предодобрения — проверка учредителя
watch(organizationId, (id) => id && void founderPrescreen.load(id), { immediate: true })
const isStartup = computed(() => founderPrescreen.state[organizationId.value]?.segment === 'startup')

const productTitle = (code: string) => props.products?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <!-- Исключили из открытой компании: почему она пропала — и над другой компанией, и над пустым состоянием -->
  <p v-if="accessLost" class="mb-6 flex items-start gap-2 rounded-2xl bg-warning-soft p-3 text-sm text-ink" role="alert">
    <CircleAlert class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
    {{ accessLost }}
  </p>
  <AsyncState
    :loading="loading && !detail"
    :error="detail ? null : error"
    :empty="!loading && !detail && !error && !organizations.length"
    empty-text="Вы больше не участник ни одной компании — кабинет компании откроется, когда руководитель добавит вас снова"
    @retry="company.loadOrganizations"
  >
    <div v-if="detail" class="space-y-8">
      <SelectField v-if="organizationOptions.length > 1" v-model="organizationId" label="Компания" :options="organizationOptions" />

      <p v-if="notice" class="flex items-center gap-2 rounded-2xl bg-success-soft p-3 text-sm text-ink" role="status">
        <CircleCheck class="size-4 shrink-0 text-success" aria-hidden="true" />
        {{ notice }}
      </p>
      <p v-if="actionError" class="rounded-2xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ actionError }}</p>

      <CompanyRequisites :company="detail" :verification="verification" :verifying="busy === 'verify'" @verify="company.verify" />
      <template v-if="isStartup">
        <FounderPrescreenPanel :organization-id="detail.id" />
        <StartupProject
          :organization-id="detail.id"
          :can-edit="canEditFinancials"
          :can-submit="canSubmit"
          @apply="(code, maxAmount) => emit('applyProduct', code, detail!.id, maxAmount)"
        />
      </template>
      <!-- Без права подачи заявки бэкенд предодобрение не отдаёт — и блок не показываем -->
      <PreApprovedOffers
        v-else-if="canSubmit"
        :offers="preApproved"
        :verified="detail.verification.status === 'verified'"
        :product-title="productTitle"
        @apply="(code, maxAmount) => emit('applyProduct', code, detail!.id, maxAmount)"
      />
      <FinancialReports
        :reports="reports"
        :can-edit="canEditFinancials"
        :busy="busy === 'report'"
        @submit="async (input, done) => (await company.submitReport(input)) && done()"
      />
      <CompanyMembers
        :members="members"
        :can-manage="canManageMembers"
        :busy="busy"
        :poa-error="company.poaError.value"
        :member-error="company.memberError.value"
        @add="async (login, role, done) => (await company.addMember(login, role)) && done()"
        @grant="async (accountId, input, done) => (await company.grantPowerOfAttorney(accountId, input)) && done()"
        @revoke="async (accountId, done) => (await company.revokePowerOfAttorney(accountId)) && done()"
        @change-role="company.changeMemberRole"
        @remove="company.removeMember"
      />
    </div>
  </AsyncState>
</template>
