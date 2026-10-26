<script setup lang="ts">
/** Плитка с главной цифрой: подпись, значение крупно и пояснение под ним */
withDefaults(defineProps<{ label: string; hint?: string | null; tone?: 'default' | 'success' | 'warning' | 'brand' }>(), {
  hint: null,
  tone: 'default',
})

const TONE_CLASS = { default: 'text-ink', success: 'text-success', warning: 'text-warning', brand: 'text-brand' } as const
</script>

<template>
  <div class="min-w-0 rounded-xl bg-surface-soft px-3.5 py-3">
    <p class="text-xs text-ink-secondary">{{ label }}</p>
    <p class="mt-1 text-lg leading-snug font-bold break-words tabular-nums" :class="TONE_CLASS[tone]"><slot /></p>
    <p v-if="hint" class="mt-0.5 text-xs text-ink-secondary">{{ hint }}</p>
  </div>
</template>
