<script setup lang="ts">
import { BellRing, ChevronLeft, ChevronRight, UserCheck } from 'lucide-vue-next'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import {
  ACTION_REQUIRED_LABEL,
  ApplicationStatusCard,
  clientStages,
  isActiveApplication,
  myApplications,
  type ApplicationDraft,
  type ApplicationPreview,
} from '@/entities/application'
import type { CreditProduct } from '@/entities/credit-product'
import { customer, personalConsents, useCustomer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { BaseButton } from '@/shared/ui'

import { HERO_DEMO_APPLICATION } from '../model/content'

/**
 * Карточка заявки на первом экране. Не вошёл — пример, как выглядит заявка в кабинете.
 * Вошёл — его активные заявки (свежая первой, остальные — переключателем); нет ни одной —
 * затемнённый пример с предложением оформить заявку.
 */
const props = defineProps<{ products: readonly CreditProduct[] | null }>()

const emit = defineEmits<{ apply: []; continue: [draft: ApplicationDraft]; open: [applicationId: string] }>()

const { me } = useCustomer()
const { state } = myApplications

// Вошёл другой клиент — грузим его заявки, вышел — убираем
watch(
  () => me.value?.id,
  (id) => (id ? void myApplications.load() : myApplications.clear()),
  { immediate: true },
)

// Банк поменял заявку (этап, решение, запрос) — статус на карточке меняется сам, без перезагрузки
const stopLive = liveFeed.onApplication(() => {
  void myApplications.refresh()
  void personalConsents.loadReminders()
})
onBeforeUnmount(stopLive)

/** На первом экране — только заявки в работе; закрытые видны в «Моих заявках» */
const active = computed(() => state.items?.filter(isActiveApplication) ?? null)

const index = ref(0)
// Список перезагрузили (например, после мастера заявки) — показываем самую свежую
watch(active, () => (index.value = 0))

const mode = computed<'example' | 'loading' | 'error' | 'empty' | 'list'>(() => {
  // Токен есть, а профиль ещё не подтянулся — это не «не вошёл», пример не показываем
  if (!customer.state.token) return 'example'
  if (active.value?.length) return 'list'
  if (active.value) return 'empty'
  return state.error ? 'error' : 'loading'
})

const count = computed(() => active.value?.length ?? 0)
const current = computed(() => active.value?.[index.value] ?? null)

/** Банк ждёт согласие руководителя на его БКИ по этой заявке — пункт consent_required из дашборда */
const needsConsent = computed(() =>
  Boolean(current.value && personalConsents.state.reminders.some((item) => item.applicationId === current.value!.id)),
)

const productOf = (code: string) => props.products?.find((product) => product.code === code)

const preview = computed<ApplicationPreview | null>(() => {
  const item = current.value
  if (!item) return null
  const status = item.client_status
  return {
    number: item.number,
    productTitle: item.product_name || productOf(item.product_code)?.title || item.product_code,
    organizationName: item.organization_name,
    amount: item.amount === null ? null : Number(item.amount),
    termMonths: item.term_months,
    status,
    stages: clientStages(status, item.submitted_at),
  }
})

function continueDraft() {
  const item = current.value
  const product = item && productOf(item.product_code)
  if (!item || !product) return
  emit('continue', {
    productId: product.id,
    amount: item.amount === null ? 0 : Number(item.amount),
    termMonths: item.term_months ?? 0,
    organizationId: item.organization_id,
  })
}
</script>

<template>
  <div class="relative">
    <ApplicationStatusCard
      v-if="mode === 'list' && preview"
      :application="preview"
      :label="`Ваша заявка № ${preview.number}`"
    >
      <template v-if="count > 1" #top>
        <div class="mb-4 flex items-center justify-between gap-3 text-xs text-on-night-secondary">
          <span>Ваши заявки</span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="flex size-7 items-center justify-center rounded-lg transition-colors hover:bg-white/10 disabled:opacity-40"
              aria-label="Предыдущая заявка"
              :disabled="index === 0"
              @click="index--"
            >
              <ChevronLeft class="size-4" aria-hidden="true" />
            </button>
            <span class="min-w-12 text-center tabular-nums" aria-live="polite">{{ index + 1 }} из {{ count }}</span>
            <button
              type="button"
              class="flex size-7 items-center justify-center rounded-lg transition-colors hover:bg-white/10 disabled:opacity-40"
              aria-label="Следующая заявка"
              :disabled="index === count - 1"
              @click="index++"
            >
              <ChevronRight class="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </template>
      <template #footer>
        <p
          v-if="needsConsent"
          class="mt-5 flex items-center gap-2 rounded-xl bg-brand/15 px-3 py-2 text-sm font-medium text-on-night"
        >
          <UserCheck class="size-4 shrink-0 text-brand" aria-hidden="true" />
          Нужно ваше согласие на запрос кредитной истории
        </p>
        <p
          v-else-if="current && ACTION_REQUIRED_LABEL[current.action_required]"
          class="mt-5 flex items-center gap-2 rounded-xl bg-brand/15 px-3 py-2 text-sm font-medium text-on-night"
        >
          <BellRing class="size-4 shrink-0 text-brand" aria-hidden="true" />
          {{ ACTION_REQUIRED_LABEL[current.action_required] }}
        </p>
        <BaseButton v-if="preview.status === 'draft'" block class="mt-6" @click="continueDraft">
          Продолжить заявку
        </BaseButton>
        <BaseButton v-else-if="current" block variant="glass" class="mt-6" @click="emit('open', current.id)">
          Подробнее о заявке
        </BaseButton>
      </template>
    </ApplicationStatusCard>

    <template v-else>
      <ApplicationStatusCard
        :application="HERO_DEMO_APPLICATION"
        :class="mode !== 'example' && 'pointer-events-none opacity-40 blur-[2px] select-none'"
        :aria-hidden="mode !== 'example' || undefined"
      />
      <div
        v-if="mode !== 'example'"
        class="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-card bg-night/50 p-6 text-center"
      >
        <template v-if="mode === 'empty'">
          <p class="text-lg font-semibold">Активных заявок нет</p>
          <p class="text-sm text-on-night-secondary">Здесь появится статус вашей заявки</p>
          <BaseButton class="mt-3" @click="emit('apply')">Оформить заявку</BaseButton>
        </template>
        <template v-else-if="mode === 'error'">
          <p class="text-lg font-semibold">Не удалось загрузить заявки</p>
          <p class="text-sm text-on-night-secondary">{{ state.error }}</p>
          <BaseButton variant="glass" class="mt-3" @click="myApplications.load()">Повторить</BaseButton>
        </template>
        <p v-else class="flex items-center gap-2 text-sm text-on-night-secondary" role="status">
          <span class="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
          Загружаем ваши заявки…
        </p>
      </div>
    </template>
  </div>
</template>
