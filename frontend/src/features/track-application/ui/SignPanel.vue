<script setup lang="ts">
import { FileSignature, ShieldCheck } from 'lucide-vue-next'
import { ref } from 'vue'

import type { OfferDto } from '@/shared/api'
import { formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/**
 * Подписание договора: пароль аккаунта ещё раз (step-up). Подпись идёт через мок ЭДО —
 * реальной электронной подписи нет, это и пишем. Без права подписи объясняем, кто может подписать.
 */
defineProps<{ offer: OfferDto | null; canSign: boolean; busy: string | null }>()

const emit = defineEmits<{ sign: [password: string] }>()

const password = ref('')
</script>

<template>
  <section class="rounded-2xl bg-surface-soft p-5">
    <h3 class="flex items-center gap-2 text-base font-bold text-ink">
      <FileSignature class="size-5 text-brand" aria-hidden="true" />
      Подпишите договор
    </h3>
    <p v-if="offer" class="mt-1 text-sm text-ink-secondary">
      {{ formatMoney(Number(offer.amount)) }} на {{ formatTerm(offer.term_months) }} под
      {{ formatPercent(Number(offer.rate)) }}, платёж {{ formatMoney(Number(offer.monthly_payment)) }} в месяц.
    </p>

    <form v-if="canSign" class="mt-4 space-y-3" @submit.prevent="password && emit('sign', password)">
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
    <p v-else class="mt-4 rounded-xl bg-white p-3 text-sm text-ink">
      У вас нет права подписи от этой компании. Подписать может руководитель, полномочия которого подтверждены
      реестром, или сотрудник с доверенностью на подпись.
    </p>
  </section>
</template>
