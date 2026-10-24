<script setup lang="ts">
import { Check, Copy, FileSignature, ShieldCheck } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import type { ContractDto, EsignRulesDto } from '@/shared/api'
import { copyText, formatDateTime } from '@/shared/lib'
import { BaseButton, BaseModal, CheckboxField, TextField } from '@/shared/ui'

import { hasContractDocument } from '../model/useApplicationCard'
import ContractDocumentBlock from './ContractDocumentBlock.vue'
import ContractStages from './ContractStages.vue'
import ContractView from './ContractView.vue'

/**
 * Подписание договора: договор (GET /applications/{id}/contract) и его PDF, Правила электронного
 * взаимодействия, пароль аккаунта ещё раз (step-up). В подпись уходят offer_hash и SHA-256 проекта PDF —
 * клиент подписывает ровно то, что видел. Со старым бэкендом PDF и правил нет — подпись как раньше.
 * Без права подписи объясняем, кто может подписать.
 */
const props = defineProps<{
  contract: ContractDto | null
  contractError: string | null
  canSign: boolean
  busy: string | null
  documentSlow: boolean
  rules: EsignRulesDto | null
  rulesError: string | null
}>()

const emit = defineEmits<{
  sign: [password: string, rulesAccepted: boolean]
  reload: []
  refreshDocument: []
  reloadRules: []
  download: [kind: 'draft' | 'signed']
}>()

const password = ref('')
const rulesAccepted = ref(false)
const rulesOpen = ref(false)
const copied = ref(false)

/** Бэкенд с PDF договора и Правилами ЭП */
const withDocument = computed(() => hasContractDocument(props.contract))
const signed = computed(() => props.contract?.status === 'signed')
const draftReady = computed(() => props.contract?.document?.kind === 'draft' && props.contract.document.status === 'ready')

/** Редакция правил: «2026-10-24» → «24.10.2026» */
const rulesDate = computed(() => props.rules?.effective_from.split('-').reverse().join('.') ?? null)

const canSubmit = computed(
  () => Boolean(password.value) && !props.busy && (!withDocument.value || (draftReady.value && rulesAccepted.value && props.rules)),
)

// Правила обновились (rules_outdated) — прежнее согласие не считается
watch(
  () => props.rules?.version,
  () => (rulesAccepted.value = false),
)

function acceptRules() {
  rulesAccepted.value = true
  rulesOpen.value = false
}

async function copyUid() {
  if (!props.contract?.uid || !(await copyText(props.contract.uid))) return
  copied.value = true
  setTimeout(() => (copied.value = false), 2_000)
}

function submit() {
  if (canSubmit.value) emit('sign', password.value, rulesAccepted.value)
}
</script>

<template>
  <section class="rounded-2xl bg-surface-soft p-5">
    <h3 class="flex items-center gap-2 text-base font-bold text-ink">
      <FileSignature class="size-5 text-brand" aria-hidden="true" />
      <template v-if="signed">Договор подписан вами</template>
      <template v-else>Подпишите договор</template>
      <template v-if="contract"> № {{ contract.number }}</template>
    </h3>

    <template v-if="contract">
      <ContractStages v-if="withDocument" class="mt-4" :contract="contract" />

      <!-- Клиент подписал, банк ещё не выдал кредит: ждём подпись банка -->
      <div v-if="signed" class="mt-4 space-y-3 text-sm text-ink">
        <p v-if="contract.signature">Вы подписали договор {{ formatDateTime(contract.signature.signed_at) }}. Кредит выдадим сразу после подписи банка.</p>
        <ContractDocumentBlock
          v-if="withDocument"
          :contract="contract"
          :busy="busy"
          :slow="documentSlow"
          @download="(kind) => emit('download', kind)"
          @refresh="emit('refreshDocument')"
        />
      </div>

      <template v-else>
        <ContractDocumentBlock
          v-if="withDocument"
          class="mt-4"
          :contract="contract"
          :busy="busy"
          :slow="documentSlow"
          @download="(kind) => emit('download', kind)"
          @refresh="emit('refreshDocument')"
        />
        <p v-if="contract.uid" class="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-secondary">
          УИд договора:
          <span class="font-mono break-all text-ink">{{ contract.uid }}</span>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-ink-secondary transition-colors hover:bg-white hover:text-ink"
            @click="copyUid"
          >
            <component :is="copied ? Check : Copy" class="size-3.5" aria-hidden="true" />
            {{ copied ? 'Скопировано' : 'Скопировать' }}
          </button>
        </p>
        <ContractView class="mt-4" :contract="contract" />
      </template>
    </template>
    <div v-else-if="contractError" class="mt-3 space-y-3">
      <p class="text-sm text-brand" role="alert">{{ contractError }}</p>
      <BaseButton variant="secondary" @click="emit('reload')">Загрузить договор ещё раз</BaseButton>
    </div>
    <p v-else class="mt-3 text-sm text-ink-secondary">Загружаем договор…</p>

    <form v-if="canSign && contract && !signed" class="mt-5 space-y-3 border-t border-line pt-4" @submit.prevent="submit">
      <TextField
        v-model="password"
        label="Пароль от кабинета"
        type="password"
        autocomplete="current-password"
        hint="Подтверждаем, что подписываете именно вы"
      />
      <template v-if="withDocument">
        <CheckboxField v-if="rules" v-model="rulesAccepted">
          Принимаю
          <button type="button" class="font-medium text-info underline underline-offset-2" @click.prevent="rulesOpen = true">
            Правила электронного взаимодействия</button
          ><template v-if="rulesDate"> (ред. от {{ rulesDate }})</template>
        </CheckboxField>
        <div v-else-if="rulesError" class="flex flex-wrap items-center gap-3 text-sm">
          <p class="text-brand" role="alert">Не удалось загрузить Правила электронного взаимодействия: {{ rulesError }}</p>
          <BaseButton size="s" variant="secondary" @click="emit('reloadRules')">Повторить</BaseButton>
        </div>
        <p v-else class="text-sm text-ink-secondary">Загружаем Правила электронного взаимодействия…</p>
      </template>
      <BaseButton type="submit" :loading="busy === 'sign'" :disabled="!canSubmit">Подписать договор</BaseButton>
      <p class="flex items-start gap-2 text-xs text-ink-secondary">
        <ShieldCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <template v-if="withDocument">
          Вы подписываете договор простой электронной подписью: паролем от кабинета. Банк подпишет его своей электронной
          подписью автоматически. Подпись банка — ключ демо-стенда, не квалифицированная.
        </template>
        <template v-else>
          Подписание смоделировано: документ уходит в мок ЭДО, реальной электронной подписи и выдачи денег нет.
        </template>
      </p>
    </form>
    <p v-else-if="!canSign && !signed" class="mt-4 rounded-xl bg-white p-3 text-sm text-ink">
      У вас нет права подписи от этой компании. Подписать может руководитель, полномочия которого подтверждены
      реестром, или сотрудник с доверенностью на подпись.
    </p>

    <BaseModal
      v-if="rules"
      v-model:open="rulesOpen"
      :title="rules.title"
      :description="rulesDate ? `Редакция от ${rulesDate}` : undefined"
      wide
    >
      <div class="space-y-3 text-sm leading-relaxed text-ink">
        <p v-for="(paragraph, index) in rules.paragraphs" :key="index">{{ paragraph }}</p>
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="rulesOpen = false">Закрыть</BaseButton>
        <BaseButton v-if="canSign" @click="acceptRules">Принимаю</BaseButton>
      </template>
    </BaseModal>
  </section>
</template>
