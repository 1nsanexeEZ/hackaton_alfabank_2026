<script setup lang="ts">
import { CircleCheck } from 'lucide-vue-next'

import { SERVER_STATUS_META } from '@/entities/application'
import type { ApplicationDto } from '@/shared/api'
import { formatMoney, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

defineProps<{ application: ApplicationDto; productTitle: string }>()
</script>

<template>
  <div class="flex flex-col items-start" role="status">
    <span class="flex size-14 items-center justify-center rounded-full bg-success-soft">
      <CircleCheck class="size-7 text-success" aria-hidden="true" />
    </span>
    <h3 class="text-subtitle mt-5 text-ink">Заявка № {{ application.number }} отправлена</h3>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <BaseBadge :tone="SERVER_STATUS_META[application.status]?.tone ?? 'neutral'">
        {{ SERVER_STATUS_META[application.status]?.label ?? application.status }}
      </BaseBadge>
      <span v-if="application.client_stage" class="text-sm text-ink-secondary">{{ application.client_stage }}</span>
    </div>
    <p class="mt-4 text-ink">
      {{ productTitle }}
      <template v-if="application.request.amount">
        · {{ formatMoney(Number(application.request.amount)) }}
      </template>
      <template v-if="application.request.term_months"> · {{ formatTerm(application.request.term_months) }}</template>
    </p>
    <p class="mt-4 text-ink-secondary">
      Следующий шаг — автоматическая проверка данных компании и оценка риска. Если банку что-то понадобится, запрос
      придёт в личный кабинет. Там же появится решение.
    </p>
  </div>
</template>
