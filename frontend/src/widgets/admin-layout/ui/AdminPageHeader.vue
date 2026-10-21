<script setup lang="ts">
import { ChevronLeft } from 'lucide-vue-next'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

/** Заголовок страницы админки: ссылка назад, название, пояснение и действия справа */
withDefaults(defineProps<{ title: string; description?: string; back?: RouteLocationRaw; backLabel?: string }>(), {
  description: undefined,
  back: undefined,
  backLabel: 'Назад',
})
</script>

<template>
  <header class="mb-6 flex flex-wrap items-end justify-between gap-4">
    <div class="min-w-0">
      <RouterLink
        v-if="back"
        :to="back"
        class="mb-2 inline-flex items-center gap-1 text-sm font-medium text-ink-secondary transition-colors hover:text-ink"
      >
        <ChevronLeft class="size-4" aria-hidden="true" />
        {{ backLabel }}
      </RouterLink>
      <h1 class="text-2xl font-bold tracking-tight text-ink lg:text-[1.75rem]">{{ title }}</h1>
      <p v-if="description" class="mt-1 max-w-2xl text-sm text-ink-secondary lg:text-base">{{ description }}</p>
      <slot name="meta" />
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
