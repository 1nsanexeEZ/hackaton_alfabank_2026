<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next'
import { useId } from 'vue'

defineProps<{ title: string }>()

const isOpen = defineModel<boolean>('open', { default: false })

const id = useId()
</script>

<template>
  <div class="border-b border-line">
    <h3>
      <button
        :id="`${id}-trigger`"
        type="button"
        :aria-expanded="isOpen"
        :aria-controls="`${id}-panel`"
        class="flex w-full items-center justify-between gap-4 py-5 text-left text-base font-semibold text-ink transition-colors hover:text-brand lg:text-lg"
        @click="isOpen = !isOpen"
      >
        <span>{{ title }}</span>
        <ChevronDown
          class="size-5 shrink-0 text-ink-secondary transition-transform duration-300"
          :class="isOpen && 'rotate-180'"
          aria-hidden="true"
        />
      </button>
    </h3>
    <div
      :id="`${id}-panel`"
      role="region"
      :aria-labelledby="`${id}-trigger`"
      :inert="!isOpen"
      class="grid transition-[grid-template-rows] duration-300"
      :class="isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
    >
      <div class="overflow-hidden">
        <div class="pr-9 pb-5 text-ink-secondary">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>
