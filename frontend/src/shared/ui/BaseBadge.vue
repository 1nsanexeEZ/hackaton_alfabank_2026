<script setup lang="ts">
import type { BadgeTone } from './badge'

withDefaults(defineProps<{ tone?: BadgeTone }>(), { tone: 'neutral' })

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: 'bg-surface text-ink-secondary',
  brand: 'bg-brand-soft text-brand',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  info: 'bg-info-soft text-info',
  glass: 'bg-night-glass text-on-night',
}
</script>

<template>
  <span
    class="inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium whitespace-nowrap"
    :class="TONE_CLASS[tone]"
  >
    <slot />
  </span>
</template>
