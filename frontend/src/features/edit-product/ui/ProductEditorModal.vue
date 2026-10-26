<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import {
  COLLATERAL_LABEL,
  COLLATERAL_TYPE_LABEL,
  FACILITY_LABEL,
  LEGAL_FORM_LABEL,
  PRODUCT_GUARANTEE_LABEL,
  PURPOSE_LABEL,
  REPAYMENT_LABEL,
} from '@/entities/credit-product'
import { workflowTitle } from '@/entities/process'
import {
  ApiError,
  backofficeApi,
  type CollateralKind,
  type CollateralType,
  type Facility,
  type LegalForm,
  type LoanPurpose,
  type ProductDto,
  type Repayment,
  type WorkflowDto,
} from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal, SelectField, TextField, ToggleSwitch } from '@/shared/ui'

import { toCreateInput, toForm, toInput, validate, type Guarantee, type ProductForm, type ProductFormErrors } from '../model/productForm'
import OptionChips from './OptionChips.vue'

/**
 * Новый продукт (POST /products) или новые условия (PUT /products/{code}). У продукта в продаже
 * PUT выпускает новую версию — идущие заявки остаются на своих условиях; черновик правится на месте.
 * Новый можно начать с копии условий другого продукта.
 */
const props = defineProps<{
  /** null — создаём новый продукт */
  product: ProductDto | null
  /** Каталог — для копии условий в новый продукт */
  catalog: readonly ProductDto[]
  workflows: readonly WorkflowDto[]
}>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [product: ProductDto] }>()

const isNew = computed(() => !props.product)

const form = reactive<ProductForm>(toForm(props.product))
const errors = reactive<ProductFormErrors>({})
const formError = ref<string | null>(null)
const pending = ref(false)
const publish = ref(false)
const templateCode = ref('')

/** Новому продукту с нуля — последняя версия стандартного маршрута */
function defaultWorkflow(): string {
  const versionOf = (code: string) => Number(/_v(\d+)$/.exec(code)?.[1] ?? 0)
  const standard = props.workflows.filter((workflow) => workflow.code.startsWith('standard_'))
  return [...standard].sort((a, b) => versionOf(b.code) - versionOf(a.code))[0]?.code ?? props.workflows[0]?.code ?? ''
}

watch(open, (isOpen) => {
  if (!isOpen) return
  Object.assign(form, toForm(props.product))
  if (!form.workflowCode) form.workflowCode = defaultWorkflow()
  Object.keys(errors).forEach((key) => delete errors[key as keyof ProductForm])
  formError.value = null
  publish.value = false
  templateCode.value = ''
})

const template = computed(() => props.catalog.find((product) => product.code === templateCode.value) ?? null)

/** Новая версия без изменений не нужна; снятый с продажи возвращается и без правок */
const isDirty = computed(
  () => !props.product || props.product.status === 'archived' || JSON.stringify(toForm(props.product)) !== JSON.stringify(form),
)

/** Копия условий: код, карточка и название — свои у нового продукта */
watch(templateCode, () => {
  if (!template.value) return
  const { code, frontendId, name, shortDescription } = form
  Object.assign(form, toForm(template.value), { code, frontendId, name, shortDescription })
})

const options = <T extends string>(labels: Record<T, string>) =>
  (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }))

const PURPOSES = options<LoanPurpose>(PURPOSE_LABEL)
const REPAYMENTS = options<Repayment>(REPAYMENT_LABEL)
const FACILITIES = options<Facility>(FACILITY_LABEL)
const LEGAL_FORMS = options<LegalForm>(LEGAL_FORM_LABEL as Record<LegalForm, string>)
const COLLATERAL_KINDS = options<CollateralKind>(COLLATERAL_LABEL)
const COLLATERAL_TYPES = options<CollateralType>(COLLATERAL_TYPE_LABEL as Record<CollateralType, string>)
const GUARANTEES = options<Guarantee>(PRODUCT_GUARANTEE_LABEL as Record<Guarantee, string>)

const templateOptions = computed(() => [
  { value: '', label: 'С чистого листа' },
  ...props.catalog.map((product) => ({ value: product.code, label: `${product.name} (${product.code})` })),
])

