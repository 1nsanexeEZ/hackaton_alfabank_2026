<script setup lang="ts">
import { Check, ShieldCheck } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import type { ContractDto, EsignRulesDto } from '@/shared/api'
import { BaseButton, BaseModal, CheckboxField, TextField } from '@/shared/ui'

import { hasContractDocument } from '../model/useApplicationCard'

/**
 * Подписание тремя шагами: ознакомиться с договором, принять Правила электронного взаимодействия,
 * подтвердить паролем от кабинета (step-up). Кнопка «Подписать» — в подвале окна, она отправляет эту
 * форму по `formId`. Со старым бэкендом PDF и Правил нет — остаётся только пароль.
 * Без права подписи — объясняем, кто может подписать.
 */
const props = defineProps<{
  contract: ContractDto
  rules: EsignRulesDto | null
  rulesError: string | null
  canSign: boolean
  /** Клиент уже скачал проект в этом окне */
  draftOpened: boolean
  busy: string | null
  formId: string
  /** Неверный пароль — показываем прямо под полем, а не общим текстом */
  passwordError: string | null
  /** Клиент вошёл кнопкой демо-доступа и пароль не вводил */
  viaDemo: boolean
}>()

const password = defineModel<string>('password', { required: true })
const rulesAccepted = defineModel<boolean>('rulesAccepted', { required: true })

const emit = defineEmits<{ submit: []; reloadRules: []; download: [kind: 'draft'] }>()

const withDocument = computed(() => hasContractDocument(props.contract))
const draftReady = computed(() => props.contract.document?.kind === 'draft' && props.contract.document.status === 'ready')
/** «2026-10-24» → «24.10.2026» */
const rulesDate = computed(() => props.rules?.effective_from.split('-').reverse().join('.') ?? null)
const rulesOpen = ref(false)

// Правила обновились (rules_outdated) — прежнее согласие не считается
watch(
  () => props.rules?.version,
  () => (rulesAccepted.value = false),
)

function acceptRules() {
  rulesAccepted.value = true
  rulesOpen.value = false
}

const AUTHORITY = { registry: 'руководитель', power_of_attorney: 'по доверенности' } as const
const signers = computed(() => props.contract.signers.map((signer) => `${signer.name} (${AUTHORITY[signer.authority] ?? signer.authority})`).join(', '))

const allSet = computed(() => Boolean(password.value) && (!withDocument.value || (rulesAccepted.value && draftReady.value)))
</script>

