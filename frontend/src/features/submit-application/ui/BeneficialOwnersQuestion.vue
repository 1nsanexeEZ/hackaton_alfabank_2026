<script setup lang="ts">
import { Plus, Trash2 } from 'lucide-vue-next'

import { SegmentedControl, TextField } from '@/shared/ui'

import { emptyOwner, MAX_OWNERS, type OwnerForm, type OwnersForm } from '../model/owners'
import CountryField from './CountryField.vue'

/**
 * Бенефициары со слов клиента (115-ФЗ ст. 6.1): банк сверяет их с ЕГРЮЛ и проверяет по перечням.
 * Подачу ответ не блокирует, но без него специалисту придётся спрашивать отдельно.
 */
defineProps<{ errors: Record<string, string> }>()

const form = defineModel<OwnersForm>('owners', { required: true })

const ANSWERS: { value: OwnersForm['answer']; label: string }[] = [
  { value: 'none', label: 'Никто' },
  { value: 'list', label: 'Есть такие — назову' },
]
const BASIS: { value: OwnerForm['basis']; label: string }[] = [
  { value: 'ownership', label: 'Владеет больше 25%' },
  { value: 'control', label: 'Контролирует иначе' },
]

const choiceClass = (active: boolean) =>
  active ? 'bg-brand-soft text-ink ring-2 ring-brand' : 'bg-surface-soft text-ink hover:bg-surface'

function add() {
  if (form.value.owners.length < MAX_OWNERS) form.value.owners.push(emptyOwner())
}

function remove(index: number) {
  form.value.owners.splice(index, 1)
  if (!form.value.owners.length) form.value.owners.push(emptyOwner())
}
</script>

<template>
  <section class="space-y-4">
    <div>
      <p id="owners-question" class="text-sm font-semibold text-ink">
        Кто владеет больше чем 25% компании — напрямую или через другие компании — или иначе контролирует её действия?
      </p>
      <p class="mt-1 text-xs text-ink-secondary">Банк сверит ответ с ЕГРЮЛ. Подачу он не задерживает, но ускорит проверку.</p>
      <div class="mt-3 grid gap-2 sm:grid-cols-2" role="radiogroup" aria-labelledby="owners-question">
        <button
          v-for="item in ANSWERS"
          :key="String(item.value)"
          type="button"
          role="radio"
          class="rounded-xl px-4 py-3 text-left text-sm font-medium transition-colors"
          :class="choiceClass(form.answer === item.value)"
          :aria-checked="form.answer === item.value"
          @click="form.answer = item.value"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <div v-if="form.answer === 'list'" class="space-y-3">
      <div
        v-for="(owner, index) in form.owners"
        :key="index"
        class="space-y-3 rounded-2xl border border-line p-4"
        :data-field="`beneficial_owners.owners.${index}.name`"
      >
        <div class="flex items-start gap-3">
          <TextField
            v-model="owner.name"
            class="flex-1"
            label="ФИО или наименование"
            placeholder="Смирнова Анна Сергеевна"
            :maxlength="300"
            :error="errors[`beneficial_owners.owners.${index}.name`]"
          />
          <button
            type="button"
            class="mt-7 flex size-11 shrink-0 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface hover:text-ink"
            :aria-label="`Убрать бенефициара ${index + 1}`"
            @click="remove(index)"
          >
            <Trash2 class="size-4" aria-hidden="true" />
          </button>
        </div>
        <SegmentedControl v-model="owner.basis" :options="BASIS" label="Основание" small />
        <CountryField
          v-model="owner.country"
          class="sm:max-w-xs"
          :data-field="`beneficial_owners.owners.${index}.country`"
          :error="errors[`beneficial_owners.owners.${index}.country`]"
        />
      </div>
      <button
        v-if="form.owners.length < MAX_OWNERS"
        type="button"
        class="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
        @click="add"
      >
        <Plus class="size-4" aria-hidden="true" />
        Ещё бенефициар
      </button>
    </div>
  </section>
</template>
