<script setup lang="ts">
import { CircleCheck } from 'lucide-vue-next'
import { computed, onMounted } from 'vue'

import type { ProductCatalog } from '@/entities/credit-product'
import { AsyncState, SelectField } from '@/shared/ui'

import { useCompany } from '../model/useCompany'
import CompanyMembers from './CompanyMembers.vue'
import CompanyRequisites from './CompanyRequisites.vue'
import FinancialReports from './FinancialReports.vue'
import PreApprovedOffers from './PreApprovedOffers.vue'

/** Компания клиента: реквизиты, предодобрение, отчётность, участники */
const props = defineProps<{ products: ProductCatalog | null }>()

const emit = defineEmits<{ applyProduct: [code: string, organizationId: string, maxAmount: number] }>()

const company = useCompany()
const { organizations, organizationId, detail, reports, preApproved, members, loading, error, busy, actionError, notice, canEditFinancials, canManageMembers } =
  company

onMounted(() => void company.loadOrganizations())

const organizationOptions = computed(() => organizations.value.map((item) => ({ value: item.id, label: `${item.name} · ИНН ${item.inn}` })))
const productTitle = (code: string) => props.products?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <AsyncState :loading="loading && !detail" :error="detail ? null : error" @retry="company.loadOrganizations">
    <div v-if="detail" class="space-y-8">
      <SelectField v-if="organizationOptions.length > 1" v-model="organizationId" label="Компания" :options="organizationOptions" />

      <p v-if="notice" class="flex items-center gap-2 rounded-2xl bg-success-soft p-3 text-sm text-ink" role="status">
        <CircleCheck class="size-4 shrink-0 text-success" aria-hidden="true" />
        {{ notice }}
      </p>
      <p v-if="actionError" class="rounded-2xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ actionError }}</p>

      <CompanyRequisites :company="detail" />
      <PreApprovedOffers
        :offers="preApproved"
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
        @add="async (login, role, done) => (await company.addMember(login, role)) && done()"
        @grant="async (accountId, input, done) => (await company.grantPowerOfAttorney(accountId, input)) && done()"
      />
    </div>
  </AsyncState>
</template>
