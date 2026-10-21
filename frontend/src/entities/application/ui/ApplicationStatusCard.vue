<script setup lang="ts">
import { Check } from 'lucide-vue-next'
import { computed } from 'vue'

import { formatMoney, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import { APPLICATION_STATUS_META } from '../model/status'
import type { ApplicationPreview } from '../model/types'

/** Карточка заявки со шкалой этапов. Рассчитана на тёмный фон */
const props = defineProps<{ application: ApplicationPreview }>()

const statusMeta = computed(() => APPLICATION_STATUS_META[props.application.status])
</script>

<template>
  <article
    class="rounded-card bg-night-elevated/90 p-5 text-on-night ring-1 ring-night-line sm:p-6"
    aria-label="Пример заявки в кабинете"
  >
    <header class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs text-on-night-secondary">Заявка № {{ application.number }}</p>
        <p class="mt-1 font-semibold">{{ application.productTitle }}</p>
      </div>
      <BaseBadge :tone="statusMeta.tone">{{ statusMeta.label }}</BaseBadge>
    </header>

    <dl class="mt-5 grid grid-cols-2 gap-3">
      <div class="rounded-2xl bg-white/5 p-3">
        <dt class="text-xs text-on-night-secondary">Сумма</dt>
        <dd class="mt-1 text-base font-semibold sm:text-lg">{{ formatMoney(application.amount) }}</dd>
      </div>
      <div class="rounded-2xl bg-white/5 p-3">
        <dt class="text-xs text-on-night-secondary">Срок</dt>
        <dd class="mt-1 text-base font-semibold sm:text-lg">{{ formatTerm(application.termMonths) }}</dd>
      </div>
    </dl>

    <ol class="mt-6">
      <li
        v-for="(stage, index) in application.stages"
        :key="stage.title"
        class="relative flex gap-3 pb-5 last:pb-0"
        :aria-current="stage.state === 'current' ? 'step' : undefined"
      >
        <span
          v-if="index < application.stages.length - 1"
          class="absolute top-7 bottom-1 left-3 w-px"
          :class="stage.state === 'done' ? 'bg-success' : 'bg-night-line'"
          aria-hidden="true"
        />
        <span
          v-if="stage.state === 'done'"
          class="relative flex size-6 shrink-0 items-center justify-center rounded-full bg-success"
        >
          <Check class="size-3.5 text-white" :stroke-width="3" aria-hidden="true" />
        </span>
        <span
          v-else-if="stage.state === 'current'"
          class="relative flex size-6 shrink-0 items-center justify-center rounded-full bg-brand/20"
        >
          <span class="absolute inset-0 animate-ping rounded-full bg-brand/30" aria-hidden="true" />
          <span class="size-2.5 rounded-full bg-brand" />
        </span>
        <span v-else class="relative size-6 shrink-0 rounded-full border-2 border-night-line" />

        <div class="min-w-0">
          <p
            class="text-sm font-medium"
            :class="stage.state === 'pending' ? 'text-on-night-secondary' : 'text-on-night'"
          >
            {{ stage.title }}
          </p>
          <p v-if="stage.caption" class="mt-0.5 text-xs text-on-night-secondary">{{ stage.caption }}</p>
        </div>
      </li>
    </ol>
  </article>
</template>
