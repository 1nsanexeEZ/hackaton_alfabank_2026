<script setup lang="ts">
import {
  BadgeCheck,
  Building,
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import {
  findProduct,
  PURPOSE_LABEL,
  REPAYMENT_LABEL,
  useLoanSchedule,
  useRecommendations,
  type ProductCatalog,
  type ProductRecommendation,
} from '@/entities/credit-product'
import { founderPrescreen } from '@/entities/customer'
import type { LoanPurpose } from '@/shared/api'
import { clamp, formatDate, formatMoney, formatMoneyShort, formatPercent, formatTerm, formatTermLimit, pluralize } from '@/shared/lib'
import { BaseButton, RangeField, SelectField } from '@/shared/ui'

import { fitLoanParams } from '../model/loanParams'

/**
 * Подбор и расчёт кредита в одном блоке: цель, сумма и срок → продукты под цель по порядку
 * (POST /products/recommend; вошедшему — ещё проверка его компании и предодобрение, GET /bff/products/recommend)
 * → расчёт выбранного продукта (у компании — по ставке её предодобрения, POST /bff/products/{code}/calculate).
 * Продукты — строками в окне фиксированной высоты: сколько бы их ни было, блок не растёт.
 */
const props = defineProps<{
  products: ProductCatalog
  /** Компании вошедшего клиента: подбор и расчёт для выбранной; гостю — пусто */
  companies?: readonly { id: string; name: string }[] | null
}>()

const emit = defineEmits<{
  apply: [params: { productId: string; amount: number; termMonths: number; purpose: LoanPurpose; organizationId: string }]
}>()

/** Выбранный продукт */
const productId = defineModel<string>('productId', { required: true })
/** Что нужно клиенту: сумма и срок — под каждый продукт их подгоняет подбор */
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })
const purpose = defineModel<LoanPurpose>('purpose', { default: 'working_capital' })
/** Для какой компании подбирать и считать; пусто — как для гостя */
const organizationId = defineModel<string>('organizationId', { default: '' })

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

// Компании — только доступные ей продукты: стартапу — для стартапа, действующему бизнесу — без них
watch(organizationId, (id) => id && void founderPrescreen.load(id), { immediate: true })
const segment = computed(() => (organizationId.value ? founderPrescreen.state[organizationId.value]?.segment : undefined))
const allowed = computed(() =>
  segment.value ? props.products.filter((item) => Boolean(item.startupOnly) === (segment.value === 'startup')) : props.products,
)

/** Рамки суммы и срока — по всем доступным продуктам: под конкретный продукт их подгоняет подбор */
const bounds = computed(() => {
  const list = allowed.value.length ? allowed.value : props.products
  return {
    amountMin: Math.min(...list.map((item) => item.amount.min)),
    amountMax: Math.max(...list.map((item) => item.amount.max)),
    termMin: Math.min(...list.map((item) => item.termMonths.min)),
    termMax: Math.max(...list.map((item) => item.termMonths.max)),
  }
})
const amountStep = computed(() => (bounds.value.amountMax <= 10_000_000 ? 50_000 : 100_000))
watch(
  bounds,
  (range) => {
    amount.value = clamp(amount.value, range.amountMin, range.amountMax)
    termMonths.value = clamp(termMonths.value, range.termMin, range.termMax)
  },
  { immediate: true },
)

const companyOptions = computed(() => (props.companies ?? []).map((item) => ({ value: item.id, label: item.name })))
const company = computed(() => props.companies?.find((item) => item.id === organizationId.value) ?? null)

const { items, loading, error } = useRecommendations(() => ({
  purpose: purpose.value,
  amount: amount.value,
  termMonths: termMonths.value,
  organizationId: company.value?.id ?? null,
}))

/** Сначала подходящие, потом «если поменять», компании не подходящие и не подходящие под задачу — по месту подбора */
const ORDER: Record<ProductRecommendation['status'], number> = { available: 0, needs_adjustment: 1, unavailable: 3 }
const rank = (item: ProductRecommendation) => (item.eligible === false ? 2 : ORDER[item.status])
const list = computed(() =>
  (items.value ?? [])
    .filter((item) => allowed.value.some((product) => product.code === item.code))
    .sort((a, b) => rank(a) - rank(b) || a.rank - b.rank),
)

const product = computed(() => findProduct(props.products, productId.value))
const selected = computed(() => list.value.find((item) => item.code === product.value.code) ?? null)

// Подбор обновился без выбранного продукта — берём лучший; продукт выбрали снаружи (из каталога),
// а под текущую цель он не подбирается — переключаем цель на его
watch(list, (next) => {
  if (!next.length || next.some((item) => item.code === product.value.code)) return
  const best = next.find((item) => rank(item) === 0) ?? next[0]!
  const found = props.products.find((item) => item.code === best.code)
  if (found) productId.value = found.id
})
watch(productId, () => {
  if (!items.value || selected.value) return
  const own = product.value.purposes[0]
  if (own && !product.value.purposes.includes(purpose.value)) purpose.value = own
})

