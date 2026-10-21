<script setup lang="ts">
import { AlarmClock, Phone, UserRound } from 'lucide-vue-next'
import { computed, watch } from 'vue'

import { ApplicationStatusBadge, ApplicationTimeline, isOverdue, ScoreBreakdown } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS, findProduct } from '@/entities/credit-product'
import { DecisionPanel } from '@/features/decide-application'
import { creditApi, type ApplicationDetails } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatDateTime, formatMoney, formatRelativeTime, formatTerm, useAsyncData } from '@/shared/lib'
import { AsyncState, PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { CounterpartyDossier } from '@/widgets/counterparty-dossier'

const props = defineProps<{ id: string }>()

const application = useAsyncData(() => creditApi.getApplication(props.id))
watch(() => props.id, application.reload)

const item = computed(() => application.data.value)
const product = computed(() => (item.value ? findProduct(DEMO_CREDIT_PRODUCTS, item.value.productId) : null))

const summary = computed(() => {
  if (!item.value || !product.value) return []
  return [
    ['Продукт', product.value.title],
    ['Сумма', formatMoney(item.value.amount)],
    ['Срок', formatTerm(item.value.termMonths)],
    ['Цель', item.value.purpose],
    ['Подана', formatDateTime(item.value.createdAt)],
    ['Решение до', formatDateTime(item.value.dueAt)],
  ]
})

function onUpdated(next: ApplicationDetails) {
  application.data.value = next
}
</script>

<template>
  <AsyncState :loading="application.loading.value" :error="application.error.value" @retry="application.reload">
    <template v-if="item">
      <AdminPageHeader
        :title="item.applicantName"
        :back="{ name: ADMIN_ROUTE.applications }"
        back-label="Все заявки"
      >
        <template #meta>
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-secondary">
            <ApplicationStatusBadge :status="item.status" />
            <span>Заявка {{ item.number }}</span>
            <span class="tabular-nums">ИНН {{ item.inn }}</span>
            <span v-if="isOverdue(item)" class="flex items-center gap-1 font-medium text-warning">
              <AlarmClock class="size-4" aria-hidden="true" />
              SLA истёк {{ formatRelativeTime(item.dueAt) }}
            </span>
          </div>
        </template>
      </AdminPageHeader>

      <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div class="min-w-0 space-y-6">
          <PanelCard title="Параметры заявки">
            <dl class="grid gap-x-6 gap-y-4 sm:grid-cols-3">
              <div v-for="[label, value] in summary" :key="label">
                <dt class="text-xs text-ink-secondary">{{ label }}</dt>
                <dd class="mt-0.5 font-semibold text-ink">{{ value }}</dd>
              </div>
            </dl>
          </PanelCard>

          <PanelCard title="Скоринг" :description="item.score ? `Рассчитан ${formatDateTime(item.score.calculatedAt)}` : undefined">
            <ScoreBreakdown v-if="item.score" :score="item.score" />
            <p v-else class="text-sm text-ink-secondary">Скоринг появится после автоматических проверок.</p>
          </PanelCard>

          <div>
            <h2 class="mb-3 text-lg font-bold text-ink">Внешние проверки</h2>
            <CounterpartyDossier v-if="item.dossier" :dossier="item.dossier" />
            <PanelCard v-else>
              <p class="text-sm text-ink-secondary">Компания с этим ИНН не найдена во внешних источниках.</p>
            </PanelCard>
          </div>
        </div>

        <aside class="space-y-6 xl:sticky xl:top-8">
          <PanelCard title="Действия">
            <DecisionPanel :application="item" @updated="onUpdated" />
          </PanelCard>

          <PanelCard title="Контакт">
            <ul class="space-y-2 text-sm text-ink">
              <li class="flex items-center gap-2">
                <UserRound class="size-4 text-ink-secondary" aria-hidden="true" />
                {{ item.contactName }}
              </li>
              <li class="flex items-center gap-2">
                <Phone class="size-4 text-ink-secondary" aria-hidden="true" />
                <a :href="`tel:${item.contactPhone.replace(/[^+\d]/g, '')}`" class="hover:underline">{{ item.contactPhone }}</a>
              </li>
            </ul>
          </PanelCard>

          <PanelCard title="История">
            <ApplicationTimeline :history="item.history" />
          </PanelCard>
        </aside>
      </div>
    </template>
  </AsyncState>
</template>
