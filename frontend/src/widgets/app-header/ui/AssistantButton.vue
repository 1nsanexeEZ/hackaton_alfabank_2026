<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import { computed } from 'vue'

import { ASSISTANT_AVAILABILITY_LABEL, assistant } from '@/entities/assistant'

/**
 * Кнопка «Умный помощник»: пилюля с градиентной красной обводкой, иконка-вспышка и точка состояния
 * (зелёная — отвечает ИИ, жёлтая — по шаблонам, серая — недоступен). Открытое окно — красноватая заливка.
 * На ширине меньше lg подпись скрыта и остаётся иконка; `block` — строка мобильного меню.
 */
withDefaults(defineProps<{ block?: boolean }>(), { block: false })

const availability = computed(() => assistant.state.availability)
const isOpen = computed(() => assistant.state.open)
const label = computed(() => ASSISTANT_AVAILABILITY_LABEL[availability.value])
</script>

<template>
  <button
    type="button"
    data-assistant-trigger
    :data-state="availability"
    :data-open="isOpen || undefined"
    :aria-expanded="isOpen"
    aria-haspopup="dialog"
    :aria-label="`Умный помощник: ${label}`"
    :title="label"
    :class="[
      'assistant-btn relative inline-flex h-10 shrink-0 cursor-pointer items-center gap-2 rounded-full text-sm font-medium whitespace-nowrap text-on-night',
      block ? 'w-full justify-between px-4' : 'max-lg:w-10 max-lg:justify-center max-lg:px-0 lg:pr-4 lg:pl-3',
    ]"
  >
    <span class="inline-flex items-center gap-2">
      <Sparkles class="assistant-btn__spark size-[18px] shrink-0" aria-hidden="true" />
      <span :class="block ? '' : 'max-lg:hidden'">Умный помощник</span>
    </span>
    <span v-if="block" class="text-xs font-normal text-on-night-secondary">{{ label }}</span>
    <span
      class="assistant-btn__dot size-[7px] shrink-0 rounded-full"
      :class="block ? '' : 'max-lg:absolute max-lg:top-1 max-lg:right-1 max-lg:size-2 max-lg:outline-2 max-lg:outline-night'"
      aria-hidden="true"
    />
  </button>
</template>

<style scoped>
.assistant-btn {
  --assistant-fill: var(--color-night);
  --assistant-edge: linear-gradient(
    120deg,
    var(--color-brand),
    color-mix(in srgb, var(--color-brand) 15%, transparent) 55%,
    rgb(255 255 255 / 0.28)
  );

  border: 1.5px solid transparent;
  background:
    linear-gradient(var(--assistant-fill), var(--assistant-fill)) padding-box,
    var(--assistant-edge) border-box;
  transition:
    color 0.25s,
    box-shadow 0.25s,
    scale 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.assistant-btn:active {
  scale: 0.96;
}

.assistant-btn__spark {
  color: color-mix(in srgb, var(--color-brand) 75%, white);
  transition: rotate 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.assistant-btn:hover .assistant-btn__spark {
  rotate: 72deg;
}

.assistant-btn__dot {
  background: var(--color-signal-off);
}

.assistant-btn[data-state='llm'] .assistant-btn__dot {
  background: var(--color-signal-ok);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-signal-ok) 80%, transparent);
}

.assistant-btn[data-state='rules'] .assistant-btn__dot {
  background: var(--color-signal-warn);
  box-shadow: 0 0 8px color-mix(in srgb, var(--color-signal-warn) 60%, transparent);
}

.assistant-btn:hover:not([data-state='off'], [data-state='unknown']) {
  --assistant-fill: color-mix(in srgb, var(--color-brand) 12%, var(--color-night));
  --assistant-edge: linear-gradient(120deg, var(--color-brand), rgb(255 255 255 / 0.4));
}

/* Недоступен: приглушённая кнопка с серой обводкой, но нажимается — окно объяснит, что случилось */
.assistant-btn[data-state='off'],
.assistant-btn[data-state='unknown'] {
  color: var(--color-on-night-secondary);
  --assistant-edge: linear-gradient(120deg, rgb(255 255 255 / 0.18), rgb(255 255 255 / 0.06));
}

.assistant-btn[data-state='off'] .assistant-btn__spark,
.assistant-btn[data-state='unknown'] .assistant-btn__spark {
  color: var(--color-on-night-secondary);
}

/* Окно открыто: красноватая заливка */
.assistant-btn[data-open] {
  --assistant-fill: color-mix(in srgb, var(--color-brand) 16%, var(--color-night));
  --assistant-edge: linear-gradient(120deg, var(--color-brand), color-mix(in srgb, var(--color-brand) 40%, transparent));

  color: var(--color-on-night);
}

@media (prefers-reduced-motion: reduce) {
  .assistant-btn__spark {
    transition: none;
  }
}
</style>
