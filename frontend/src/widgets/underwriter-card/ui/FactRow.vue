<script setup lang="ts">
/** Строка «показатель — значение» внутри блока карточки: подпись слева, значение справа, пояснение под значением */
withDefaults(defineProps<{ label: string; hint?: string | null; tone?: 'default' | 'success' | 'warning' | 'brand' }>(), {
  hint: null,
  tone: 'default',
})

const TONE_CLASS = { default: 'text-ink', success: 'text-success', warning: 'text-warning', brand: 'text-brand' } as const
</script>

<template>
  <div class="flex items-start justify-between gap-4 border-t border-line py-2.5 text-sm first:border-t-0">
    <dt class="max-w-[48%] shrink-0 text-ink-secondary">{{ label }}</dt>
    <dd class="min-w-0 text-right font-semibold break-words" :class="TONE_CLASS[tone]">
      <slot />
      <span v-if="hint" class="mt-0.5 block text-xs font-medium text-ink-secondary">{{ hint }}</span>
    </dd>
  </div>
</template>
