<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { APPLICATION_STATUS_META } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS } from '@/entities/credit-product'
import { creditApi, type ApplicationFilters, type ApplicationStatus } from '@/shared/api'
import { useAsyncData } from '@/shared/lib'
import { AsyncState, PanelCard, SegmentedControl, SelectField } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { ApplicationsTable } from '@/widgets/applications-table'

type StatusFilter = 'active' | 'all' | ApplicationStatus

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: 'active', label: 'В работе' },
  { value: 'info_requested', label: 'Ждут клиента' },
  { value: 'approved', label: 'Одобрены' },
  { value: 'signing', label: 'Подписание' },
  { value: 'rejected', label: 'Отказы' },
  { value: 'all', label: 'Все' },
]

const STATUS_OPTIONS = [
  { value: 'all' as StatusFilter, label: 'Все статусы' },
  { value: 'active' as StatusFilter, label: 'В работе' },
  ...(Object.keys(APPLICATION_STATUS_META) as ApplicationStatus[])
    .filter((status) => status !== 'draft')
    .map((status) => ({ value: status as StatusFilter, label: APPLICATION_STATUS_META[status].label })),
]

const PRODUCT_OPTIONS = [
  { value: 'all', label: 'Все продукты' },
  ...DEMO_CREDIT_PRODUCTS.map((product) => ({ value: product.id, label: product.title })),
]

const route = useRoute()
const router = useRouter()

// Фильтры живут в адресе: ссылкой на отфильтрованный список можно поделиться
const filters = reactive({
  status: (route.query.status as StatusFilter) || 'active',
  product: (route.query.product as string) || 'all',
  search: (route.query.q as string) || '',
})

const list = useAsyncData(() => {
  const query: ApplicationFilters = {
    status: filters.status === 'all' ? undefined : filters.status,
    productId: filters.product === 'all' ? undefined : filters.product,
    search: filters.search || undefined,
  }
  return creditApi.listApplications(query)
})

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => ({ ...filters }),
  (next, prev) => {
    void router.replace({
      query: {
        status: next.status === 'active' ? undefined : next.status,
        product: next.product === 'all' ? undefined : next.product,
        q: next.search || undefined,
      },
    })
    clearTimeout(searchTimer)
    searchTimer = setTimeout(list.reload, next.search !== prev.search ? 250 : 0)
  },
)
</script>

<template>
  <AdminPageHeader title="Заявки" description="Рассмотрение кредитных заявок: проверки, скоринг и решение" />

  <PanelCard flush>
    <div class="flex flex-col gap-3 border-b border-line p-4 xl:flex-row xl:items-center xl:justify-between">
      <SegmentedControl v-model="filters.status" :options="STATUS_TABS" label="Статус заявки" class="max-xl:hidden" />
      <SelectField v-model="filters.status" :options="STATUS_OPTIONS" label="Статус" hide-label dense class="xl:hidden" />
      <div class="flex flex-col gap-3 sm:flex-row">
        <SelectField v-model="filters.product" :options="PRODUCT_OPTIONS" label="Продукт" hide-label dense class="sm:w-52" />
        <label class="relative block sm:w-72">
          <span class="sr-only">Поиск</span>
          <Search class="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-secondary" aria-hidden="true" />
          <input
            v-model="filters.search"
            type="search"
            placeholder="Номер, ИНН или название"
            class="h-11 w-full rounded-lg bg-surface pr-4 pl-10 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20"
          />
        </label>
      </div>
    </div>

    <AsyncState
      :loading="list.loading.value && !list.data.value"
      :error="list.error.value"
      :empty="!list.data.value?.length"
      empty-text="Заявок с такими условиями нет"
      @retry="list.reload"
    >
      <ApplicationsTable :items="list.data.value ?? []" :class="list.loading.value && 'opacity-60'" />
    </AsyncState>
  </PanelCard>
</template>