<template>
  <section v-if="canSign" class="space-y-4 rounded-2xl border border-line p-4 sm:p-5" aria-labelledby="sign-steps-title">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h3 id="sign-steps-title" class="text-base font-extrabold text-ink sm:text-[1.0625rem]">Подписание</h3>
      <span class="text-sm font-semibold" :class="allSet ? 'text-success' : 'text-ink-secondary'">
        {{ allSet ? 'всё готово к подписи' : 'три шага' }}
      </span>
    </div>

    <form :id="formId" class="space-y-4" @submit.prevent="emit('submit')">
      <ol class="space-y-4">
        <li v-if="withDocument" class="flex items-start gap-3.5" data-sign="draft">
          <span
            class="flex size-7 shrink-0 items-center justify-center rounded-full text-[0.8125rem] font-extrabold"
            :class="draftOpened ? 'bg-success text-white' : 'border-[3px] border-brand text-brand-active'"
            aria-hidden="true"
          >
            <Check v-if="draftOpened" class="size-3.5 stroke-[3]" />
            <template v-else>1</template>
          </span>
          <div class="min-w-0 flex-1 pt-0.5">
            <p class="text-[0.9375rem] font-semibold text-ink">Ознакомьтесь с договором</p>
            <p v-if="draftOpened" class="text-sm text-ink-secondary">Проект скачан — подписываете ровно его</p>
            <p v-else class="text-sm text-ink-secondary">
              Скачайте проект выше или
              <button
                type="button"
                class="font-medium text-info underline underline-offset-2 disabled:opacity-50"
                :disabled="!draftReady || Boolean(busy)"
                @click="emit('download', 'draft')"
              >
                откройте его здесь</button
              >.
            </p>
          </div>
        </li>

        <li v-if="withDocument" class="flex items-start gap-3.5">
          <span
            class="flex size-7 shrink-0 items-center justify-center rounded-full text-[0.8125rem] font-extrabold"
            :class="rulesAccepted ? 'bg-success text-white' : 'border-[3px] border-brand text-brand-active'"
            aria-hidden="true"
          >
            <Check v-if="rulesAccepted" class="size-3.5 stroke-[3]" />
            <template v-else>2</template>
          </span>
          <div class="min-w-0 flex-1 space-y-2 pt-0.5">
            <p class="text-[0.9375rem] font-semibold text-ink">Примите Правила электронного взаимодействия</p>
            <CheckboxField v-if="rules" v-model="rulesAccepted" data-sign="rules">
              Принимаю
              <button type="button" class="font-medium text-info underline underline-offset-2" @click.prevent="rulesOpen = true">
                Правила электронного взаимодействия</button
              ><template v-if="rulesDate"> (ред. от {{ rulesDate }})</template>
            </CheckboxField>
            <div v-else-if="rulesError" class="flex flex-wrap items-center gap-3 text-sm">
              <p class="text-brand" role="alert">Не удалось загрузить Правила: {{ rulesError }}</p>
              <BaseButton size="s" variant="secondary" @click="emit('reloadRules')">Повторить</BaseButton>
            </div>
            <p v-else class="text-sm text-ink-secondary">Загружаем Правила электронного взаимодействия…</p>
          </div>
        </li>

        <li class="flex items-start gap-3.5">
          <span
            class="flex size-7 shrink-0 items-center justify-center rounded-full border-[3px] border-brand text-[0.8125rem] font-extrabold text-brand-active"
            aria-hidden="true"
          >
            {{ withDocument ? 3 : 1 }}
          </span>
          <div class="min-w-0 flex-1 pt-0.5">
            <TextField
              v-model="password"
              data-sign="password"
              label="Подтвердите паролем от кабинета"
              type="password"
              autocomplete="current-password"
              :error="passwordError ?? undefined"
              :hint="
                viaDemo
                  ? 'Вы вошли через демо-доступ без пароля. Пароль демо-учёток — значение DEMO_PASSWORD из README стенда'
                  : 'Подтверждаем, что подписываете именно вы'
              "
            />
          </div>
        </li>
      </ol>
    </form>

    <p class="flex items-start gap-2.5 text-[0.8125rem] leading-relaxed text-ink-secondary">
      <ShieldCheck class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
      <template v-if="withDocument">
        Вы подписываете простой электронной подписью — паролем от кабинета. Сразу после вас договор подпишет банк своей
        электронной подписью с меткой времени.
      </template>
      <template v-else>Вы подписываете простой электронной подписью — паролем от кабинета.</template>
    </p>

    <BaseModal v-if="rules" v-model:open="rulesOpen" :title="rules.title" :description="rulesDate ? `Редакция от ${rulesDate}` : undefined" wide>
      <div class="space-y-3 text-sm leading-relaxed text-ink">
        <p v-for="(paragraph, index) in rules.paragraphs" :key="index">{{ paragraph }}</p>
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="rulesOpen = false">Закрыть</BaseButton>
        <BaseButton @click="acceptRules">Принимаю</BaseButton>
      </template>
    </BaseModal>
  </section>

  <p v-else class="rounded-2xl bg-surface-soft p-4 text-sm text-ink">
    У вас нет права подписи от этой компании. Подписать может руководитель компании или
    сотрудник с доверенностью на подпись<template v-if="signers">: {{ signers }}</template>.
  </p>
</template>
