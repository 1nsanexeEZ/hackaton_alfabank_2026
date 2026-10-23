<script setup lang="ts">
import {
  BadgeCheck,
  Building,
  Calculator,
  CircleAlert,
  CircleX,
  FileCheck,
  RefreshCw,
  Rocket,
  Truck,
  Wallet,
  Waves,
  Wrench,
  type LucideIcon,
} from 'lucide-vue-next'
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'

import { PURPOSE_LABEL, useRecommendations, type ProductCatalog, type ProductRecommendation } from '@/entities/credit-product'
import { customer } from '@/entities/customer'
import { clientApi, type LoanPurpose, type OrganizationSummaryDto } from '@/shared/api'
import { formatMoney, formatMoneyShort, formatTerm } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, RangeField, SelectField } from '@/shared/ui'

/**
 * Подбор кредита под задачу: цель, сумма и срок → продукты по порядку с объяснением, почему подходят
 * или что поменять. Вошедшему — ещё проверка его компании и предварительно одобренный максимум.
 */
const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  apply: [params: { productCode: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId?: string }]
  calculate: [params: { productCode: string; amount: number; termMonths: number }]
}>()

const PURPOSES: readonly { value: LoanPurpose; icon: LucideIcon }[] = [
  { value: 'working_capital', icon: Wallet },
  { value: 'cash_gap', icon: Waves },
  { value: 'equipment', icon: Wrench },
  { value: 'vehicles', icon: Truck },
  { value: 'real_estate', icon: Building },
  { value: 'contract_execution', icon: FileCheck },
  { value: 'refinancing', icon: RefreshCw },
  { value: 'expansion', icon: Rocket },
]

const bounds = computed(() => ({
  amountMin: Math.min(...props.products.map((product) => product.amount.min)),
  amountMax: Math.max(...props.products.map((product) => product.amount.max)),
  termMin: Math.min(...props.products.map((product) => product.termMonths.min)),
  termMax: Math.max(...props.products.map((product) => product.termMonths.max)),
}))

const need = reactive({ purpose: 'working_capital' as LoanPurpose, amount: 3_000_000, termMonths: 24 })

// Вошёл — подбираем ещё и для его компании
const organizations = shallowRef<OrganizationSummaryDto[]>([])
const organizationId = ref('')

async function loadOrganizations() {
  if (!customer.state.token) {
    organizations.value = []
    organizationId.value = ''
    return
  }
  try {
    organizations.value = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
    if (!organizations.value.some((item) => item.id === organizationId.value)) organizationId.value = organizations.value[0]?.id ?? ''
  } catch {
    organizations.value = []
  }
}

onMounted(loadOrganizations)
watch(() => customer.state.me?.id, loadOrganizations)

const { items, loading, error } = useRecommendations(() => ({ ...need, organizationId: organizationId.value || null }))

const organizationOptions = computed(() => organizations.value.map((item) => ({ value: item.id, label: item.name })))
const title = (code: string) => props.products.find((product) => product.code === code)?.title ?? code

const STATUS: Record<ProductRecommendation['status'], { label: string; tone: 'success' | 'warning' | 'neutral' }> = {
  available: { label: 'Подходит', tone: 'success' },
  needs_adjustment: { label: 'Если поменять условия', tone: 'warning' },
  unavailable: { label: 'Не подходит', tone: 'neutral' },
}

/** Продукт подходит задаче, но не компании — это важнее, показываем так */
const badge = (item: ProductRecommendation) =>
  item.eligible === false ? { label: 'Вашей компании не подходит', tone: 'neutral' as const } : STATUS[item.status]

function payment(item: ProductRecommendation) {
  return item.paymentFrom === item.paymentTo
    ? formatMoney(item.paymentFrom)
    : `${formatMoney(item.paymentFrom)} – ${formatMoney(item.paymentTo)}`
}

function apply(item: ProductRecommendation) {
  emit('apply', {
    productCode: item.code,
    amount: item.amount,
    termMonths: item.termMonths,
    purpose: need.purpose,
    organizationId: organizationId.value || undefined,
  })
}
</script>