/** Маршрут продукта есть всегда, даже если его уже нет среди маршрутов процесса */
const workflowOptions = computed(() => {
  const codes = new Set(props.workflows.map((workflow) => workflow.code))
  if (form.workflowCode) codes.add(form.workflowCode)
  return [...codes].sort().map((code) => ({ value: code, label: workflowTitle(code) }))
})

/** Что бэкенд проверяет сверх формы: занятый код (409), карточка и маршрут (422, поле — в details.field) */
const VIOLATION: Record<string, { field: keyof ProductForm; text: string }> = {
  frontend_id: { field: 'frontendId', text: 'Эта карточка уже у другого продукта' },
  workflow_code: { field: 'workflowCode', text: 'Такого маршрута нет' },
}

function fieldErrors(caught: unknown): boolean {
  if (!(caught instanceof ApiError)) return false
  if (caught.status === 409 && isNew.value && caught.code === 'conflict') {
    errors.code = 'Продукт с таким кодом уже есть'
    return true
  }
  const violation = typeof caught.details.field === 'string' ? VIOLATION[caught.details.field] : undefined
  if (violation) errors[violation.field] = violation.text
  return Boolean(violation)
}

async function submit() {
  formError.value = null
  Object.keys(errors).forEach((key) => delete errors[key as keyof ProductForm])
  Object.assign(errors, validate(form, isNew.value))
  if (Object.keys(errors).length) {
    formError.value = 'Проверьте отмеченные поля'
    return
  }
  pending.value = true
  try {
    const saved = props.product
      ? await backofficeApi.updateProduct(props.product.code, toInput(form, props.product))
      : await backofficeApi.createProduct(toCreateInput(form, template.value, publish.value))
    emit('saved', saved)
    open.value = false
  } catch (caught) {
    formError.value = fieldErrors(caught) ? 'Проверьте отмеченные поля' : errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal
    v-model:open="open"
    :title="product ? `Условия: ${product.name}` : 'Новый продукт'"
    :description="
      product?.status === 'active'
        ? 'Сохранение выпустит новую версию продукта. Идущие заявки остаются на своих условиях'
        : product?.status === 'archived'
          ? 'Сохранение вернёт продукт в продажу с этими условиями'
          : undefined
    "
    wide
  >
    <form id="product-form" class="space-y-6" novalidate @submit.prevent="submit">
      <section v-if="isNew" class="grid gap-3 sm:grid-cols-2">
        <SelectField v-model="templateCode" label="На основе продукта" :options="templateOptions" dense class="sm:col-span-2" />
        <TextField v-model="form.code" label="Код" dense placeholder="EQUIPMENT_LEASE" :error="errors.code" hint="Не меняется у всех версий продукта" />
        <TextField v-model="form.frontendId" label="Карточка на сайте" dense placeholder="equipment-lease" :error="errors.frontendId" />
      </section>

      <section class="grid gap-3 sm:grid-cols-2">
        <TextField v-model="form.name" label="Название" dense :error="errors.name" class="sm:col-span-2" />
        <TextField v-model="form.shortDescription" label="Коротко для каталога" dense :error="errors.shortDescription" class="sm:col-span-2" />
        <TextField
          v-model="form.keywords"
          label="Слова на карточке"
          dense
          placeholder="Без залога, Быстро, На любые цели"
          hint="Через запятую, до 5"
          :error="errors.keywords"
          class="sm:col-span-2"
        />
        <TextField v-model="form.tag" label="Метка" dense placeholder="Популярный" hint="Пусто — без метки" :error="errors.tag" />
        <TextField v-model="form.decisionTime" label="Время решения" dense placeholder="1 рабочий день" hint="Пусто — по авторешению" :error="errors.decisionTime" />
      </section>

      <section>
        <h3 class="mb-3 text-sm font-semibold text-ink">Условия</h3>
        <div class="grid gap-3 sm:grid-cols-2">
          <TextField v-model="form.amountMin" filter="amount" label="Сумма от, ₽" dense :error="errors.amountMin" />
          <TextField v-model="form.amountMax" filter="amount" label="Сумма до, ₽" dense :error="errors.amountMax" />
          <TextField v-model="form.termMin" filter="digits" label="Срок от, мес." dense :error="errors.termMin" />
          <TextField v-model="form.termMax" filter="digits" label="Срок до, мес." dense :error="errors.termMax" />
          <TextField v-model="form.rateBase" filter="decimal" label="Ставка от, %" dense :error="errors.rateBase" />
          <TextField v-model="form.rateMax" filter="decimal" label="Ставка до, %" dense :error="errors.rateMax" />
          <TextField
            v-model="form.autoDecisionLimit"
            label="Авторешение до, ₽"
            inputmode="numeric"
            dense
            hint="Выше — решает специалист; 0 — всегда специалист"
          />
          <SelectField v-model="form.facility" label="Как выдаём" :options="FACILITIES" dense />
        </div>
        <div class="mt-4 space-y-4">
          <OptionChips v-model="form.repayment" label="Графики погашения — первый по умолчанию" :options="REPAYMENTS" :error="errors.repayment" />
          <OptionChips v-model="form.purposes" label="Цели кредита" :options="PURPOSES" :error="errors.purposes" />
        </div>
      </section>

      <section>
        <h3 class="mb-3 text-sm font-semibold text-ink">Кому подходит</h3>
        <div class="space-y-4">
          <OptionChips v-model="form.legalForms" label="Формы бизнеса" :options="LEGAL_FORMS" :error="errors.legalForms" />
          <div class="grid gap-3 sm:grid-cols-2">
            <TextField v-model="form.minBusinessAge" filter="digits" label="Бизнесу не меньше, мес." dense />
            <TextField v-model="form.minRevenue" filter="amount" label="Выручка за год от, ₽" dense hint="Пусто — без требования" />
          </div>
          <ToggleSwitch
            v-model="form.startupOnly"
            label="Только для стартапа"
            description="Бизнес младше 6 месяцев или без годового отчёта: решение по проектной оценке"
          />
        </div>
      </section>

      <section>
        <h3 class="mb-3 text-sm font-semibold text-ink">Обеспечение</h3>
        <div class="grid gap-3 sm:grid-cols-2">
          <SelectField v-model="form.collateralKind" label="Залог" :options="COLLATERAL_KINDS" dense />
          <TextField
            v-if="form.collateralKind === 'optional'"
            v-model="form.collateralFrom"
            label="Залог обязателен от, ₽"
            inputmode="numeric"
            dense
            hint="Пусто — по желанию при любой сумме"
          />
          <SelectField v-model="form.guarantee" label="Поручительство" :options="GUARANTEES" dense />
        </div>
        <OptionChips
          v-if="form.collateralKind !== 'none'"
          v-model="form.collateralTypes"
          label="Что принимаем в залог"
          :options="COLLATERAL_TYPES"
          class="mt-4"
        />
        <ToggleSwitch
          v-model="form.targetUse"
          label="Подтверждение целевого использования"
          description="Деньги идут продавцу транспорта, недвижимости или в погашение других кредитов"
          class="mt-4"
        />
      </section>

      <section class="grid gap-3 sm:grid-cols-2">
        <SelectField
          v-if="workflowOptions.length"
          v-model="form.workflowCode"
          label="Маршрут заявки"
          :options="workflowOptions"
          dense
          class="sm:col-span-2"
        />
        <p v-if="errors.workflowCode" class="text-xs text-brand sm:col-span-2" role="alert">{{ errors.workflowCode }}</p>
        <ToggleSwitch
          v-if="isNew"
          v-model="publish"
          label="Сразу в продажу"
          description="Иначе продукт останется черновиком и не появится на сайте"
          class="sm:col-span-2"
        />
      </section>

      <p v-if="product || template" class="text-xs text-ink-secondary">
        Документы, дополнительные поля заявки, господдержка и полное описание остаются как у продукта
        «{{ (product ?? template)!.name }}».
      </p>
    </form>
    <p v-if="formError" class="mt-4 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ formError }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton type="submit" form="product-form" :disabled="!isDirty" :loading="pending">
        {{ product ? (product.status === 'archived' ? 'Вернуть в продажу' : 'Сохранить') : 'Создать' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>
