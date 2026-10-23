<script setup lang="ts">
import { FileSignature, ShieldCheck } from 'lucide-vue-next'
import { ref } from 'vue'

import type { ContractDto } from '@/shared/api'
import { BaseButton, TextField } from '@/shared/ui'

import ContractView from './ContractView.vue'

/**
 * Подписание договора: сначала договор (GET /applications/{id}/contract), потом пароль аккаунта ещё раз
 * (step-up). В подпись уходит offer_hash договора — клиент подписывает то, что видел. Подпись идёт через
 * мок ЭДО — реальной электронной подписи нет, это и пишем. Без права подписи объясняем, кто может подписать.
 */
defineProps<{ contract: ContractDto | null; contractError: string | null; canSign: boolean; busy: string | null }>()

const emit = defineEmits<{ sign: [password: string]; reload: [] }>()

const password = ref('')
</script>

<template>
  <section class="rounded-2xl bg-surface-soft p-5">
    <h3 class="flex items-center gap-2 text-base font-bold text-ink">
      <FileSignature class="size-5 text-brand" aria-hidden="true" />
      Подпишите договор<template v-if="contract"> № {{ contract.number }}</template>
    </h3>

    <ContractView v-if="contract" class="mt-4" :contract="contract" />
    <div v-else-if="contractError" class="mt-3 space-y-3">
      <p class="text-sm text-brand" role="alert">{{ contractError }}</p>
      <BaseButton variant="secondary" @click="emit('reload')">Загрузить договор ещё раз</BaseButton>
    </div>
    <p v-else class="mt-3 text-sm text-ink-secondary">Загружаем договор…</p>

    <form v-if="canSign && contract" class="mt-5 space-y-3 border-t border-line pt-4" @submit.prevent="password && emit('sign', password)">
      <TextField
        v-model="password"
        label="Пароль от кабинета"
        type="password"
        autocomplete="current-password"
        hint="Подтверждаем, что подписываете именно вы"
      />
      <BaseButton type="submit" :loading="busy === 'sign'" :disabled="!password || Boolean(busy)">Подписать договор</BaseButton>
      <p class="flex items-start gap-2 text-xs text-ink-secondary">
        <ShieldCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Подписание смоделировано: документ уходит в мок ЭДО, реальной электронной подписи и выдачи денег нет.
      </p>
    </form>
    <p v-else-if="!canSign" class="mt-4 rounded-xl bg-white p-3 text-sm text-ink">
      У вас нет права подписи от этой компании. Подписать может руководитель, полномочия которого подтверждены
      реестром, или сотрудник с доверенностью на подпись.
    </p>
  </section>
</template>
