<script setup lang="ts" generic="T extends string">
import { ChevronDown } from 'lucide-vue-next'
import { useId } from 'vue'

defineProps<{
  label: string
  options: readonly { value: T; label: string }[]
}>()

const model = defineModel<T>({ required: true })

const id = useId()
</script>

<template>
  <div>
    <label :for="id" class="mb-2 block text-sm font-medium text-ink">{{ label }}</label>
    <div class="relative">
      <select
        :id="id"
        v-model="model"
        class="h-14 w-full cursor-pointer appearance-none rounded-xl bg-surface pr-12 pl-4 text-base text-ink transition outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
      >
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <ChevronDown
        class="pointer-events-none absolute top-1/2 right-4 size-5 -translate-y-1/2 text-ink-secondary"
        aria-hidden="true"
      />
    </div>
  </div>
</template>
