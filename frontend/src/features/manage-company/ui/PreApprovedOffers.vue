<script setup lang="ts">
import { BadgeCheck } from 'lucide-vue-next'

import type { PreApprovedOfferDto } from '@/shared/api'
import { formatDate, formatMoney, formatPercent, formatTermLimit } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

/**
 * Предварительное одобрение: до какой суммы и под какую ставку банк готов дать без долгой проверки.
 * Только компаниям, сверенным с ЕГРЮЛ: при расхождении с реестром предложения снимаются.
 */
defineProps<{ offers: PreApprovedOfferDto[]; productTitle: (code: string) => string; verified: boolean }>()

const emit = defineEmits<{ apply: [code: string, maxAmount: number] }>()
</script>

<template>
  <section>
    <h3 class="text-base font-bold text-ink">Предварительно одобрено</h3>
    <p class="mt-0.5 text-sm text-ink-secondary">
      Предварительная оценка банка. Окончательное решение — после заявки.
    </p>
    <p v-if="!offers.length && !verified" class="mt-3 rounded-2xl bg-warning-soft p-4 text-sm text-ink">
      Предложения появятся, когда реквизиты компании будут актуальны — обновите их выше
    </p>
    <p v-else-if="!offers.length" class="mt-3 rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
      Пока нет — подайте финансовую отчётность, и банк пересчитает предложение
    </p>
    <ul v-else class="mt-3 grid gap-2 sm:grid-cols-2">
      <li v-for="offer in offers" :key="offer.product_code" class="flex flex-col gap-3 rounded-2xl bg-success-soft p-4">
        <div>
          <p class="flex items-center gap-2 text-sm font-semibold text-ink">
            <BadgeCheck class="size-4 text-success" aria-hidden="true" />
            {{ productTitle(offer.product_code) }}
          </p>
          <p class="mt-1 text-lg font-bold text-ink">до {{ formatMoney(Number(offer.max_amount)) }}</p>
          <p class="text-xs text-ink-secondary">
            от {{ formatPercent(Number(offer.rate_from)) }} · {{ formatTermLimit(offer.term_max_months) }} · действует до
            {{ formatDate(offer.valid_until) }}
          </p>
          <p v-if="offer.note" class="mt-1 text-xs text-ink-secondary">{{ offer.note }}</p>
        </div>
        <BaseButton size="s" variant="secondary" class="self-start" @click="emit('apply', offer.product_code, Number(offer.max_amount))">
          Оформить
        </BaseButton>
      </li>
    </ul>
  </section>
</template>
