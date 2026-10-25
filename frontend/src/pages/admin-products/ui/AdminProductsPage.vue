<script setup lang="ts">
import { Pencil, Plus, Rocket, Undo2, XCircle } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { COLLATERAL_LABEL, LEGAL_FORM_LABEL, PRODUCT_STATUS_META } from '@/entities/credit-product'
import { workflowTitle } from '@/entities/process'
import { useSession } from '@/entities/session'
import { ProductEditorModal, ProductStatusModal } from '@/features/edit-product'
import { backofficeApi, type ProductDto, type ProductStatus } from '@/shared/api'
import { formatMoney, formatPercent, formatTerm, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

/**
 * Каталог продуктов на бэкенде (PR #200). Ведёт каталог тот, у кого есть credits.update: ему —
 * все версии с черновиками и архивом (GET /products/all). Остальным — продукты в продаже, только просмотр.
 */
const { can } = useSession()
const canManage = computed(() => can('credits.update'))

const products = useAsyncData(() => backofficeApi.products(canManage.value ? 'all' : 'active'))
const workflows = useAsyncData(() => (canManage.value ? backofficeApi.workflows() : Promise.resolve([])))

type Filter = 'all' | ProductStatus
const filter = ref<Filter>('all')
const counts = computed(() => {
  const list = products.data.value ?? []
  return {
    all: list.length,
    active: list.filter((product) => product.status === 'active').length,
    draft: list.filter((product) => product.status === 'draft').length,
    archived: list.filter((product) => product.status === 'archived').length,
  }
})
const FILTERS = computed(() =>
  (
    [
      { value: 'all', label: 'Все' },
      { value: 'active', label: 'В продаже' },
      { value: 'draft', label: 'Черновики' },
      { value: 'archived', label: 'Сняты' },
    ] as const
  ).map((item) => ({ value: item.value as Filter, label: `${item.label} · ${counts.value[item.value]}` })),
)
const visible = computed(() =>
  (products.data.value ?? []).filter((product) => filter.value === 'all' || product.status === filter.value),
)

const editing = ref<ProductDto | null>(null)
const isEditorOpen = ref(false)
const changing = ref<ProductDto | null>(null)
const statusAction = ref<'activate' | 'withdraw'>('withdraw')
const isStatusOpen = ref(false)

function openCreate() {
  editing.value = null
  isEditorOpen.value = true
}

function openEdit(product: ProductDto) {
  editing.value = product
  isEditorOpen.value = true
}

function openStatus(product: ProductDto, action: 'activate' | 'withdraw') {
  changing.value = product
  statusAction.value = action
  isStatusOpen.value = true
}

/** Новая версия заменяет прежнюю в списке, новый продукт встаёт в конец каталога */
function onSaved(saved: ProductDto) {
  const list = products.data.value ?? []
  products.data.value = list.some((item) => item.code === saved.code)
    ? list.map((item) => (item.code === saved.code ? saved : item))
    : [...list, saved]
}

function onStatusChanged(code: string, product: ProductDto | null) {
  const list = products.data.value ?? []
  products.data.value = product ? list.map((item) => (item.code === code ? product : item)) : list.filter((item) => item.code !== code)
}

const range = (min: string, max: string) => `${formatMoney(Number(min))} – ${formatMoney(Number(max))}`
const rate = (product: ProductDto) =>
  product.rate_base === product.rate_max
    ? formatPercent(Number(product.rate_base))
    : `${formatPercent(Number(product.rate_base))} – ${formatPercent(Number(product.rate_max))}`
const forms = (product: ProductDto) => product.allowed_legal_forms.map((form) => LEGAL_FORM_LABEL[form] ?? form).join(', ')
const autoDecision = (product: ProductDto) =>
  Number(product.auto_decision_limit) > 0 ? `до ${formatMoney(Number(product.auto_decision_limit))}` : 'всегда специалист'
</script>

<template>
  <AdminPageHeader title="Продукты" description="Каталог: условия, по которым принимаем заявки и считаем решение">
    <template v-if="can('credits.create')" #actions>
      <BaseButton size="s" :disabled="!products.data.value" @click="openCreate">
        <Plus class="size-4" aria-hidden="true" />
        Новый продукт
      </BaseButton>
    </template>
  </AdminPageHeader>

  <p v-if="!canManage" class="mb-4 rounded-xl bg-white px-4 py-3 text-sm text-ink-secondary ring-1 ring-line">
    Только просмотр продуктов в продаже: вести каталог может администратор.
  </p>

  <SegmentedControl
    v-if="canManage && products.data.value?.length"
    v-model="filter"
    :options="FILTERS"
    label="Какие продукты показать"
    small
    class="mb-4"
  />
  <AsyncState
    :loading="products.loading.value"
    :error="products.error.value"
    :empty="!visible.length"
    :empty-text="products.data.value?.length ? 'Таких продуктов нет' : 'Каталог пуст'"
    @retry="products.reload"
  >
    <div class="grid gap-6 xl:grid-cols-2">
      <PanelCard
        v-for="product in visible"
        :key="product.code"
        :title="product.name"
        :description="`${product.code} · версия ${product.version}`"
      >
        <template #actions>
          <BaseBadge :tone="PRODUCT_STATUS_META[product.status].tone">{{ PRODUCT_STATUS_META[product.status].label }}</BaseBadge>
        </template>
        <p class="text-sm text-ink-secondary">{{ product.short_description }}</p>
        <dl class="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt class="text-ink-secondary">Сумма</dt>
            <dd class="text-ink">{{ range(product.amount_min, product.amount_max) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Срок</dt>
            <dd class="text-ink">{{ formatTerm(product.term_min_months) }} – {{ formatTerm(product.term_max_months) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Ставка</dt>
            <dd class="text-ink">{{ rate(product) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Авторешение</dt>
            <dd class="text-ink">{{ autoDecision(product) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Кому</dt>
            <dd class="text-ink">{{ forms(product) }}{{ product.startup_only ? ' · только стартап' : '' }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Залог</dt>
            <dd class="text-ink">{{ COLLATERAL_LABEL[product.collateral_kind] }}</dd>
          </div>
          <div class="sm:col-span-2">
            <dt class="text-ink-secondary">Маршрут заявки</dt>
            <dd class="text-ink">{{ workflowTitle(product.workflow_code) }}</dd>
          </div>
        </dl>
        <div v-if="canManage" class="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
          <BaseButton size="s" variant="secondary" @click="openEdit(product)">
            <component :is="product.status === 'archived' ? Undo2 : Pencil" class="size-4" aria-hidden="true" />
            {{ product.status === 'archived' ? 'Вернуть в продажу' : 'Изменить условия' }}
          </BaseButton>
          <BaseButton v-if="product.status === 'draft'" size="s" variant="secondary" @click="openStatus(product, 'activate')">
            <Rocket class="size-4" aria-hidden="true" />
            Выпустить
          </BaseButton>
          <BaseButton
            v-if="product.status !== 'archived' && can('credits.delete')"
            size="s"
            variant="ghost"
            @click="openStatus(product, 'withdraw')"
          >
            <XCircle class="size-4" aria-hidden="true" />
            {{ product.status === 'draft' ? 'Удалить черновик' : 'Снять с продажи' }}
          </BaseButton>
        </div>
      </PanelCard>
    </div>
  </AsyncState>

  <ProductEditorModal
    v-model:open="isEditorOpen"
    :product="editing"
    :catalog="products.data.value ?? []"
    :workflows="workflows.data.value ?? []"
    @saved="onSaved"
  />
  <ProductStatusModal v-model:open="isStatusOpen" :product="changing" :action="statusAction" @changed="onStatusChanged" />
</template>
