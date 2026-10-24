<script setup lang="ts">
import { CircleCheck, CircleX, FileText } from 'lucide-vue-next'
import { computed, ref, toRef, watch } from 'vue'

import { founderPrescreen, prescreenPassed, projectApproved, projectOutdated } from '@/entities/customer'
import { errorMessage, formatDate, formatDateTime, formatMoney, formatTerm } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

import { useBusinessPlan } from '../model/useBusinessPlan'
import BusinessPlanEditor from './BusinessPlanEditor.vue'

/**
 * Ветка стартапа после проверки учредителя (docs/api/client-journey.md §4.6): бизнес-план и финмодель
 * в кабинете → проектная оценка банка → «вам предодобрен кредит до N». Оценка смотрит, хватает ли
 * денежного потока на платежи, достаточно ли своих средств и обеспечения; цифр модели клиенту не отдают.
 * Заявку на кредит для стартапа можно подать и без оценки — тогда сумму определит специалист.
 */
const props = defineProps<{ organizationId: string; canEdit: boolean; canSubmit: boolean }>()

const emit = defineEmits<{ apply: [code: string, maxAmount: number] }>()

const businessPlan = useBusinessPlan(toRef(props, 'organizationId'))
const { plan, loading, error, saving, errors } = businessPlan

const info = computed(() => founderPrescreen.state[props.organizationId] ?? null)
const project = computed(() => info.value?.project ?? null)
const approved = computed(() => projectApproved(info.value))
const outdated = computed(() => projectOutdated(info.value))
const prescreenOk = computed(() => prescreenPassed(info.value?.prescreen))
const failedReasons = computed(() => project.value?.reasons.filter((reason) => !reason.passed) ?? [])

const editing = ref(false)
watch(
  () => props.organizationId,
  () => (editing.value = false),
)

function startEdit() {
  businessPlan.edit()
  editing.value = true
}

async function save() {
  if (await businessPlan.save()) editing.value = false
}

const assessing = ref(false)
const assessError = ref<string | null>(null)
async function assess() {
  assessing.value = true
  assessError.value = null
  try {
    await founderPrescreen.runProject(props.organizationId)
  } catch (caught) {
    assessError.value = errorMessage(caught)
  } finally {
    assessing.value = false
  }
}

const model = computed(() => plan.value?.financial_model ?? null)
</script>

<template>
  <section class="space-y-4 rounded-2xl bg-surface-soft p-5">
    <div>
      <p class="flex items-center gap-2 font-semibold text-ink">
        <FileText class="size-5 shrink-0 text-brand" aria-hidden="true" />
        Бизнес-план и проектная оценка
      </p>
      <p class="mt-1 text-sm text-ink-secondary">
        Заполните бизнес-план и финмодель — банк оценит проект и скажет заранее, до какой суммы готов дать кредит на
        запуск бизнеса. Оценка действует 30 дней.
      </p>
    </div>

    <div v-if="project" class="rounded-xl bg-white p-4 text-sm">
      <template v-if="approved">
        <p class="flex items-center gap-2 font-medium text-success">
          <CircleCheck class="size-4 shrink-0" aria-hidden="true" />
          Вам предодобрен кредит до {{ formatMoney(Number(project.max_amount)) }}
        </p>
        <p class="mt-1 text-ink-secondary">Действует до {{ formatDate(project.valid_until) }} · оценка {{ formatDateTime(project.checked_at) }}</p>
        <BaseButton v-if="project.max_amount" class="mt-3" size="s" @click="emit('apply', project.product_code, Number(project.max_amount))">
          Оформить заявку
        </BaseButton>
      </template>
      <template v-else-if="outdated">
        <p class="font-medium text-warning">Бизнес-план изменили после оценки — оцените проект заново</p>
        <p class="mt-1 text-ink-secondary">Прошлая оценка — {{ formatDateTime(project.checked_at) }} по редакции {{ project.plan_revision }}</p>
      </template>
      <p v-else-if="project.status === 'passed'" class="font-medium text-warning">
        Срок оценки истёк {{ formatDate(project.valid_until) }} — оцените проект заново
      </p>
      <template v-else>
        <p class="flex items-center gap-2 font-medium text-brand">
          <CircleX class="size-4 shrink-0" aria-hidden="true" />
          Проект не прошёл оценку · {{ formatDateTime(project.checked_at) }}
        </p>
        <ul class="mt-2 space-y-0.5 text-ink-secondary">
          <li v-for="reason in failedReasons" :key="reason.code">• {{ reason.message }}</li>
        </ul>
        <p class="mt-2 text-ink-secondary">Поправьте план и оцените снова.</p>
      </template>
    </div>

    <BusinessPlanEditor
      v-if="editing"
      v-model:form="businessPlan.form"
      :errors="errors"
      :saving="saving"
      :error="error"
      :is-new="!plan"
      @fill="businessPlan.fillMonths"
      @save="save"
      @cancel="editing = false"
    />

    <template v-else>
      <p v-if="loading" class="text-sm text-ink-secondary">Загружаем бизнес-план…</p>
      <div v-else-if="plan && model" class="rounded-xl bg-white p-4 text-sm">
        <p class="font-medium text-ink">Бизнес-план · редакция {{ plan.revision }}</p>
        <p class="mt-1 text-ink">{{ plan.summary }}</p>
        <p class="mt-2 text-ink-secondary">
          Кредит {{ formatMoney(Number(model.loan_amount)) }} на {{ formatTerm(model.loan_term_months) }} · свои средства
          {{ formatMoney(Number(model.own_funds)) }} · обновлён {{ formatDateTime(plan.submitted_at) }}
        </p>
      </div>
      <p v-else-if="!error" class="text-sm text-ink">Бизнес-план ещё не заполнен.</p>
      <p v-if="error && !editing" class="text-sm text-brand" role="alert">{{ error }}</p>

      <div class="flex flex-wrap items-center gap-3">
        <BaseButton v-if="canEdit" :variant="plan ? 'secondary' : 'primary'" size="s" @click="startEdit">
          {{ plan ? 'Изменить план' : 'Заполнить бизнес-план' }}
        </BaseButton>
        <BaseButton
          v-if="plan && canSubmit && (!approved || outdated)"
          size="s"
          :loading="assessing"
          :disabled="!prescreenOk"
          @click="assess"
        >
          {{ project ? 'Оценить проект заново' : 'Оценить проект' }}
        </BaseButton>
      </div>
      <p v-if="plan && canSubmit && !prescreenOk" class="text-xs text-ink-secondary">
        Оценить проект можно после проверки учредителя — она выше.
      </p>
      <p v-if="!canEdit && !plan" class="text-xs text-ink-secondary">
        Заполняет участник с правом вести отчётность компании.
      </p>
      <p v-if="assessError" class="text-sm text-brand" role="alert">{{ assessError }}</p>
    </template>
  </section>
</template>