<template>
  <div class="grid gap-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-10">
    <div class="space-y-6">
      <fieldset>
        <legend class="mb-3 text-sm font-medium text-ink">Для чего нужны деньги</legend>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="purpose in PURPOSES"
            :key="purpose.value"
            type="button"
            class="flex min-h-14 items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm font-medium transition-colors"
            :class="need.purpose === purpose.value ? 'bg-brand text-white' : 'bg-surface text-ink hover:bg-surface-strong'"
            :aria-pressed="need.purpose === purpose.value"
            @click="need.purpose = purpose.value"
          >
            <component :is="purpose.icon" class="size-5 shrink-0" aria-hidden="true" />
            {{ PURPOSE_LABEL[purpose.value] }}
          </button>
        </div>
      </fieldset>

      <RangeField
        v-model="need.amount"
        label="Сумма"
        :min="bounds.amountMin"
        :max="bounds.amountMax"
        :step="100_000"
        :format-value="formatMoney"
      />
      <RangeField
        v-model="need.termMonths"
        label="Срок"
        :min="bounds.termMin"
        :max="bounds.termMax"
        :step="3"
        :format-value="formatTerm"
        :editable="false"
      />

      <SelectField
        v-if="organizationOptions.length > 1"
        v-model="organizationId"
        label="Подбираем для компании"
        :options="organizationOptions"
      />
      <p v-else-if="!organizationOptions.length" class="text-sm text-ink-secondary">
        Войдите — проверим, подходит ли продукт вашей компании, и покажем предварительно одобренную сумму.
      </p>
    </div>

    <div aria-live="polite">
      <AsyncState :loading="loading && !items" :error="items ? null : error">
        <p v-if="items && !items.length" class="rounded-2xl bg-surface-soft p-6 text-sm text-ink-secondary">
          Под эту цель продуктов нет — выберите другую цель или посмотрите каталог ниже.
        </p>
        <ol v-else-if="items" class="space-y-3 transition-opacity" :class="loading && 'opacity-60'">
          <li v-for="item in items" :key="item.code" class="rounded-2xl bg-surface-soft p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-xs font-medium text-ink-muted">{{ item.rank }} место</p>
                <p class="mt-0.5 text-lg font-bold text-ink">{{ title(item.code) }}</p>
              </div>
              <BaseBadge :tone="badge(item).tone">{{ badge(item).label }}</BaseBadge>
            </div>

            <p class="mt-2 text-sm text-ink">
              Платёж {{ payment(item) }} в месяц
              <span class="text-ink-secondary">· {{ formatMoneyShort(item.amount) }} на {{ formatTerm(item.termMonths) }}</span>
            </p>

            <ul v-if="item.adjustments.length" class="mt-3 space-y-1 text-sm text-warning">
              <li v-for="hint in item.adjustments" :key="hint" class="flex items-start gap-2">
                <CircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {{ hint }}
              </li>
            </ul>

            <template v-if="item.eligible !== null">
              <p v-if="item.eligible" class="mt-3 flex items-center gap-2 text-sm text-success">
                <BadgeCheck class="size-4 shrink-0" aria-hidden="true" />
                {{
                  item.preApprovedMax
                    ? `Ваша компания подходит · предварительно одобрено до ${formatMoney(item.preApprovedMax)}`
                    : 'Ваша компания подходит'
                }}
              </p>
              <ul v-else class="mt-3 space-y-1 text-sm text-brand">
                <li v-for="reason in item.notEligibleReasons" :key="reason" class="flex items-start gap-2">
                  <CircleX class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  {{ reason }}
                </li>
              </ul>
            </template>

            <div class="mt-4 flex flex-wrap gap-2">
              <BaseButton size="s" :disabled="item.status === 'unavailable' || item.eligible === false" @click="apply(item)">
                Оформить
              </BaseButton>
              <BaseButton
                size="s"
                variant="secondary"
                @click="emit('calculate', { productCode: item.code, amount: item.amount, termMonths: item.termMonths })"
              >
                <Calculator class="size-4" aria-hidden="true" />
                Рассчитать
              </BaseButton>
            </div>
          </li>
        </ol>
      </AsyncState>
    </div>
  </div>
</template>