const titleOf = (code: string) => props.products.find((item) => item.code === code)?.title ?? code

function choose(item: ProductRecommendation) {
  const found = props.products.find((candidate) => candidate.code === item.code)
  if (found) productId.value = found.id
}

/** Сумма и срок под выбранный продукт: подогнанные подбором, без подбора — по рамкам продукта */
const fitted = computed(() =>
  selected.value
    ? { amount: selected.value.amount, termMonths: selected.value.termMonths }
    : fitLoanParams(product.value, amount.value, termMonths.value),
)

const { schedule, personal, pending, estimated } = useLoanSchedule(() => ({
  product: product.value,
  amount: fitted.value.amount,
  termMonths: fitted.value.termMonths,
  organizationId: company.value?.id ?? null,
}))

const preApproved = computed(() => personal.value?.preApproved ?? null)
/** «Сумма/срок больше одобренного» и «больше посильного» объясняет блок предодобрения, остальное — отдельно */
const isLimitReason = (code: string) => code.endsWith('_above_pre_approved') || code === 'amount_above_affordable'
const limitProblem = computed(() => personal.value?.problems.find((reason) => isLimitReason(reason.code)) ?? null)
/** Сообщение бэка о лимите, а если в нём нет, что подать всё равно можно, — дописываем */
const limitText = computed(() => {
  const message = (limitProblem.value?.message ?? 'Запрос больше, чем банк готов предложить').replace(/\.$/, '')
  return message.includes('специалист') ? `${message}.` : `${message}. Подать можно — решит специалист.`
})
const overLimit = computed(() => personal.value?.withinPreApproved === false || Boolean(personal.value?.aboveAffordable))
/** Посильная сумма ниже предодобренной — её ограничила платёжеспособность по отчётности */
const paymentLimit = computed(() =>
  personal.value?.affordableBy === 'payment' && personal.value.maxAffordable !== null ? personal.value.maxAffordable : null,
)
/** Почему компании не подходит: из подбора, а без него — из личного расчёта */
const notEligible = computed(() => {
  if (selected.value?.notEligibleReasons.length) return selected.value.notEligibleReasons
  return personal.value?.eligible === false
    ? personal.value.problems.filter((reason) => !isLimitReason(reason.code)).map((reason) => reason.message)
    : []
})

function takeSuggestion() {
  const suggestion = personal.value?.suggestion
  if (!suggestion) return
  amount.value = clamp(suggestion.amount, product.value.amount.min, product.value.amount.max)
  termMonths.value = clamp(suggestion.termMonths, product.value.termMonths.min, product.value.termMonths.max)
}

const STATUS: Record<ProductRecommendation['status'], { label: string; dot: string }> = {
  available: { label: 'Подходит', dot: 'bg-success' },
  needs_adjustment: { label: 'Если поменять условия', dot: 'bg-warning' },
  unavailable: { label: 'Не под эту задачу', dot: 'bg-ink-muted' },
}
const statusOf = (item: ProductRecommendation) =>
  item.eligible === false ? { label: 'Компании не подходит', dot: 'bg-brand' } : STATUS[item.status]

const blocked = computed(() => selected.value?.status === 'unavailable' || notEligible.value.length > 0)

function apply() {
  emit('apply', {
    productId: product.value.id,
    amount: fitted.value.amount,
    termMonths: fitted.value.termMonths,
    purpose: purpose.value,
    organizationId: company.value?.id ?? '',
  })
}

