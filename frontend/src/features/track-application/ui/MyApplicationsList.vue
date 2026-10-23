<script setup lang="ts">
import { BellRing, ChevronRight, FilePlus2 } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import {
  ACTION_REQUIRED_LABEL,
  CLIENT_STATUS_META,
  isActiveApplication,
  myApplications,
} from '@/entities/application'
import { useProductCatalog } from '@/entities/credit-product'
import { formatDateTime, formatMoney, formatTerm } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, SegmentedControl } from '@/shared/ui'

/** Все заявки клиента по его компаниям: в работе и закрытые, с тем, что ждёт банк */
const emit = defineEmits<{ open: [applicationId: string]; apply: [] }>()

const { state } = myApplications

// Список мог устареть (заявку подали в другой вкладке) — перечитываем при каждом открытии
onMounted(() => void myApplications.load())

const filter = ref<'active' | 'all'>('active')
const FILTERS = [
  { value: 'active', label: 'В работе' },
  { value: 'all', label: 'Все' },
] as const

// У черновиков нет названия продукта из BFF — берём из каталога
const { products } = useProductCatalog()
const productName = (item: { product_name: string; product_code: string }) =>
  item.product_name || products.value?.find((product) => product.code === item.product_code)?.title || item.product_code

const items = computed(() => (state.items ?? []).filter((item) => filter.value === 'all' || isActiveApplication(item)))
const companies = computed(() => new Set((state.items ?? []).map((item) => item.organization_id)).size)
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <SegmentedControl v-model="filter" :options="FILTERS" label="Какие заявки показать" small />
      <BaseButton size="s" variant="secondary" @click="emit('apply')">
        <FilePlus2 class="size-4" aria-hidden="true" />
        Новая заявка
      </BaseButton>
    </div>

    <AsyncState :loading="!state.items && !state.error" :error="state.items ? null : state.error" @retry="myApplications.load">
      <p v-if="!items.length" class="rounded-2xl bg-surface-soft p-6 text-center text-sm text-ink-secondary">
        {{ filter === 'active' ? 'Активных заявок нет' : 'Заявок пока нет' }}
      </p>
      <ul v-else class="space-y-2">
        <li v-for="item in items" :key="item.id">
          <button
            type="button"
            class="flex w-full items-center gap-4 rounded-2xl bg-surface-soft p-4 text-left transition-colors hover:bg-surface"
            @click="emit('open', item.id)"
          >
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="font-semibold text-ink">{{ productName(item) }}</p>
                <BaseBadge :tone="CLIENT_STATUS_META[item.client_status].tone">
                  {{ CLIENT_STATUS_META[item.client_status].label }}
                </BaseBadge>
              </div>
              <p class="mt-1 text-sm text-ink-secondary">
                № {{ item.number }}
                <template v-if="item.amount"> · {{ formatMoney(Number(item.amount)) }}</template>
                <template v-if="item.term_months"> · {{ formatTerm(item.term_months) }}</template>
                <template v-if="companies > 1"> · {{ item.organization_name }}</template>
              </p>
              <p v-if="ACTION_REQUIRED_LABEL[item.action_required]" class="mt-2 flex items-center gap-1.5 text-sm font-medium text-brand">
                <BellRing class="size-4" aria-hidden="true" />
                {{ ACTION_REQUIRED_LABEL[item.action_required] }}
              </p>
              <p v-else-if="item.client_stage" class="mt-1 text-xs text-ink-secondary">{{ item.client_stage }}</p>
            </div>
            <div class="flex shrink-0 flex-col items-end gap-1">
              <span class="text-xs text-ink-muted">{{ formatDateTime(item.updated_at) }}</span>
              <ChevronRight class="size-5 text-ink-muted" aria-hidden="true" />
            </div>
          </button>
        </li>
      </ul>
    </AsyncState>
  </div>
</template>
