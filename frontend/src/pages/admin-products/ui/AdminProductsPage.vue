<script setup lang="ts">
import { useSession } from '@/entities/session'
import { ProductSettingsForm } from '@/features/edit-product'
import { creditApi, type ProductSettings } from '@/shared/api'
import { useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

const { can } = useSession()

const products = useAsyncData(() => creditApi.listProducts())

function onSaved(saved: ProductSettings) {
  products.data.value = (products.data.value ?? []).map((item) => (item.id === saved.id ? saved : item))
}
</script>

<template>
  <AdminPageHeader
    title="Продукты"
    description="Условия кредитных продуктов: по ним проверяем параметры заявки и считаем ставку решения"
  />

  <AsyncState :loading="products.loading.value" :error="products.error.value" @retry="products.reload">
    <p v-if="!can('credits.update')" class="mb-4 rounded-xl bg-white px-4 py-3 text-sm text-ink-secondary ring-1 ring-line">
      Только просмотр: менять условия может руководитель или администратор.
    </p>
    <div class="grid gap-6 lg:grid-cols-2">
      <PanelCard v-for="product in products.data.value ?? []" :key="product.id" :title="product.title">
        <template #actions>
          <BaseBadge :tone="product.active ? 'success' : 'neutral'">{{ product.active ? 'Активен' : 'Выключен' }}</BaseBadge>
        </template>
        <ProductSettingsForm :product="product" :readonly="!can('credits.update')" @saved="onSaved" />
      </PanelCard>
    </div>
  </AsyncState>
</template>
