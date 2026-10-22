<script setup lang="ts">
import { CircleCheck } from 'lucide-vue-next'
import { computed } from 'vue'

import { APPLICATION_STATUS_META, toClientStatus } from '@/entities/application'
import type { ApplicationDto } from '@/shared/api'
import { formatMoney, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

const props = defineProps<{ application: ApplicationDto; productTitle: string }>()

// Клиенту — клиентский статус, как в BFF, а не внутренний статус процесса
const status = computed(() => {
  const clientStatus = toClientStatus(props.application.status, props.application.client_stage)
  return clientStatus ? APPLICATION_STATUS_META[clientStatus] : null
})
</script>

<template>
  <div class="flex flex-col items-start" role="status">
    <span class="flex size-14 items-center justify-center rounded-full bg-success-soft">
      <CircleCheck class="size-7 text-success" aria-hidden="true" />
    </span>
    <h3 class="text-subtitle mt-5 text-ink">Заявка № {{ application.number }} отправлена</h3>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <BaseBadge v-if="status" :tone="status.tone">{{ status.label }}</BaseBadge>
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