// Список продуктов — окно фиксированной высоты: внизу подсказка, сколько ещё ниже
const listBox = ref<HTMLElement | null>(null)
const hiddenBelow = ref(0)
function measureList() {
  const box = listBox.value
  if (!box) return (hiddenBelow.value = 0)
  const bottom = box.getBoundingClientRect().bottom
  hiddenBelow.value = [...box.querySelectorAll('li')].filter((row) => {
    const rect = row.getBoundingClientRect()
    return rect.top + rect.height / 2 > bottom
  }).length
}
let observer: ResizeObserver | undefined
watch(listBox, (box) => {
  observer?.disconnect()
  if (!box) return
  observer = new ResizeObserver(measureList)
  observer.observe(box)
})
watch(list, () => void nextTick(measureList))
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="space-y-4">
    <!-- min-w-0: у fieldset по умолчанию min-width: min-content — без него лента целей растягивала бы страницу -->
    <fieldset class="min-w-0">
      <legend class="mb-3 text-sm font-medium text-ink">Для чего нужны деньги</legend>
      <!-- На телефоне цели — лентой с прокруткой, на широком экране переносятся -->
      <div class="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
        <button
          v-for="item in PURPOSES"
          :key="item.value"
          type="button"
          class="flex h-11 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium whitespace-nowrap transition-colors"
          :class="purpose === item.value ? 'bg-brand text-white' : 'bg-white text-ink hover:bg-surface-strong'"
          :aria-pressed="purpose === item.value"
          @click="purpose = item.value"
        >
          <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
          {{ PURPOSE_LABEL[item.value] }}
        </button>
      </div>
    </fieldset>

    <div class="grid gap-4 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)_minmax(0,21rem)] xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)_minmax(0,24rem)]">
      <!-- Параметры и предодобрение -->
      <div class="space-y-6 rounded-card bg-white p-5 lg:p-6">
        <SelectField v-if="companyOptions.length > 1" v-model="organizationId" label="Компания" :options="companyOptions" />
        <RangeField
          v-model="amount"
          label="Сумма"
          :min="bounds.amountMin"
          :max="bounds.amountMax"
          :step="amountStep"
          :format-value="formatMoney"
        />
        <RangeField
          v-model="termMonths"
          label="Срок"
          :min="bounds.termMin"
          :max="bounds.termMax"
          :step="3"
          :format-value="formatTerm"
        />

        <div v-if="company && preApproved" class="rounded-2xl p-4 text-sm" :class="overLimit ? 'bg-warning-soft' : 'bg-success-soft'">
          <p class="text-ink">
            Предварительно одобрено до <b>{{ formatMoney(preApproved.maxAmount) }}</b> от {{ formatPercent(preApproved.rateFrom) }},
            {{ formatTermLimit(preApproved.termMaxMonths) }} — до {{ formatDate(preApproved.validUntil) }}
          </p>
          <p v-if="paymentLimit !== null" class="mt-1 text-ink-secondary">
            По отчётности на этот срок компании посильно до {{ formatMoney(paymentLimit) }}.
          </p>
          <template v-if="overLimit && personal">
            <p class="mt-2 text-ink-secondary">
              {{ limitText }}
            </p>
            <button
              v-if="personal.suggestion"
              type="button"
              class="mt-2 text-left font-medium text-ink underline underline-offset-2"
              @click="takeSuggestion"
            >
              Взять посильные условия: {{ formatMoney(personal.suggestion.amount) }} на {{ formatTerm(personal.suggestion.termMonths) }}
            </button>
          </template>
        </div>
        <p v-else-if="company && segment === 'startup'" class="rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
          Предварительного одобрения пока нет: пройдите проверку учредителя и оцените проект в «Компании» — банк заранее
          скажет сумму.
        </p>
        <p v-else-if="company && personal && personal.withinPreApproved === null" class="rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
          По этому продукту предварительного одобрения нет — расчёт по базовой ставке.
        </p>
        <p v-else-if="!companyOptions.length" class="text-sm text-ink-secondary">
          Войдите — проверим, подходит ли продукт вашей компании, и посчитаем по ставке её предодобрения.
        </p>
      </div>

      <!-- Продукты под цель: окно фиксированной высоты -->
      <div class="flex min-w-0 flex-col rounded-card bg-white p-5 lg:p-6">
        <p class="text-sm font-medium text-ink">
          Под эту цель
          <span v-if="list.length" class="text-ink-secondary">· {{ list.length }} {{ pluralize(list.length, ['продукт', 'продукта', 'продуктов']) }}</span>
        </p>
        <p v-if="error && !items" class="mt-3 text-sm text-brand">{{ error }}</p>
        <p v-else-if="items && !list.length" class="mt-3 rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
          Под эту цель продуктов нет — выберите другую цель или посмотрите каталог ниже.
        </p>
        <!--
          Отступ внутри прокрутки: рамка выбранного продукта рисуется снаружи карточки и иначе обрезается.
          Без overscroll-contain: долистали список до края — прокрутка уходит странице
        -->
        <ol
          v-else
          ref="listBox"
          class="-mx-1 mt-2 max-h-60 space-y-2 overflow-y-auto p-1 pr-2 transition-opacity lg:max-h-[26rem]"
          :class="loading && 'opacity-60'"
          aria-label="Продукты под цель"
          @scroll.passive="measureList"
        >
          <li v-if="!items" class="h-16 animate-pulse rounded-xl bg-surface-soft" />
          <li v-for="item in list" :key="item.code">
            <button
              type="button"
              class="w-full rounded-xl p-3 text-left transition-colors"
              :class="item.code === product.code ? 'bg-brand-soft ring-2 ring-brand' : 'bg-surface-soft/60 hover:bg-surface-soft'"
              :aria-pressed="item.code === product.code"
              @click="choose(item)"
            >
              <span class="flex items-start justify-between gap-2">
                <span class="min-w-0 text-sm font-semibold text-ink">{{ titleOf(item.code) }}</span>
                <span class="flex shrink-0 items-center gap-1.5 text-xs text-ink-secondary">
                  <span class="size-2 rounded-full" :class="statusOf(item).dot" aria-hidden="true" />
                  {{ statusOf(item).label }}
                </span>
              </span>
              <span class="mt-1 block text-xs text-ink-secondary">
                от {{ formatMoney(item.paymentFrom) }} в месяц
                <template v-if="item.amount !== amount || item.termMonths !== termMonths">
                  · {{ formatMoneyShort(item.amount) }} на {{ formatTerm(item.termMonths) }}</template
                >
                <template v-if="item.preApprovedMax"> · одобрено до {{ formatMoneyShort(item.preApprovedMax) }}</template>
              </span>
            </button>
          </li>
        </ol>
        <p v-if="hiddenBelow" class="mt-2 text-xs text-ink-secondary">Ещё {{ hiddenBelow }} ниже — прокрутите список</p>
      </div>

      <!-- Расчёт выбранного продукта -->
      <div class="flex flex-col rounded-card bg-night p-6 text-on-night lg:p-7" aria-live="polite">
        <p class="text-sm text-on-night-secondary">{{ product.title }}</p>
        <p class="mt-3 text-sm text-on-night-secondary">
          {{ schedule?.repayment === 'interest_only' ? 'Платёж по процентам в месяц' : 'Ежемесячный платёж' }}
        </p>
        <p class="mt-1 text-4xl font-bold tracking-tight transition-opacity" :class="pending && 'opacity-60'">
          {{ schedule ? formatMoney(schedule.monthlyPayment) : '—' }}
        </p>
        <p class="mt-1 text-sm text-on-night-secondary">{{ formatMoney(fitted.amount) }} на {{ formatTerm(fitted.termMonths) }}</p>

        <dl class="mt-6 space-y-3 border-t border-night-line pt-5 text-sm" :class="pending && 'opacity-60'">
          <div class="flex justify-between gap-4">
            <dt class="text-on-night-secondary">Ставка</dt>
            <dd class="font-semibold">{{ personal ? '' : 'от ' }}{{ formatPercent(schedule?.rate ?? product.rateFrom) }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-on-night-secondary">Переплата</dt>
            <dd class="font-semibold">{{ schedule ? formatMoneyShort(schedule.totalInterest) : '—' }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt class="text-on-night-secondary">Всего выплат</dt>
            <dd class="font-semibold">{{ schedule ? formatMoneyShort(schedule.totalPaid) : '—' }}</dd>
          </div>
          <div v-if="schedule" class="flex justify-between gap-4">
            <dt class="text-on-night-secondary">Погашение</dt>
            <dd class="text-right font-semibold">{{ REPAYMENT_LABEL[schedule.repayment] }}</dd>
          </div>
        </dl>

        <ul v-if="selected?.adjustments.length || notEligible.length || selected?.eligible" class="mt-5 space-y-1.5 text-sm">
          <li v-for="hint in selected?.adjustments ?? []" :key="hint" class="flex items-start gap-2">
            <CircleAlert class="mt-0.5 size-4 shrink-0 text-warning-soft" aria-hidden="true" />
            {{ hint }}
          </li>
          <li v-for="reason in notEligible" :key="reason" class="flex items-start gap-2">
            <CircleX class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
            {{ reason }}
          </li>
          <li v-if="selected?.eligible && !notEligible.length" class="flex items-start gap-2">
            <BadgeCheck class="mt-0.5 size-4 shrink-0 text-success-soft" aria-hidden="true" />
            {{ company ? `${company.name} подходит` : 'Компания подходит' }}
          </li>
        </ul>

        <!-- Итог отделён от действия отступом; на десктопе кнопка прижата к низу колонки, но отступ остаётся -->
        <div class="mt-auto pt-8">
          <BaseButton size="l" block :disabled="blocked" @click="apply">Оформить заявку</BaseButton>
        </div>
        <p class="mt-3 text-xs text-on-night-secondary">
          <template v-if="blocked">{{ notEligible.length ? 'Компании продукт не подходит' : 'Под эту задачу продукт не подходит' }} — выберите другой. </template>
          <template v-if="estimated && !pending">Банк сейчас не отвечает — показан приблизительный расчёт. </template>
          <template v-if="company && personal?.preApproved">Расчёт по ставке предварительного одобрения. </template>
          <template v-else>Расчёт по базовой ставке продукта. </template>
          Точные условия банк покажет после рассмотрения заявки.
        </p>
      </div>
    </div>
  </div>
</template>
