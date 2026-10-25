<script setup lang="ts">
import { BadgeCheck, Building2, CircleAlert, Sparkles } from 'lucide-vue-next'
import { computed, shallowRef, watch } from 'vue'

import {
  amountStep,
  PURPOSE_LABEL,
  termStep,
  useLoanSchedule,
  useRecommendations,
  type ProductCatalog,
  type ProductRecommendation,
} from '@/entities/credit-product'
import { founderPrescreen, FounderPrescreenPanel, projectApproved } from '@/entities/customer'
import { clientApi, type LoanPurpose, type OrganizationDetailDto } from '@/shared/api'
import { clamp, formatMoney, formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'
import { AnimatedNumber, RangeField, SelectField, TextField } from '@/shared/ui'

import type { ApplicationWizard } from '../model/useApplicationWizard'

/**
 * Шаг «Условия» начинается с подбора: компания и цель → продукты под эту цель (с проверкой компании
 * и предодобрением) → выбранный продукт, сумма, срок. Подбор — тот же, что на лендинге.
 */
const props = defineProps<{ wizard: ApplicationWizard; products: ProductCatalog }>()

const { terms, organizations, organization, product, fieldErrors, ineligibleReason, allowedProducts, isStartup, companyInfo } = props.wizard

const organizationOptions = computed(() =>
  (organizations.value ?? []).map((item) => ({ value: item.id, label: `${item.name} · ИНН ${item.inn}` })),
)
// Стартапу — только продукты для стартапа, действующему бизнесу — без них
const productOptions = computed(() => allowedProducts.value.map((item) => ({ value: item.id, label: item.title })))

// Компания сменилась или пришли из каталога с недоступным ей продуктом — берём первый доступный
watch(
  [companyInfo, allowedProducts],
  ([info, allowed]) => {
    if (!info || !allowed.length) return
    if (!allowed.some((item) => item.id === terms.productId)) terms.productId = allowed[0]!.id
  },
  { immediate: true },
)
// Цель выбирают первой — поэтому все цели, а не только цели текущего продукта
const purposeOptions = (Object.keys(PURPOSE_LABEL) as LoanPurpose[]).map((value) => ({ value, label: PURPOSE_LABEL[value] }))

const purpose = computed({
  get: () => terms.purpose as LoanPurpose,
  set: (value: LoanPurpose) => (terms.purpose = value),
})

const { items: recommended } = useRecommendations(() =>
  terms.purpose
    ? {
        purpose: terms.purpose as LoanPurpose,
        amount: terms.amount,
        termMonths: terms.termMonths,
        organizationId: terms.organizationId || null,
      }
    : null,
)

const productByCode = (code: string) => props.products.find((item) => item.code === code)

/** Подходящие под цель и под сегмент компании (стартапу — только продукты для стартапа) — сначала те, что ей подходят */
const suggestions = computed(() =>
  (recommended.value ?? [])
    .filter((item) => item.status !== 'unavailable' && allowedProducts.value.some((product) => product.code === item.code))
    .sort((a, b) => Number(b.eligible !== false) - Number(a.eligible !== false) || a.rank - b.rank)
    .slice(0, 4),
)

function choose(item: ProductRecommendation) {
  const next = productByCode(item.code)
  if (next) terms.productId = next.id
}

// Выбрали цель, под которую текущий продукт не подходит, — берём первый подходящий из подбора
watch(suggestions, (list) => {
  const first = list.find((item) => item.eligible !== false) ?? list[0]
  if (first && !product.value.purposes.includes(terms.purpose as LoanPurpose)) choose(first)
})

/** Предодобрение по выбранному продукту — из того же подбора */
const preApprovedMax = computed(() => recommended.value?.find((item) => item.code === product.value.code)?.preApprovedMax ?? null)

/** Реквизиты компании из базы банка: клиенту их не вводить; расхождение с ЕГРЮЛ — заявку посмотрит специалист */
const requisites = shallowRef<OrganizationDetailDto | null>(null)
watch(
  () => terms.organizationId,
  async (id) => {
    requisites.value = null
    if (!id) return
    try {
      const detail = await clientApi.getOrganization(id)
      if (id === terms.organizationId) requisites.value = detail
    } catch {
      // Реквизиты — подсказка: без них заявка всё равно подаётся
    }
  },
  { immediate: true },
)

const requisitesLine = computed(() => {
  const detail = requisites.value
  if (!detail) return ''
  return [`ОГРН ${detail.ogrn}`, detail.kpp && `КПП ${detail.kpp}`, detail.head_name && `руководитель — ${detail.head_name}`]
    .filter(Boolean)
    .join(', ')
})

// Платёж — по ставке предодобрения выбранной компании, как в калькуляторе на лендинге
const { schedule, personal, pending } = useLoanSchedule(() => ({
  product: product.value,
  amount: terms.amount,
  termMonths: terms.termMonths,
  organizationId: terms.organizationId || null,
}))

/**
 * До какой суммы банк готов предложить на этот срок: посильный максимум калькулятора (предодобрение,
 * платёжеспособность по отчётности или проектная оценка стартапа), пока его нет — предодобрение из подбора
 */
const limit = computed(() => {
  const value = personal.value
  if (value && value.maxAffordable !== null) return { amount: value.maxAffordable, by: value.affordableBy ?? 'pre_approved' }
  return preApprovedMax.value ? { amount: preApprovedMax.value, by: 'pre_approved' as const } : null
})
const LIMIT_TEXT: Record<string, string> = {
  pre_approved: 'Предварительно одобрено до',
  payment: 'По отчётности на этот срок компании посильно до',
  project: 'По проектной оценке предодобрено до',
}
const takeLimit = () => {
  if (limit.value) terms.amount = clamp(limit.value.amount, product.value.amount.min, product.value.amount.max)
}

/** Стартапу без действующей проектной оценки — подсказка: с ней банк заранее скажет сумму */
const suggestProject = computed(
  () => product.value.startupOnly && isStartup.value && terms.organizationId && !projectApproved(founderPrescreen.state[terms.organizationId]),
)
</script>

<template>
  <div class="space-y-6">
    <div data-field="organization">
      <SelectField
        v-if="organizationOptions.length > 1"
        v-model="terms.organizationId"
        label="Компания"
        :options="organizationOptions"
      />
      <div v-else-if="organization" class="flex items-center gap-3 rounded-2xl bg-surface-soft p-4">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white text-ink-secondary">
          <Building2 class="size-5" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <p class="truncate font-semibold text-ink">{{ organization.name }}</p>
          <p class="text-sm text-ink-secondary">ИНН {{ organization.inn }}</p>
        </div>
      </div>
      <p v-if="fieldErrors.organization" class="mt-1.5 text-sm text-brand">{{ fieldErrors.organization }}</p>
      <p v-if="requisitesLine" class="mt-2 text-xs text-ink-secondary">Из базы банка: {{ requisitesLine }}</p>
      <p
        v-if="requisites?.verification.status === 'mismatch'"
        class="mt-2 flex items-start gap-2 rounded-xl bg-warning-soft p-3 text-sm text-ink"
      >
        <CircleAlert class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
        Часть данных компании нужно уточнить — заявку посмотрит специалист банка, решение займёт больше времени.
      </p>
    </div>

    <div data-field="request.purpose">
      <SelectField v-model="purpose" label="Для чего нужны деньги" :options="purposeOptions" />
      <p v-if="fieldErrors['request.purpose']" class="mt-1.5 text-sm text-brand">
        {{ fieldErrors['request.purpose'] }}
      </p>
    </div>

    <div v-if="suggestions.length">
      <p class="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
        <Sparkles class="size-4 text-brand" aria-hidden="true" />
        Под эту цель подходят
      </p>
      <ul class="grid gap-2 sm:grid-cols-2">
        <li v-for="item in suggestions" :key="item.code">
          <button
            type="button"
            class="flex h-full w-full flex-col items-start gap-1 rounded-xl p-3 text-left text-sm transition-colors"
            :class="
              product.code === item.code
                ? 'bg-brand-soft ring-2 ring-brand'
                : item.eligible === false
                  ? 'bg-surface-soft opacity-70 hover:opacity-100'
                  : 'bg-surface-soft hover:bg-surface'
            "
            :aria-pressed="product.code === item.code"
            @click="choose(item)"
          >
            <span class="font-semibold text-ink">{{ productByCode(item.code)?.title }}</span>
            <span class="text-xs text-ink-secondary">от {{ formatMoney(item.paymentFrom) }} в месяц</span>
            <span v-if="item.eligible === false" class="text-xs text-brand">{{ item.notEligibleReasons[0] }}</span>
            <span v-else-if="item.preApprovedMax" class="flex items-center gap-1 text-xs text-success">
              <BadgeCheck class="size-3.5" aria-hidden="true" />
              Предварительно до {{ formatMoneyShort(item.preApprovedMax) }}
            </span>
          </button>
        </li>
      </ul>
    </div>

    <div data-field="request.product">
      <SelectField v-model="terms.productId" label="Продукт" :options="productOptions" />
      <p v-if="ineligibleReason || fieldErrors['request.product']" class="mt-1.5 text-sm text-brand" role="alert">
        {{ ineligibleReason ?? fieldErrors['request.product'] }}
      </p>
      <p v-if="isStartup" class="mt-1.5 text-xs text-ink-secondary">
        Компания недавно зарегистрирована — для неё кредиты на запуск бизнеса с проверкой учредителя.
      </p>
    </div>

    <FounderPrescreenPanel v-if="product.startupOnly && isStartup && terms.organizationId" :organization-id="terms.organizationId" />
    <p v-if="suggestProject" class="rounded-xl bg-surface-soft p-3 text-sm text-ink-secondary">
      Заявку можно подать и без проектной оценки, но с ней банк заранее скажет, до какой суммы готов дать кредит:
      заполните бизнес-план и оцените проект в «Компании».
    </p>

    <RangeField
      v-model="terms.amount"
      label="Сумма кредита"
      :min="product.amount.min"
      :max="product.amount.max"
      :step="amountStep(product)"
      :format-value="formatMoney"
    />
    <div v-if="limit" class="-mt-3 flex items-start gap-2 text-sm" :class="terms.amount > limit.amount ? 'text-warning' : 'text-success'">
      <CircleAlert v-if="terms.amount > limit.amount" class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <BadgeCheck v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p>
        {{ LIMIT_TEXT[limit.by] }} {{ formatMoney(limit.amount) }}<template v-if="terms.amount > limit.amount">
          — подать больше можно, решение примет специалист.
          <button type="button" class="font-medium underline underline-offset-2" @click="takeLimit">Взять {{ formatMoney(limit.amount) }}</button>
        </template>
      </p>
    </div>
    <RangeField
      v-model="terms.termMonths"
      label="Срок"
      :min="product.termMonths.min"
      :max="product.termMonths.max"
      :step="termStep(product)"
      :format-value="formatTerm"
      :editable="false"
    />

    <TextField
      v-model="terms.purposeComment"
      label="Комментарий к цели"
      placeholder="Необязательно"
      :maxlength="500"
    />

    <div class="flex flex-wrap items-baseline justify-between gap-2 rounded-2xl bg-night px-5 py-4 text-on-night">
      <span class="text-sm text-on-night-secondary">
        {{ schedule?.repayment === 'interest_only' ? 'Платёж по процентам в месяц' : 'Платёж в месяц' }}
      </span>
      <span class="text-xl font-bold transition-opacity" :class="pending && 'opacity-60'">
        <AnimatedNumber v-if="schedule" :value="schedule.monthlyPayment" :format="formatMoney" />
        <template v-else>—</template>
        <span class="text-sm font-normal text-on-night-secondary">
          по ставке {{ personal?.preApproved ? '' : 'от ' }}{{ formatPercent(schedule?.rate ?? product.rateFrom) }}
        </span>
      </span>
    </div>
  </div>
</template>
